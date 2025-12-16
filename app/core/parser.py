import re
import time
import random
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any, List, Callable
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


# --- Ban Recovery Mechanism ---
class BanRecoveryStrategy:
    def __init__(self, driver_manager):
        self.driver_manager = driver_manager
        self.ban_count = 0
        self.last_ban_time = None
        self.max_wait_time = 300
     
    def handle_soft_ban(self, stop_check: Optional[Callable[[], bool]] = None) -> bool:
        self.ban_count += 1
        current_time = time.time()
        
        logger.warning(f"SOFT BAN #{self.ban_count} DETECTED")
        
        wait_time = min(30 * (2 ** (self.ban_count - 1)), self.max_wait_time)
        
        if self.ban_count == 1:
            strategy = "Быстрое восстановление"
        elif self.ban_count == 2:
            strategy = "Сброс cookies + ожидание"
        elif self.ban_count == 3:
            strategy = "Полный сброс + долгое ожидание"
        else:
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
                logger.info("Восстановление прервано пользователем")
                return False
            
            remaining = wait_time - elapsed
            if elapsed % 10 == 0 or elapsed >= wait_time - 5:
                logger.progress(f"Ожидание снятия бана... {int(remaining)}с", token="ban_timer")
            
            time.sleep(step)
            elapsed += step
        
        if self.last_ban_time and (current_time - self.last_ban_time) < 300:
            logger.warning("ПРЕДУПРЕЖДЕНИЕ: Частые баны! Рекомендуется увеличить паузы.")
        
        logger.success("Ожидание завершено, пробуем продолжить...", token="ban_timer")
        self.last_ban_time = current_time
        return True


# --- Page Loader ---
class PageLoader:
    @staticmethod
    def wait_for_load(driver, timeout: int = 5) -> bool:
        try:
            WebDriverWait(driver, timeout).until(lambda d: d.execute_script("return document.readyState") in ["interactive", "complete"])
            return True
        except TimeoutException: return False
    
    @staticmethod
    def safe_get(
        driver,
        url: str,
        stop_check: Optional[Callable[[], bool]] = None,
        on_request: Optional[Callable[[], None]] = None,
        driver_manager=None,
        rotate_ua_for_avito: bool = False,
        ban_strategy=None,
    ) -> bool:
        max_retries = 3
        base_delay = 2
        
        speed_mult = driver_manager.speed_multiplier if driver_manager else 1.0
        
        for attempt in range(max_retries + 1):
            if stop_check and stop_check():
                return False
        
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
                    #logger.warning("SOFT BAN DETECTED (Page Title)")
        
                    if ban_strategy:
                        success = ban_strategy.handle_soft_ban(stop_check)
                        if not success:
                            return False
                        raise WebDriverException("Soft Ban - Retry")
                    else:
                        time.sleep(20)
                        raise WebDriverException("Soft Ban")
                     
                load_timeout = int(10 * speed_mult)
                if PageLoader.wait_for_load(driver, timeout=load_timeout):
                    logger.dev(f"Page loaded in {time.time() - t_start:.2f}s")
                    return True
            
            except WebDriverException as e:
                if "Soft Ban" in str(e):
                    continue
                 
                if "timed out receiving message from renderer" in str(e).lower():
                    logger.dev("Renderer timeout (ignored due to eager strategy)")
                    return True
        
                logger.dev(f"Load Error: {e}", level="ERROR")
                logger.error(f"WebDriver Error: {e}")
        
                if stop_check and stop_check():
                    return False
                if attempt < max_retries:
                    # Экспоненциальный бэкофф с джиттером
                    calculated_delay = (base_delay * (2 ** attempt) + random.uniform(0.5, 2.0)) * speed_mult
                    step = 0.3
                    elapsed = 0.0
        
                    logger.dev(f"Retrying in {calculated_delay:.1f}s (attempt {attempt + 1}/{max_retries})")
        
                    while elapsed < calculated_delay:
                        if stop_check and stop_check():
                            return False
                        time.sleep(step)
                        elapsed += step
                else:
                    return False
        return False
    
    @staticmethod
    def scroll_page(driver, stop_check: Optional[Callable[[], bool]] = None, max_attempts: int = 3):
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(max_attempts):
            if stop_check and stop_check(): return
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(0.8, 1.2))
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height: break
            last_height = new_height


# --- Search Navigator ---
class SearchNavigator:
    def __init__(self, driver):
        self.driver = driver
    
    def _human_type(self, element, text):
        from app.config import (
            HUMAN_TYPING_MIN_DELAY,
            HUMAN_TYPING_MAX_DELAY,
            HUMAN_TYPING_PAUSE_CHANCE,
            HUMAN_TYPING_PAUSE_DURATION
        )
        
        try:
            if not element.is_displayed():
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(random.uniform(0.3, 0.6))
        
            self.driver.execute_script("arguments[0].focus();", element)
            time.sleep(random.uniform(0.1, 0.2))
            element.click()
            time.sleep(random.uniform(0.2, 0.4))
            element.clear()
            time.sleep(random.uniform(0.1, 0.3))
        
            for i, char in enumerate(text):
                element.send_keys(char)
        
                delay = random.uniform(HUMAN_TYPING_MIN_DELAY, HUMAN_TYPING_MAX_DELAY)
        
                if random.random() < HUMAN_TYPING_PAUSE_CHANCE:
                    pause_min, pause_max = HUMAN_TYPING_PAUSE_DURATION
                    delay += random.uniform(pause_min, pause_max)
        
                if char == ' ':
                    delay *= random.uniform(1.2, 1.5)
        
                time.sleep(delay)
        
            return True
        except Exception as e:
            raise e
    
    def _type_query(self, keywords, fast_mode=False):
        current_url = self.driver.current_url
        need_navigation = False
        
        if "avito.ru" not in current_url:
            need_navigation = True
        elif any(keyword in current_url for keyword in ["/catalog", "/audio", "/noutbuki", "/planshety", "/kompyutery", "/bytovaya"]):
            need_navigation = True
        else:
            try:
                test_input = self.driver.find_element(By.CSS_SELECTOR, AvitoSelectors.SEARCH_INPUTS[0])
                if not test_input.is_displayed():
                    need_navigation = True
            except:
                need_navigation = True
        
        if need_navigation:
            logger.dev("Сброс навигации на главную (Москва)...")
            if not PageLoader.safe_get(self.driver, "https://www.avito.ru/moskva"):
                logger.warning("Не удалось загрузить главную страницу")
                return None
            time.sleep(0.5 if fast_mode else 2)
        
        search_input = None
        for i, selector in enumerate(AvitoSelectors.SEARCH_INPUTS):
            try:
                search_input = WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if search_input.is_displayed():
                    break
                search_input = None
            except Exception:
                continue
             
        if not search_input:
            logger.warning("Поисковая строка не найдена...")
            return None
        
        try:
            if not fast_mode:
                logger.info(f"Ввод запроса: {keywords}")
        
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_input)
            time.sleep(0.3)
        
            if fast_mode:
                search_input.click()
                search_input.clear()
                search_input.send_keys(keywords)
            else:
                self._human_type(search_input, keywords)
        except Exception as e:
            logger.dev(f"Input failed: {e}", level="ERROR")
            return None
        
        time.sleep(2.0)
        
        dropdown = None
        try:
            dropdown = WebDriverWait(self.driver, 8).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, AvitoSelectors.DROPDOWN))
            )
            logger.dev("Категории не появились")
        except TimeoutException:
            logger.dev("Категории не появились за 8 секунд.", level="WARNING")
            return None
        except Exception as e:
            logger.dev(f"Dropdown error: {e}", level="WARNING")
            return None
        
        items = []
        try:
            dropdown_items = WebDriverWait(self.driver, 3).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, AvitoSelectors.DROPDOWN_ITEMS)
            )
            items.extend(dropdown_items)
        except: pass
        
        return items if items else None
    
    def _is_valid_url(self, url: str) -> bool:
        if not url or "avito.ru" not in url: return False
        url_clean = url.split('#')[0].rstrip('/')
        if not url_clean: return False
        
        trimmed = url_clean.rstrip("/")
        invalid_pages = [
            "https://www.avito.ru/moskva",
            "https://www.avito.ru/rossiya",
            "https://www.avito.ru",
            "https://avito.ru"
        ]
        
        if trimmed in invalid_pages: return False
        
        parsed = urlparse(url_clean) 
        qs = parse_qs(parsed.query)
        path = parsed.path
        
        if "q" in qs and qs["q"][0].strip(): return True
        
        path_segments = path.count("/")
        if path_segments >= 3: return True
        
        return False
    
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
                    
                    href = item.get_attribute("href") or ""
                 
                    results.append({
                        "text": text, 
                        "type": type_str,
                        "href": href
                    })
                except: pass
        except Exception as e:
            logger.dev(f"Scan Error: {e}")
        return results
     
    def perform_smart_search(self, keywords: str, forced_filters: Optional[List[str]] = None) -> List[str]:
        collected_urls = []
        try:
            logger.info(f"Умный поиск: '{keywords}'...", token="smart_search")
        
            items = self._type_query(keywords)
            if not items:
                logger.warning("Меню категорий не открылось...")
                logger.success("Поиск завершен (запасной режим)...", token="smart_search")
                return []
        
            candidates = []
            seen_texts = set()
        
            def normalize(s): return str(s).replace('\xa0', ' ').replace('\n', ' ').strip().lower()
        
            for i, item in enumerate(items):
                try:
                    text = item.text.replace("\n", " ").strip()
                    if not text: continue
                    if text not in seen_texts: seen_texts.add(text)
        
                    has_icon = len(item.find_elements(By.TAG_NAME, "img")) > 0
                    has_arrow = "←" in text or "→" in text
                    item_type = "CATEGORY" if has_icon else ("GENERAL" if has_arrow else "QUERY")
                    href = item.get_attribute("href") or ""
        
                    candidates.append({
                        'index': i, 'text': text, 'type': item_type,
                        'is_main': has_icon, 'href': href, 'element': item
                    })
                except: pass
        
            if not candidates: return []
            target_texts = []
             
            if forced_filters:
                logger.info(f"Ищем выбранные категории ({len(forced_filters)} шт)...")
                for f in forced_filters:
                    f_norm = normalize(f)
                    matched = None
                    for c in candidates:
                        if f_norm == normalize(c['text']): matched = c; break
                    if not matched:
                        for c in candidates:
                            if f_norm in normalize(c['text']): matched = c; break
                    if matched and matched['text'] not in target_texts:
                        target_texts.append(matched['text'])
             
            if not target_texts and not forced_filters:
                logger.dev(f"Кандидаты: {[c['text'] for c in candidates]}")
                best_candidate = None
                keywords_norm = normalize(keywords)
                valid_candidates = [c for c in candidates if "ваканси" not in normalize(c['text'])]

                for c in valid_candidates:
                    if keywords_norm in normalize(c['text']): best_candidate = c; break
                if not best_candidate:
                    for c in valid_candidates:
                        if c['is_main'] and c['type'] == "CATEGORY": best_candidate = c; break
                if not best_candidate:
                    for c in valid_candidates:
                        if c['type'] == "QUERY": best_candidate = c; break
                if not best_candidate and valid_candidates:
                    best_candidate = valid_candidates[0]
        
                if best_candidate: target_texts = [best_candidate['text']]
        
            if not target_texts: 
                logger.warning("Не выбрано ни одной категории для перехода...")
                return []
        
            for idx, target_text in enumerate(target_texts):
                try:
                    logger.info(f"Переход {idx+1}/{len(target_texts)}: {target_text}...")
                     
                    cached = next((c for c in candidates if c['text'] == target_text), None)
                    if cached and cached.get('href') and self._is_valid_url(cached['href']):
                        try:
                            self.driver.get(cached['href'])
                            PageLoader.wait_for_load(self.driver, timeout=10)
                            time.sleep(1.5)
                            if self._is_valid_url(self.driver.current_url):
                                collected_urls.append(self.driver.current_url)
                                continue 
                        except: pass
        
                    target = None
                    if idx == 0 and cached: target = cached
                    else:
                        items = self._type_query(keywords, fast_mode=True)
                        if items:
                            for item in items:
                                if item.text.replace("\n", " ").strip() == target_text:
                                    target = {'text': target_text, 'element': item, 'index': 0}
                                    break
                     
                    if not target: continue
        
                    try:
                        self.driver.execute_script("arguments[0].click();", target['element'])
                        time.sleep(1.5)
                        waited = 0
                        while waited < 8:
                            time.sleep(0.5)
                            waited += 0.5
                            if self._is_valid_url(self.driver.current_url) and self.driver.current_url not in collected_urls:
                                collected_urls.append(self.driver.current_url)
                                break
                    except: pass
                except Exception as e:
                    logger.error(f"Сбой перехода '{target_text}'...: {e}")
                    continue
                 
            logger.success("Категории найдены...", token="smart_search")
            return collected_urls
        
        except Exception as e:
            logger.error(f"Ошибка умного поиска: {e}...", token="smart_search")
            return []

# --- Item Parser ---
class ItemParser:
    _parse_cache = {}
    
    @staticmethod
    def extract_ad_id(url: str) -> str:
        try:
            ad_id = url.split('?')[0].split('_')[-1]
            if not ad_id: return url.split('/')[-1]
            return ad_id
        except:
            return ""
     
    @staticmethod
    def parse_search_item(soup_element, logger=None) -> Optional[Dict[str, Any]]:
        try:
            element_id = str(soup_element)
            if element_id in ItemParser._parse_cache:
                return ItemParser._parse_cache[element_id]
            
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
                if href:
                    parts = [p for p in href.split('/') if p and p not in ['profile', 'user', 'brands', 'companies']]
                    if parts:
                        seller_id = parts[-1].split('?')[0]
            
            condition = "Б/У"
            t_lower = title.lower() if title else ""
            if any(x in t_lower for x in ["новый", "новая", "новое", "new", "запечатан", "не вскрывал"]):
                condition = "Новое"
            elif any(x in t_lower for x in ["запчаст", "разбор", "дефект", "сломан", "не рабоч", "под восстановление"]):
                condition = "На запчасти"

            views = 0
        
            result = {
                'id': ad_id, 'link': link, 'price': price,
                'title': title, 'date_text': date_text,
                'description': description, 'city': city, 'condition': 'неизвестно',
                'condition': condition,
                'seller_id': seller_id,
                'views': views,
                'parsed_at': datetime.now().isoformat()
            }
            
            ItemParser._parse_cache[element_id] = result
            return result
        except Exception:
            return None


# --- Main Avito Parser Class ---
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
        self._request_count = 0
        self._success_count = 0
        self.ban_strategy = BanRecoveryStrategy(self.driver_manager)
        self._initialize_parser()
    
    def _initialize_parser(self):
        try:
            if not self.driver_manager:
                self.driver_manager = DriverManager()
            if not self.ban_strategy:
                self.ban_strategy = BanRecoveryStrategy(self.driver_manager)
        except Exception as e:
            logger.error(f"Ошибка инициализации парсера: {e}...")
            raise
    
    def __enter__(self): return self
     
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False
    
    def request_stop(self):
        self._stop_requested = True
        logger.warning("Остановка поиска...")
    
    def is_stop_requested(self) -> bool: return self._stop_requested
     
    def get_dropdown_options(self, keywords: str) -> List[Dict[str, str]]:
        logger.info(f"Сканирование категорий: '{keywords}'...")
        try:
            self.driver_manager._initialize_driver()
            navigator = SearchNavigator(self.driver_manager.driver)
            return navigator.get_search_suggestions(keywords)
        except Exception as e:
            logger.error(f"Ошибка сканирования: {e}...")
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
         
        category_urls = []
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
            for url in smart_urls: category_urls.append((url, "Категория"))
        else:
            params = {"q": query_str}
            fallback = f"{BASE_URL_MOSCOW}?{urlencode(params)}"
            category_urls.append((fallback, "Поиск"))
        
        final_tasks: List[tuple[str, str]] = []
        unique_check: set[str] = set()
         
        sort_map = {
            "default": "101", 
            "price_asc": "1",
            "price_desc": "2",
            "date": "104",
            "discount": "172297_desc",
        }
        sort_code = sort_map.get(sort_type, "101")
        
        for raw_url, cat_label in category_urls:
            try:
                parsed = urlparse(raw_url)
                qs = parse_qs(parsed.query)
                if min_price: qs["pmin"] = [str(min_price)]
                if max_price: qs["pmax"] = [str(max_price)]
                if sort_code: qs["s"] = [sort_code]
                 
                qs_encoded = urlencode(qs, doseq=True)
                 
                # --- ЗАДАЧА 1: ЛОКАЛЬНО (Москва) ---
                url_local = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{qs_encoded}"
                if url_local not in unique_check:
                    unique_check.add(url_local)
                    final_tasks.append((url_local, f"{cat_label} (Москва)"))
        
                # --- ЗАДАЧА 2: ВСЕ РЕГИОНЫ (Если включено) ---
                if search_all_regions:
                    path_str = parsed.path
                    if "/moskva/" in path_str:
                        new_path = path_str.replace("/moskva/", "/rossiya/", 1)
                    else:
                        new_path = "/rossiya" + path_str if path_str.startswith("/") else "/rossiya/" + path_str
                     
                    url_global = f"{parsed.scheme}://{parsed.netloc}{new_path}?{qs_encoded}"
                     
                    if url_global not in unique_check:
                        unique_check.add(url_global)
                        final_tasks.append((url_global, f"{cat_label} (РФ)"))
        
            except Exception as e:
                logger.error(f"Ошибка задач для {raw_url}: {e}")
                final_tasks.append((raw_url, cat_label))
        
        return final_tasks
    
    def run_tasks(self, final_tasks, **kwargs) -> List[Dict[str, Any]]:
        all_results = []
        seen_ids = set()
         
        existing_ids_base = kwargs.get('existing_ids_base', set())
        if existing_ids_base:
            seen_ids.update(existing_ids_base)
            logger.info(f"Загружено {len(existing_ids_base)} исключений (ранее найденные товары)...")
         
        total_tasks = len(final_tasks)
        max_limit_per_task = self.max_total_items
         
        grand_total_expected = (max_limit_per_task * total_tasks) if max_limit_per_task else 0
         
        kwargs_filtered = {
            k: v for k, v in kwargs.items() 
            if k not in ['max_total_items', 'existing_ids_base']
        }
         
        for i, (url, label) in enumerate(final_tasks):
            if self.is_stop_requested(): break
            
            if max_limit_per_task:
                current_task_target_ceiling = len(all_results) + max_limit_per_task
            else:
                current_task_target_ceiling = None
        
            logger.info(f"Задача {i+1}/{total_tasks}: {label}...")
             
            self.process_region(
                base_url=url,
                seen_ids=seen_ids,
                results_list=all_results,
                existing_ids_base=existing_ids_base,
                max_total_items=current_task_target_ceiling,
                total_expected_items=grand_total_expected,
                current_task_index=i,
                total_tasks=total_tasks,
                **kwargs_filtered
            )
             
        return all_results
    
    def search_items(self, keywords, ignore_keywords=None, **kwargs) -> List[Dict[str, Any]]:
        if self._is_running: return []
        self._is_running = True
        self._stop_requested = False
        self.progress_value.emit(0)
        
        logger.success(f"--- ЗАПУСК: {keywords} ---")
        
        try:
            logger.progress("Браузер...", token="init")
            self.driver_manager._initialize_driver()
            self.driver_manager.set_speed_multiplier(1.0)
            logger.success("Браузер готов к работе...", token="init")
        
            if self.is_stop_requested(): return []
        
            final_tasks = self._build_tasks(
                keywords, 
                kwargs.get('min_price'), 
                kwargs.get('max_price'), 
                kwargs.get('search_all_regions', False), 
                kwargs.get('forced_categories'), 
                kwargs.get('sort_type', 'date')
            )
             
            if self.is_stop_requested(): return []
        
            search_mode = kwargs.get('search_mode', 'full')
            self.driver_manager.set_speed_multiplier(0.7 if search_mode in ["full", "neuro"] else 1.0)
        
            self.max_total_items = kwargs.get('max_total_items')
            kwargs['ignore_keywords'] = ignore_keywords or []
        
            results = self.run_tasks(final_tasks, **kwargs)
            return results
        
        except Exception as e:
            self.error_occurred.emit(str(e))
            logger.error(f"Error: {e}")
            return []
        finally:
            self._is_running = False
            if self.driver_manager: self.driver_manager.set_speed_multiplier(1.0)
            logger.info("Готово...")
    
    def process_region(
        self, 
        base_url, 
        seen_ids, 
        results_list, 
        existing_ids_base=None, 
        max_pages=100, 
        max_items_per_page=None, 
        max_total_items=None, 
        search_mode="full", 
        ignore_keywords=None, 
        min_price=None, 
        max_price=None, 
        filter_defects=False, 
        skip_duplicates=False, 
        allow_rewrite_duplicates=False, 
        total_expected_items=None, 
        current_task_index=0, 
        total_tasks=1, 
        **kwargs
    ):
        is_deep_mode = (search_mode in ["full", "neuro"])
        page_limit = min(max_pages, ALL_PAGES_LIMIT) if max_pages and max_pages > 0 else ALL_PAGES_LIMIT
        page = 1
        ignore_keywords = ignore_keywords or []
        blacklist_manager = get_blacklist_manager()
        consecutive_deep_errors = 0
        
        while True:
            if self.is_stop_requested(): break
            blocked_seller_ids = blacklist_manager.get_active_seller_ids()
        
            current_progress = 0
            items_collected_total = len(results_list)
        
            if total_expected_items and total_expected_items > 0:
                current_progress = int((items_collected_total / total_expected_items) * 100)
            else:
                current_progress = int((page / page_limit) * 100)
             
            self.progress_value.emit(min(100, current_progress))
        
            if max_total_items and items_collected_total >= max_total_items:
                logger.info(f"Лимит задачи достигнут ({items_collected_total}/{max_total_items})...")
                break
        
            if page > page_limit: break
        
            logger.progress(f"Сканирование страницы {page}...", token="parser_page")
            url = f"{base_url}&p={page}" if "?" in base_url else f"{base_url}?p={page}"
        
            ok = PageLoader.safe_get(
                self.driver_manager.driver,
                url,
                self.is_stop_requested,
                on_request=lambda: self.update_requests_count.emit(1, 0),
                driver_manager=self.driver_manager,
                ban_strategy=self.ban_strategy
            )
        
            if not ok:
                if self.is_stop_requested(): break
                page += 1
                continue
        
            PageLoader.scroll_page(self.driver_manager.driver, self.is_stop_requested)
            has_next = self._has_next_page(page)
            page_items = self._parse_page()
             
            if not page_items:
                logger.info("Товары на странице не найдены (конец списка)...")
                break
        
            items_added_on_page = 0
             
            for item in page_items:
                if self.is_stop_requested(): break
                if max_total_items and len(results_list) >= max_total_items:
                    return
        
                ad_id = str(item.get("id") or "").strip()
                if ad_id in seen_ids:
                    continue
                if ad_id and existing_ids_base and ad_id in existing_ids_base:
                    if skip_duplicates and not allow_rewrite_duplicates:
                        continue
                 
                raw_seller_id = str(item.get('seller_id', ''))
                if raw_seller_id and raw_seller_id.lower() in blocked_seller_ids:
                    continue
                 
                if self._should_skip(item, min_price, max_price, ignore_keywords, filter_defects):
                    continue
                 
                if is_deep_mode:
                    if consecutive_deep_errors >= 3:
                        pass
                    else:
                        short_title = item["title"][:30]
                        logger.progress(f"Сканируем: {short_title}...", token="parser_deep")
                         
                        self.update_requests_count.emit(1, 0)
                        details = self._deep_dive_get_details(item["link"])
                        if details:
                            consecutive_deep_errors = 0
                            item.update(details)
                            real_seller_id = str(item.get('seller_id', ''))
                            if real_seller_id and real_seller_id.lower() in blocked_seller_ids:
                                logger.info(f"Пропущен продавец из ЧС: {real_seller_id}...")
                                continue
                        else:
                            consecutive_deep_errors += 1
                            continue 
        
                if item['id'] not in seen_ids:
                    seen_ids.add(item['id'])
                    results_list.append(item)
                    items_added_on_page += 1
        
                    if total_expected_items and total_expected_items > 0:
                        total_done = len(results_list)
                        p = min(100, int((total_done / total_expected_items) * 100))
                        self.progress_value.emit(p)
                     
                if max_items_per_page and items_added_on_page >= max_items_per_page: 
                    break
                     
            logger.success(f"Страница {page}: +{items_added_on_page} товаров...", token="parser_page")
            if is_deep_mode and items_added_on_page > 0:
                logger.success("Обработка товаров завершена...", token="parser_deep")
        
            if not has_next: 
                logger.info("Следующая страница не найдена (конец пагинации)...")
                break
             
            page += 1
    
    def _deep_dive_get_details(self, url):
        try:
            if self.is_stop_requested(): return None
        
            ok = PageLoader.safe_get(
                self.driver_manager.driver,
                url,
                stop_check=self.is_stop_requested,
                driver_manager=self.driver_manager,
                ban_strategy=self.ban_strategy,
            )
             
            if not ok: 
                return None
        
            wait = random.uniform(1.2, 2.0)
            time.sleep(wait)
             
            if self.is_stop_requested(): return None
             
            if self.driver_manager and self.driver_manager.driver:
                body_text = self.driver_manager.driver.execute_script(
                    "return document.body.innerText;"
                ).lower()
            else:
                return None
        
            stop_phrases = [
                "снято с публикации",
                "товар зарезервирован",
                "это объявление закрыто",
                "товар купили",
                "покупатель уже забронировал",
                "товар в пути",
                "объявление не посмотреть",
                "срок размещения объявления истек"
            ]
             
            for phrase in stop_phrases:
                if phrase in body_text:
                    return None
        
            # 2. Инициализация структуры
            details = {
                'description': '',
                'city': 'неизвестно',
                'condition': 'неизвестно',
                'date_text': 'неизвестно',
                'views': 0,
                'seller_id': '',
                'price': 0
            }
        
            driver = self.driver_manager.driver if self.driver_manager else None
            if not driver:
                return None
        
            try:
                price_meta = driver.find_element(By.CSS_SELECTOR, "[itemprop='price']")
                price_val = price_meta.get_attribute("content")
                if price_val:
                    details['price'] = int(price_val)
                else:
                    text_price = price_meta.text.replace('\xa0', '').replace(' ', '').replace('₽', '')
                    details['price'] = int(text_price)
            except:
                try:
                    price_el = driver.find_element(By.CSS_SELECTOR, "[data-marker='item-view/item-price']")
                    text_price = price_el.text.replace('\xa0', '').replace(' ', '').replace('₽', '')
                    details['price'] = int(text_price)
                except: pass
        
            try:
                seller_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/user/'], a[href*='/companies/'], a[href*='/brands/']")
                for link in seller_links:
                    href = link.get_attribute('href')
                    if href:
                        match = re.search(r'/(?:user|companies|brands)/([^/]+)', href)
                        if match:
                            details['seller_id'] = match.group(1).split('?')[0]
                            break
            except: pass
        
            try:
                desc_el = driver.find_element(By.CSS_SELECTOR, "[data-marker='item-view/item-description']")
                details['description'] = desc_el.text.strip()
            except: pass
        
            try:
                addr_container = driver.find_element(By.CSS_SELECTOR, "[itemprop='address']")
                details['city'] = addr_container.text.strip().split(',')[0].strip()
            except:
                try:
                    addr_el = driver.find_element(By.CSS_SELECTOR, "[data-marker='delivery-item-address-text']")
                    details['city'] = addr_el.text.strip().split(',')[0].strip()
                except: pass
        
            try:
                params_el = driver.find_element(By.CSS_SELECTOR, "[data-marker='item-view/item-params']")
                for line in params_el.text.split('\n'):
                    if "Состояние" in line:
                        raw_cond = line.replace("Состояние", "").replace(":", "").strip()
                        if raw_cond.lower() in ["б/у", "б/y", "старое"]:
                            details['condition'] = "Б/У"
                        else:
                            details['condition'] = raw_cond.capitalize()
                        break
            except: pass
        
            try:
                date_el = driver.find_element(By.CSS_SELECTOR, "[data-marker='item-view/item-date']")
                details['date_text'] = date_el.text.replace("· ", "").strip()
            except: pass
        
            try:
                views_el = driver.find_element(By.CSS_SELECTOR, "[data-marker='item-view/total-views']")
                txt = views_el.text
                m = re.search(r'(\d+)', txt.replace(' ', ''))
                if m: details['views'] = int(m.group(1))
            except:
                try:
                    src = driver.page_source
                    m = re.search(r'(\d+)\s+просмотр', src)
                    if m: details['views'] = int(m.group(1))
                except: pass
        
            return details
        
        except Exception as e:
            return None
    
    def _has_next_page(self, current_page: int) -> bool:
        try:
            if self.driver_manager and self.driver_manager.driver:
                btn = self.driver_manager.driver.find_elements(By.CSS_SELECTOR, AvitoSelectors.PAGINATION_NEXT)
                if btn and btn[0]:
                    btn_class = btn[0].get_attribute("class")
                    if btn_class:
                        return AvitoSelectors.DISABLED_CLASS not in btn_class
        except: pass
        return False
    
    def _should_skip(self, item, min_p, max_p, ignore_kws, filter_defects: bool = False):
        price = item.get('price', 0)
        if min_p and price < min_p: return True
        if max_p and price > max_p: return True
         
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

    def _parse_page(self) -> List[Dict[str, Any]]:
        items = []
        try:
            if self.driver_manager and self.driver_manager.driver:
                source = self.driver_manager.driver.page_source
                soup = BeautifulSoup(source, 'lxml')
                elements = soup.select(AvitoSelectors.ITEM_CONTAINER)
                
                for el in elements:
                    if self.is_stop_requested(): break
                    
                    # --- НАЧАЛО: Улучшенная фильтрация каруселей и рекомендаций ---
                    is_carousel = False
                    
                    # Проверяем самого элемента и его родителей (до 6 уровней вверх достаточно)
                    # Авито часто кладет рекомендации в контейнеры с data-marker="recommendations..."
                    for parent in el.parents:
                        if parent.name == 'body': 
                            break
                        
                        # Получаем атрибуты
                        p_classes = parent.get('class', [])
                        # Превращаем список классов в строку для поиска
                        p_class_str = " ".join(p_classes).lower() if p_classes else ""
                        p_marker = parent.get('data-marker', '').lower()

                        # Стоп-слова, указывающие на рекомендательные блоки
                        stop_words = ['carousel', 'recommend', 'similar', 'suggest', 'slider']
                        
                        # 1. Проверка классов
                        if any(sw in p_class_str for sw in stop_words):
                            is_carousel = True
                            break
                        
                        # 2. Проверка маркеров
                        if any(sw in p_marker for sw in stop_words):
                            is_carousel = True
                            break
                            
                    if is_carousel:
                        try:
                            # Пытаемся выцепить заголовок для лога, чтобы понимать, что мы скипнули
                            title_el = el.select_one(AvitoSelectors.PREVIEW_TITLE)
                            t_text = title_el.get_text(strip=True)[:30] if title_el else "Unknown"
                            # Используем dev логгер, чтобы не засорять UI пользователя, но видеть в debug.log
                            logger.info(f"Исключено из карусели/рекомендаций: {t_text}...")
                        except:
                            pass
                        continue
                    # --- КОНЕЦ: Улучшенная фильтрация ---

                    item = ItemParser.parse_search_item(el)
                    if item: items.append(item)
                    
        except Exception as e:
            logger.error(f"Ошибка парсинга страницы: {e}...")
        return items
    
    def cleanup(self):
        try:
            if self.driver_manager:
                self.driver_manager.cleanup()
            ItemParser._parse_cache.clear()
            logger.info("Ресурсы парсера очищены...")
        except Exception as e:
            logger.error(f"Ошибка при очистке парсера: {e}...")