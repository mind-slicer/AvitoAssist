import re
import time
import random
import json
import gzip
import os
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List, Callable, Set
from urllib.parse import urlencode, urlparse, parse_qs
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from PyQt6.QtCore import QObject, pyqtSignal

from app.core.driver import DriverManager
from app.config import USER_AGENTS, BASE_URL_MOSCOW, ALL_PAGES_LIMIT
from app.core.blacklist_manager import get_blacklist_manager
from app.core.selectors import AvitoSelectors

from app.core.log_manager import logger


# Ban recovery mechanism
class BanRecoveryStrategy:
    def __init__(self, driver_manager):
        self.driver_manager = driver_manager
        self.ban_count = 0
        self.last_ban_time = None
    
    def handle_soft_ban(self, stop_check: Callable[[], bool] = None) -> bool:
        self.ban_count += 1
        current_time = time.time()
        
        logger.warning(f"SOFT BAN #{self.ban_count} DETECTED")
        
        if self.ban_count == 1:
            wait_time = 30
            strategy = "Быстрое восстановление"
        elif self.ban_count == 2:
            wait_time = 60
            strategy = "Сброс cookies + ожидание"
        elif self.ban_count == 3:
            wait_time = 120
            strategy = "Полный сброс + долгое ожидание"
        else:
            wait_time = 180
            strategy = "Критическое ожидание"
        
        logger.info(f"Стратегия анти-бана: {strategy} ({wait_time}с)")
        
        if self.ban_count >= 2:
            try:
                logger.dev("Сброс cookies...")
                self.driver_manager.driver.delete_all_cookies()
            except Exception as e:
                logger.dev(f"Cookie clear failed: {e}", level="ERROR")
        
        if self.ban_count >= 3:
            try:
                logger.dev("Смена User-Agent...")
                new_ua = random.choice(USER_AGENTS)
                self.driver_manager.driver.execute_cdp_cmd(
                    'Network.setUserAgentOverride', 
                    {"userAgent": new_ua}
                )
            except Exception as e:
                logger.dev(f"UA change failed: {e}", level="ERROR")
        
        step = 1
        elapsed = 0
        while elapsed < wait_time:
            if stop_check and stop_check():
                if stop_check and stop_check():
                    logger.info("Восстановление прервано пользователем")
                return False
            
            remaining = wait_time - elapsed
            if elapsed % 10 == 0:
                logger.progress(f"Ожидание снятия бана... {int(remaining)}с", token="ban_timer")
            
            time.sleep(step)
            elapsed += step
        
        if self.last_ban_time and (current_time - self.last_ban_time) < 300:
            logger.warning("ПРЕДУПРЕЖДЕНИЕ: Частые баны! Рекомендуется увеличить паузы.")
        
        self.last_ban_time = current_time
        logger.success("Попытка продолжения работы...")
        return True

# Class loads the site pages carefully
class PageLoader:
    @staticmethod
    def wait_for_load(driver, timeout: int = 5) -> bool:
        try:
            WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") in ["interactive", "complete"])
            return True
        except TimeoutException: return False

    @staticmethod
    def _rotate_user_agent(driver):
        new_ua = random.choice(USER_AGENTS)
        try: driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": new_ua})
        except: pass

    @staticmethod
    def safe_get(
        driver,
        url: str,
        stop_check: Callable[[], bool] = None,
        on_request: Callable[[], None] = None,
        driver_manager=None,
        rotate_ua_for_avito: bool = True,
        ban_strategy=None,
    ) -> bool:
        max_retries = 2
        base_delay = 3  
        
        for attempt in range(max_retries + 1):
            if stop_check and stop_check():
                return False

            is_avito = "avito.ru" in url

            if (not is_avito) or (is_avito and rotate_ua_for_avito):
                PageLoader._rotate_user_agent(driver)

            if driver_manager and hasattr(driver_manager, 'rate_limit_delay'):
                driver_manager.rate_limit_delay(stop_check=stop_check)

            if on_request:
                on_request()

            try:
                logger.dev(f"GET Request (Att {attempt+1}): {url}")
                t_start = time.time()
                driver.get(url)

                title = driver.title.lower()

                if "доступ ограничен" in title or "проблема с ip" in title:
                    logger.warning("SOFT BAN DETECTED (Page Title)")

                    if ban_strategy:
                        success = ban_strategy.handle_soft_ban(stop_check)
                        if not success:
                            return False
                        raise WebDriverException("Soft Ban - Retry")
                    else:
                        time.sleep(20)
                        raise WebDriverException("Soft Ban")
                    
                if PageLoader.wait_for_load(driver, timeout=8):
                    logger.dev(f"Page loaded in {time.time() - t_start:.2f}s")
                    return True
            
            except WebDriverException as e:
                if "Soft Ban" in str(e):
                    continue

                logger.dev(f"Load Error: {e}", level="ERROR")
 
                if stop_check and stop_check():
                    return False    
                if attempt < max_retries:
                    delay = base_delay * (1.5 ** attempt) + random.uniform(1.0, 3.0)
                    step = 0.3
                    elapsed = 0.0   

                    logger.dev(f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})")

                    while elapsed < delay:
                        if stop_check and stop_check():
                            return False
                        time.sleep(step)
                        elapsed += step
                else:
                    return False    
        return False

    @staticmethod
    def scroll_page(driver, stop_check: Callable[[], bool] = None, max_attempts: int = 3):
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(max_attempts):
            if stop_check and stop_check(): return
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(0.8, 1.2))
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height: break
            last_height = new_height

# Class search for Avito categories and get optimal links for crawling
# Imitating a human
class SearchNavigator:
    def __init__(self, driver):
        self.driver = driver

    def _human_type(self, element, text):
        try:
            if not element.is_displayed():
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.2)
            
            self.driver.execute_script("arguments[0].focus();", element)
            element.click()
            element.clear()
            
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.02, 0.08))

                if random.random() < 0.1:
                    time.sleep(random.uniform(0.1, 0.2))
            return True
        except Exception as e:
            raise e

    def _type_query(self, keywords, fast_mode=False):
        if not fast_mode and ("avito.ru" not in self.driver.current_url):
            self.driver.get("https://www.avito.ru/moskva")
            time.sleep(2)

        search_input = None
        for selector in AvitoSelectors.SEARCH_INPUTS:
            try:
                search_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                if search_input.is_displayed(): break
            except: continue
            
        if not search_input:
            logger.warning("Поисковая строка не найдена")
            return None

        try:
            logger.info(f"Ввод запроса: {keywords}")
            self._human_type(search_input, keywords)
        except Exception as e:
            logger.dev(f"Input failed: {e}", level="ERROR")
            return None

        time.sleep(1.5)
        
        # Ждем выпадающий список
        dropdown = None
        try:
            dropdown = WebDriverWait(self.driver, 3).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, AvitoSelectors.DROPDOWN))
            )
        except: pass

        if not dropdown:
            search_input.send_keys(Keys.ENTER)
            return []

        # Парсим подсказки
        items = []
        try:
            found = dropdown.find_elements(By.CSS_SELECTOR, AvitoSelectors.DROPDOWN_ITEMS)
            items.extend(found)
        except: pass
        
        return items

    #?
    def _wait_for_dropdown(self):
        dropdown = None
        for selector in ['div[data-marker*="suggest"]', '[role="listbox"]']:
            try:
                dropdown = WebDriverWait(self.driver, 3).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                )
                if self.logger:
                    self.logger(f"Dropdown found...")
                break
            except:
                continue
        return dropdown

    #?
    def _extract_dropdown_items(self, dropdown):
        items = []
        for selector in ['[data-marker*="suggest/list/item"]', '[role="option"]']:
            try:
                found = dropdown.find_elements(By.CSS_SELECTOR, selector)
                if found:
                    items.extend(found)

                if self.logger and items:
                    count = len(items)
                    self.logger(f"Found {count} category entries in dropdown")
                    names = []
                    for it in items:
                        try:
                            t = it.text.replace("\n", " ").strip()
                            if t:
                                names.append(t)
                        except Exception:
                            pass
                    if names:
                        self.logger(f"Categories (raw): {', '.join(names)}")
            except:
                continue
        return items

    def get_search_suggestions(self, keywords: str) -> List[Dict[str, str]]:
        results = []
        try:
            items = self._type_query(keywords)
            if not items: return []
            
            seen = set()
            for item in items:
                try:
                    text = item.text.replace("\n", " ").strip()
                    if not text or text in seen: continue
                    seen.add(text)
                    
                    has_icon = len(item.find_elements(By.TAG_NAME, "img")) > 0
                    has_arrow = "←" in text or "→" in text
                    type_str = "ГЛАВНАЯ" if has_icon else ("СПЕЦИАЛЬНАЯ" if has_arrow else "ЗАПРОС")
                    
                    results.append({"text": text, "type": type_str})
                except: pass
        except Exception as e:
            logger.dev(f"Scan Error: {e}")
        return results
    
    def perform_smart_search(self, keywords: str, forced_filters: List[str] = None) -> List[str]:
        collected_urls = []
        try:
            logger.info(f"Умный поиск: '{keywords}'...", token="smart_search")
            
            items = self._type_query(keywords)
            if not items:
                logger.warning("Подсказки не появились. Использую Fallback.", token="smart_search")
                return []

            candidates = []
            seen_texts = set()

            for i, item in enumerate(items):
                try:
                    text = item.text.replace("\n", " ").strip()
                    if not text or text in seen_texts: continue
                    seen_texts.add(text)

                    has_icon = len(item.find_elements(By.TAG_NAME, "img")) > 0
                    
                    is_forced = False
                    if forced_filters:
                        for f in forced_filters:
                            if f.lower() in text.lower():
                                is_forced = True
                                break
                    
                    if (not forced_filters and has_icon) or is_forced:
                        candidates.append({'element': item, 'text': text})
                except: pass

            if not candidates:
                logger.info("Подходящих категорий в подсказках не найдено.", token="smart_search")
                return []

            indices_to_click = [c['index'] for c in candidates]
            
            target_candidate = candidates[0] # Берем лучшую
            logger.info(f"Выбор категории: {target_candidate['text']}", token="smart_search")
            
            try:
                # Попытка клика
                el = target_candidate['element']
                self.driver.execute_script("arguments[0].click();", el)
                PageLoader.wait_for_load(self.driver)
                
                time.sleep(2)
                current_url = self.driver.current_url
                logger.success(f"Переход успешен: {target_candidate['text']}")
                collected_urls.append(current_url)
                
            except Exception as e:
                logger.error(f"Ошибка перехода: {e}")

            return collected_urls

        except Exception as e:
            logger.error(f"Ошибка Smart Search: {e}")
            return []

    def _is_valid_url(self, url: str) -> bool:
        from urllib.parse import urlparse, parse_qs

        if not url or "avito.ru" not in url:
            return False

        trimmed = url.rstrip("/")
        if trimmed in ("https://www.avito.ru/moskva", "https://www.avito.ru/rossiya"):
            return False

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        if "q" in qs:
            return True

        if parsed.path.count("/") >= 3:
            return True
        
        return False

# Single ads-element parsing class
class ItemParser:
    @staticmethod
    def extract_ad_id(url: str) -> str:
        try: return url.split('?')[0].split('_')[-1]
        except: return ""
    
    @staticmethod
    def parse_search_item(soup_element, logger=None) -> Optional[Dict[str, Any]]:
        try:
            link_el = soup_element.select_one(AvitoSelectors.PREVIEW_TITLE)
            if not link_el: return None
            
            link = "https://www.avito.ru" + link_el.get('href') if link_el.get('href').startswith('/') else link_el.get('href')
            title = link_el.get_text(strip=True)
            ad_id = ItemParser.extract_ad_id(link)

            price = 0
            price_el = soup_element.select_one(AvitoSelectors.PREVIEW_PRICE)
            if price_el:
                raw_price = price_el.get_text(strip=True).replace('\xa0', '').replace(' ', '').replace('₽', '')
                match = re.search(r'(\d+)', raw_price)
                if match: price = int(match.group(1))

            description = ""
            for sel in AvitoSelectors.PREVIEW_DESC_VARIANTS:
                el = soup_element.select_one(sel)
                if el: 
                    description = el.get_text(strip=True)
                    break

            date_text = "неизвестно"
            del_el = soup_element.select_one(AvitoSelectors.PREVIEW_DATE)
            if del_el: date_text = del_el.get_text(strip=True)

            city = "неизвестно"
            geo = soup_element.select_one(AvitoSelectors.PREVIEW_GEO)
            if geo: city = re.split(r'[,·]', geo.get_text(strip=True))[0].strip()

            seller_id = ""
            sel_link = soup_element.select_one(AvitoSelectors.PREVIEW_SELLER_LINK)
            if sel_link:
                href = sel_link.get('href')
                m = re.search(r'/profile/(\w+)', href)
                if m: seller_id = m.group(1)

            return {
                'id': ad_id, 'link': link, 'price': price,
                'title': title, 'date_text': date_text,
                'description': description, 'city': city, 'condition': 'неизвестно',
                'seller_id': seller_id,
                'parsed_at': datetime.now().isoformat()
            }
        except Exception:
            return None

# Main class of the website parser
class AvitoParser(QObject):
    progress_value = pyqtSignal(int)
    update_requests_count = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, debug_mode: bool = False):
        super().__init__()
        self.driver_manager = DriverManager()
        self._stop_requested = False
        self._is_running = False
        self.debug_mode = debug_mode
        self.max_total_items = None
        self.deep_checks_done = 0

        self.ban_strategy = BanRecoveryStrategy(self.driver_manager)

    def __enter__(self): return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def request_stop(self):
        self._stop_requested = True
        logger.warning("Остановка поиска...")

    def is_stop_requested(self) -> bool: return self._stop_requested
    
    def get_dropdown_options(self, keywords: str) -> List[Dict[str, str]]:
        logger.info(f"Сканирование категорий: {keywords}")
        try:
            self.driver_manager._initialize_driver()
            #time.sleep(random.uniform(2, 4))
            navigator = SearchNavigator(self.driver_manager.driver)
            return navigator.get_search_suggestions(keywords)
        except Exception as e:
            logger.error(f"Ошибка сканирования: {e}")
            return []

    def _build_tasks(
        self,
        keywords,
        min_price,
        max_price,
        search_all_regions: bool,
        forced_categories: List[str] | None,
        sort_type: str,
    ) -> List[tuple[str, str]]:
        target_urls = []
        if isinstance(keywords, (list, tuple)): query_str = " ".join(keywords)
        else: query_str = str(keywords)

        navigator = SearchNavigator(self.driver_manager.driver)

        if forced_categories:
            logger.info("Открытие выбранных категорий...")
            smart_urls = navigator.perform_smart_search(query_str, forced_filters=forced_categories)
        else:
            logger.info("Умный поиск категорий...")
            smart_urls = navigator.perform_smart_search(query_str)

        if smart_urls:
            for url in smart_urls: target_urls.append((url, "Категория"))
        else:
            params = {"q": query_str}
            fallback = f"{BASE_URL_MOSCOW}?{urlencode(params)}"
            target_urls.append((fallback, "Поиск (Fallback)"))

        final_tasks: List[tuple[str, str]] = []
        unique_task_urls: set[str] = set()

        sort_map = {
            # По умолчанию (релевантность)
            "default": None, # 101
            # Дешевле
            "price_asc": "1",
            # Дороже
            "price_desc": "2",
            # По дате
            "date": "104",
            "discount": None, # TODO
        }
        sort_code = sort_map.get(sort_type)

        for raw_url, label in target_urls:
            try:
                if "avito.ru/moskva" in raw_url and len(raw_url) < 40 and "q=" not in raw_url:
                    continue

                parsed = urlparse(raw_url)
                qs = parse_qs(parsed.query)

                if min_price:
                    qs["pmin"] = [str(min_price)]
                if max_price:
                    qs["pmax"] = [str(max_price)]
                
                if sort_code is not None:
                    qs["s"] = [sort_code]

                path = parsed.path
                if search_all_regions:
                    if "/moskva/" in path:
                        path = path.replace("/moskva/", "/rossiya/")
                    elif "/sankt-peterburg/" in path:
                        path = path.replace("/sankt-peterburg/", "/rossiya/")
                    elif not path.startswith("/rossiya/"):
                        pass
                else:
                    if "/rossiya/" in path:
                        path = path.replace("/rossiya/", "/moskva/")

                new_qs = urlencode(qs, doseq=True)
                final_url = f"{parsed.scheme}://{parsed.netloc}{path}?{new_qs}"

                if final_url not in unique_task_urls:
                    unique_task_urls.add(final_url)
                    final_tasks.append((final_url, label))
            except Exception:
                if raw_url not in unique_task_urls:
                    unique_task_urls.add(raw_url)
                    final_tasks.append((raw_url, label))

        if not final_tasks:
            params = {"q": query_str}
            fb_url = f"{BASE_URL_MOSCOW}?{urlencode(params)}"
            if sort_code is not None:
                fb_url += f"&s={sort_code}"
            final_tasks.append((fb_url, "Emergency Global"))

        return final_tasks
    
    #def _run_tasks(
    #    self,
    #    final_tasks: List[tuple[str, str]],
    #    *,
    #    max_pages: int,
    #    max_items_per_page: int | None,
    #    max_total_items: int | None,
    #    search_mode: str,
    #    filter_defects: bool,
    #    ignore_keywords: List[str] | None,
    #    min_price=None,
    #    max_price=None,
    #    skip_duplicates: bool = False,
    #    allow_rewrite_duplicates: bool = False,
    #    existing_ids_base: Optional[Set[str]] = None,
    #) -> List[Dict[str, Any]]:
    #    all_results: List[Dict[str, Any]] = []
    #    seen_ids: set[str] = set()
    #    ignore_keywords = ignore_keywords or []
#
    #    for i, (url, label) in enumerate(final_tasks):
    #        if self.is_stop_requested():
    #            if self.debug_mode:
    #                self.log("Stop requested - returning collected results")
    #            break
    #        
    #        if self.max_total_items and self.deep_checks_done >= self.max_total_items:
    #            break
#
    #        if self.debug_mode:
    #            self.log(f"Processing Task {i+1}/{len(final_tasks)}: {label} -> {url}")
    #        self.update_progress.emit(f"Scanning: {label}...")
#
    #        self.process_region(
    #            url,
    #            max_pages,
    #            min_price,
    #            max_price,
    #            ignore_keywords,
    #            seen_ids,
    #            all_results,
    #            search_mode,
    #            max_items_per_page=max_items_per_page,
    #            max_total_items=max_total_items,
    #            filter_defects=filter_defects,
    #            skip_duplicates=skip_duplicates,
    #            allow_rewrite_duplicates=allow_rewrite_duplicates,
    #            existing_ids_base=existing_ids_base,
    #        )
#
    #    if self.debug_mode:
    #        self.log(f"--- FINISHED. Total Unique: {len(all_results)} ---")
    #    return all_results

    def _run_tasks(self, final_tasks, **kwargs) -> List[Dict[str, Any]]:
        all_results = []
        seen_ids = set()
        
        total_tasks = len(final_tasks)
        for i, (url, label) in enumerate(final_tasks):
            if self.is_stop_requested(): break
            
            logger.info(f"Задача {i+1}/{total_tasks}: {label}")
            
            self.process_region(url, seen_ids, all_results, **kwargs)

        return all_results

    #def search_items(
    #    self,
    #    keywords,
    #    ignore_keywords=None,
    #    *,
    #    max_pages: int = 10,
    #    max_items_per_page: int | None = None,
    #    max_total_items: int | None = None,
    #    min_price=None,
    #    max_price=None,
    #    sort_type="date",
    #    search_all_regions=False,
    #    search_mode="full",
    #    forced_categories: List[str] | None = None,
    #    filter_defects: bool = False,
    #    skip_duplicates: bool = False,
    #    allow_rewrite_duplicates: bool = False,
    #    merge_with_table: Optional[str] = None,
    #) -> List[Dict[str, Any]]:
    #    if self._is_running:
    #        return []
#
    #    self._is_running = True
    #    self._stop_requested = False
#
    #    if self.debug_mode:
    #        try:
    #            with open(self.log_file, "a", encoding="utf-8") as f:
    #                f.write(f"\n{'='*20} SESSION START: {datetime.now().isoformat()} {'='*20}\n")
    #        except:
    #            pass
#
    #    self.log(f"--- START: {keywords} (Mode: {search_mode}) ---")
    #    if forced_categories:
    #        self.log(f"Forced Categories: {forced_categories}")
#
    #    try:
    #        self.update_progress.emit("Initializing browser...")
    #        self.driver_manager._initialize_driver()
#
    #        final_tasks = self._build_tasks(
    #            keywords=keywords,
    #            min_price=min_price,
    #            max_price=max_price,
    #            search_all_regions=search_all_regions,
    #            forced_categories=forced_categories,
    #            sort_type=sort_type,
    #        )
#
    #        existing_ids_base: Set[str] = set()
    #        if merge_with_table:
    #            existing_ids_base = self._load_existing_ids_for_queue(merge_with_table) if merge_with_table else set()
    #            if self.debug_mode:
    #                self.log(f"Loaded {len(existing_ids_base)} base IDs from {merge_with_table}")
#
    #        self.max_total_items = max_total_items
    #        self.deep_checks_done = 0
#
    #        results = self._run_tasks(
    #        final_tasks,
    #        max_pages=max_pages,
    #        max_items_per_page=max_items_per_page,
    #        max_total_items=max_total_items,
    #        search_mode=search_mode,
    #        filter_defects=filter_defects,
    #        ignore_keywords=ignore_keywords or [],
    #        min_price=min_price,
    #        max_price=max_price,
    #        skip_duplicates=skip_duplicates,
    #        allow_rewrite_duplicates=allow_rewrite_duplicates,
    #        existing_ids_base=existing_ids_base,
    #    )
#
    #        return results
#
    #    except Exception as e:
    #        self.error_occurred.emit(str(e))
    #        self.log(f"CRITICAL ERROR: {e}")
    #        return []
    #    finally:
    #        self._is_running = False
    #        if self._stop_requested:
    #            self.log("Search stopped. Returning collected items gathered so far.")

    def search_items(self, keywords, **kwargs) -> List[Dict[str, Any]]:
        if self._is_running: return []
        self._is_running = True
        self._stop_requested = False

        logger.success(f"--- ЗАПУСК ПАРСЕРА: {keywords} ---")

        try:
            logger.progress("Инициализация браузера...", token="init")
            self.driver_manager._initialize_driver()
            
            final_tasks = self._build_tasks(keywords, kwargs.get('min_price'), kwargs.get('max_price'), kwargs.get('search_all_regions', False), kwargs.get('forced_categories'), kwargs.get('sort_type', 'date'))
            
            self.max_total_items = kwargs.get('max_total_items')
            self.deep_checks_done = 0

            results = self._run_tasks(final_tasks, **kwargs)
            return results

        except Exception as e:
            self.error_occurred.emit(str(e))
            logger.error(f"Критическая ошибка: {e}")
            return []
        finally:
            self._is_running = False

    #def process_region(
    #    self,
    #    base_url,
    #    max_pages,
    #    min_p,
    #    max_p,
    #    ignore_kws,
    #    seen_ids,
    #    results_list,
    #    search_mode,
    #    *,
    #    max_items_per_page: int | None = None,
    #    max_total_items: int | None = None,
    #    filter_defects: bool = False,
    #    skip_duplicates: bool = False,
    #    allow_rewrite_duplicates: bool = False,
    #    existing_ids_base: Optional[Set[str]] = None,
    #):
    #    is_deep_mode = (search_mode in ["full", "neuro"])
    #    ignore_kws = ignore_kws or []
#
    #    if max_pages and max_pages > 0:
    #        display_total = str(max_pages)
    #        page_limit = min(max_pages, ALL_PAGES_LIMIT)
    #    else:
    #        display_total = "ВСЕ"
    #        page_limit = ALL_PAGES_LIMIT
    #        if self.debug_mode:
    #            self.log(f"max_pages<=0, using ALL mode with safety limit: {ALL_PAGES_LIMIT}")
#
    #    page = 1
#
    #    blacklist_manager = get_blacklist_manager()
    #    blocked_seller_ids = blacklist_manager.get_active_seller_ids()
#
    #    if blocked_seller_ids and self.debug_mode:
    #        self.log(f"Blacklist active: {len(blocked_seller_ids)} sellers blocked")
#
    #    while True:
    #        if self.is_stop_requested():
    #            self.log(f"Stop requested at page {page}. Collected {len(results_list)} items.")
    #            break
#
    #        if max_total_items and len(results_list) >= max_total_items:
    #            return
#
    #        if page > page_limit:
    #            if self.debug_mode:
    #                self.log(f"Reached page limit {page_limit}, stopping region parsing.")
    #            break
#
    #        self.update_progress.emit(f"Searching page {page}/{display_total}...")
#
    #        url = f"{base_url}&p={page}" if "?" in base_url else f"{base_url}?p={page}"
#
    #        ok = PageLoader.safe_get(
    #            self.driver_manager.driver,
    #            url,
    #            self.is_stop_requested,
    #            logger=self.log if self.debug_mode else None,
    #            on_request=lambda: self.update_requests_count.emit(1, 0),
    #            driver_manager=self.driver_manager,
    #            ban_strategy=self.ban_strategy,
    #        )
#
    #        if not ok:
    #            page += 1
    #            continue
#
    #        PageLoader.scroll_page(self.driver_manager.driver, self.is_stop_requested, max_attempts=3)
    #        time.sleep(0.5)
    #        self._wait_for_items()
#
    #        page_items = self._parse_page()
    #        if not page_items:
    #            break
#
    #        total_items = len(page_items)
    #        items_on_page = 0
#
    #        for i, item in enumerate(page_items):
    #            if self.is_stop_requested():
    #                break
    #            if self.max_total_items and self.deep_checks_done >= self.max_total_items:
    #                return
#
    #            ad_id = str(item.get("id") or "").strip()
    #            
    #            if ad_id and existing_ids_base and ad_id in existing_ids_base:
    #                # Если найдено совпадение в базе
    #                if skip_duplicates and not allow_rewrite_duplicates:
    #                    # Если режим "Обновлять дубликаты" ВЫКЛЮЧЕН -> пропускаем полностью
    #                    if self.debug_mode:
    #                        self.log(f"Skipped base-table duplicate (fast): {ad_id}")
    #                    continue
    #                # Если режим ВКЛЮЧЕН -> идем дальше, парсим, обновляем
    #            # ====================================================
#
    #            if item["id"] in seen_ids:
    #                # Пропуск дубликатов внутри текущей сессии
    #                if self.debug_mode:
    #                    self.log(f"Skipped duplicate ID (session): {item['id']}")
    #                continue
    #            
    #            item_seller_id = item.get('seller_id', '')
    #            if item_seller_id and item_seller_id in blocked_seller_ids:
    #                if self.debug_mode:
    #                    self.log(f"BLOCKED by blacklist: seller_id={item_seller_id}, ad={item['id']}")
    #                continue
#
    #            if self._should_skip(item, min_p, max_p, ignore_kws, filter_defects):
    #                continue
#
    #            if search_mode == "primary":
    #                item["city"] = "неизвестно"
    #                item["condition"] = "неизвестно"
#
    #            elif is_deep_mode:
    #                if self.max_total_items and self.deep_checks_done >= self.max_total_items:
    #                    return
    #                
    #                self.deep_checks_done += 1
#
    #                self.update_requests_count.emit(1, 0)
    #                short_title = item["title"][:25] + "..." if len(item["title"]) > 25 else item["title"]
    #                
    #                if self.max_total_items:
    #                    num = self.deep_checks_done
    #                    denom = self.max_total_items
    #                else:
    #                    num = i + 1
    #                    denom = total_items
    #                
    #                self.update_progress.emit(f"Deep check {num}/{denom}: {short_title}")
#
    #                details = self._deep_dive_get_details(item["link"])
    #                if not details:
    #                    self.log(f"FILTERED (Tech): {item['id']}")
    #                    continue
#
    #                item.update(details)
#
    #            if item["id"] not in seen_ids:
    #                seen_ids.add(item["id"])
    #                results_list.append(item)
    #                items_on_page += 1
#
    #            if max_items_per_page and items_on_page >= max_items_per_page:
    #                break
#
    #        collected = len(results_list)
    #        if self.max_total_items:
    #            self.update_progress.emit(
    #                f"Collected {collected} items so far (deep checks {self.deep_checks_done}/{self.max_total_items})"
    #            )
    #        else:
    #            self.update_progress.emit(
    #                f"Collected {collected} items so far..."
    #            )
#
    #        if self.max_total_items and self.deep_checks_done >= self.max_total_items:
    #            return
#
    #        if not self._has_next_page(page):
    #            break
#
    #        page += 1

    def process_region(self, base_url, seen_ids, results_list, max_pages=10, max_items_per_page=None, max_total_items=None, search_mode="full", **kwargs):
        is_deep_mode = (search_mode in ["full", "neuro"])
        page_limit = min(max_pages, ALL_PAGES_LIMIT) if max_pages > 0 else ALL_PAGES_LIMIT
        page = 1

        while True:
            if self.is_stop_requested(): break
            if max_total_items and len(results_list) >= max_total_items: return
            if page > page_limit: break

            # Обновляем прогресс текстом
            logger.progress(f"Сканирование страницы {page}...", token="parser_page")
            
            # Обновляем прогресс бар (эвристика: если лимит 10 стр, то 1 стр = 10%)
            # Либо если есть max_total_items, считаем от него
            if max_total_items:
                pct = int((len(results_list) / max_total_items) * 100)
            else:
                pct = int((page / page_limit) * 100)
            self.progress_value.emit(min(pct, 99))

            url = f"{base_url}&p={page}" if "?" in base_url else f"{base_url}?p={page}"

            ok = PageLoader.safe_get(
                self.driver_manager.driver, url, self.is_stop_requested,
                on_request=lambda: self.update_requests_count.emit(1, 0),
                driver_manager=self.driver_manager,
                ban_strategy=self.ban_strategy
            )

            if not ok:
                page += 1
                continue

            PageLoader.scroll_page(self.driver_manager.driver, self.is_stop_requested)
            
            blacklist_manager = get_blacklist_manager()
            blocked_seller_ids = blacklist_manager.get_active_seller_ids()

            page_items = self._parse_page()
            if not page_items: break

            items_added_on_page = 0
            for i, item in enumerate(page_items):
                if self.is_stop_requested(): break
                if max_total_items and len(results_list) >= max_total_items: return

                if item["id"] in seen_ids: continue
                
                item_seller_id = item.get('seller_id', '')
                if item_seller_id and item_seller_id in blocked_seller_ids:
                    # TODO LOG
                    continue
                
                if is_deep_mode:
                    if max_total_items and self.deep_checks_done >= max_total_items: return
                    self.deep_checks_done += 1
                    
                    short = item["title"][:30]
                    # Обновляем статус глубокой проверки
                    logger.progress(f"Анализ товара: {short}", token="parser_deep")
                    
                    details = self._deep_dive_get_details(item["link"])
                    if details: item.update(details)
                
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    results_list.append(item)
                    items_added_on_page += 1
                    
                if max_items_per_page and items_added_on_page >= max_items_per_page: break

            # Если мы набрали товары, обновляем "галочкой" статус страницы
            if items_added_on_page > 0:
                logger.info(f"Стр {page}: +{items_added_on_page} товаров", token=f"page_done_{page}")

            if not self._has_next_page(page): break
            page += 1

    # TODO
    def _deep_dive_get_details(self, url):
        try:
            if self.is_stop_requested():
                return None

            ok = PageLoader.safe_get(
                self.driver_manager.driver,
                url,
                stop_check=self.is_stop_requested,
                driver_manager=self.driver_manager,
                ban_strategy=self.ban_strategy,
            )
            if not ok:
                return None

            wait = random.uniform(1.5, 2.5)
            step = 0.3
            elapsed = 0.0

            while elapsed < wait:
                if self.is_stop_requested():
                    return None
                time.sleep(step)
                elapsed += step

            if self.is_stop_requested():
                return None

            body_text = self.driver_manager.driver.execute_script(
                "return document.body.innerText;"
            ).lower()

            stop_phrases = [
                "снято с публикации",
                "товар зарезервирован",
                "это объявление закрыто",
                "товар купили",
                "покупатель уже забронировал",
                "товар в пути",
                "объявление не посмотреть",
            ]
            for phrase in stop_phrases:
                if phrase in body_text:
                    return None

            try:
                reserved_el = self.driver_manager.driver.find_elements(
                    By.XPATH, "//button//span[contains(text(), 'Забронировано')]"
                )
                if reserved_el:
                    return None
            except:
                pass

            details = {
                'description': '',
                'city': 'неизвестно',
                'condition': 'неизвестно',
                'date_text': 'неизвестно',
            }

            seller_id = ""
            try:
                # Ищем ссылку на профиль продавца
                seller_link = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR,
                    "a[data-marker='seller-info/label'], a[href*='/profile/']"
                )
                href = seller_link.get_attribute('href')
                if href:
                    match = re.search(r'/profile/(\w+)', href)
                    if match:
                        seller_id = match.group(1)
            except:
                pass
            
            if seller_id:
                details['seller_id'] = seller_id

            try:
                desc_el = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR,
                    "[data-marker='item-view/item-description']",
                )
                details['description'] = desc_el.text.strip()
            except:
                pass

            try:
                addr_container = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR,
                    "[itemprop='address']",
                )
                details['city'] = addr_container.text.strip().split(',')[0].strip()
            except:
                try:
                    addr_el = self.driver_manager.driver.find_element(
                        By.CSS_SELECTOR,
                        "[data-marker='delivery-item-address-text'], [class*='item-address-georeferences']",
                    )
                    details['city'] = addr_el.text.strip().split(',')[0].strip()
                except:
                    pass

            try:
                params_el = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR,
                    "[data-marker='item-view/item-params']",
                )
                for line in params_el.text.split('\n'):
                    if "Состояние" in line:
                        details['condition'] = (
                            line.replace("Состояние", "")
                                .replace(":", "")
                                .strip()
                        )
                        break
            except:
                pass

            try:
                date_el = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR,
                    "[data-marker='item-view/item-date']",
                )
                details['date_text'] = date_el.text.replace("· ", "").strip()
            except:
                pass

            return details

        except Exception as e:
            if self.debug_mode: #TODO LOG
                return None

    def _has_next_page(self, current_page: int) -> bool:
        try:
            btn = self.driver_manager.driver.find_elements(By.CSS_SELECTOR, AvitoSelectors.PAGINATION_NEXT)
            if btn: return AvitoSelectors.DISABLED_CLASS not in btn[0].get_attribute("class")
        except: pass
        return False

    #? - Это подразумевалось под _check_price()?
    def _should_skip(self, item, min_p, max_p, ignore_kws, filter_defects: bool = False):
        if min_p and item['price'] < min_p: return True
        if max_p and item['price'] > max_p: return True
        text_lower = f"{item['title'].lower()} {item.get('description', '').lower()}"
        
        for w in ignore_kws:
            if w.lower() in text_lower: return True

        if filter_defects:
            defect_markers = [
                "сломан", "разбит", "запчаст", "дефект", "не рабоч", 
                "не включ", "артефакт", "отвал", "восстановлен", 
                "под восстановление", "донор", "глючит", "проблемн"
            ]
            for dm in defect_markers:
                if dm in text_lower:
                    if f"без {dm}" in text_lower or f"нет {dm}" in text_lower:
                        continue
                    return True

        return False

    #? - Не трогать? Ее вызывает process_region()   
    def _parse_page(self) -> List[Dict[str, Any]]:
        items = []
        try:
            # BeautifulSoup парсинг
            source = self.driver_manager.driver.page_source
            soup = BeautifulSoup(source, 'lxml')
            elements = soup.select(AvitoSelectors.ITEM_CONTAINER)
            
            for el in elements:
                if self.is_stop_requested(): break
                # Игнорируем карусели
                if el.find_parent(class_=lambda x: x and 'carousel' in x.lower()): continue
                
                item = ItemParser.parse_search_item(el)
                if item: items.append(item)
        except Exception as e:
            logger.error(f"Ошибка парсинга страницы: {e}")
        return items

    def cleanup(self):
        self.driver_manager.cleanup()