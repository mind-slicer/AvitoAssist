import re
import time
import random
import json
import gzip
import os
from typing import Optional, Dict, Any, List, Callable, Set
from urllib.parse import urlencode, urlparse, parse_qs
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from PyQt6.QtCore import QObject, pyqtSignal

from app.core.driver import DriverManager
from app.config import USER_AGENTS, BASE_URL_MOSCOW, ALL_PAGES_LIMIT
from app.core.blacklist_manager import get_blacklist_manager


# Ban recovery mechanism
class BanRecoveryStrategy:
    def __init__(self, driver_manager, logger=None):
        self.driver_manager = driver_manager
        self.logger = logger
        self.ban_count = 0
        self.last_ban_time = None
    
    def handle_soft_ban(self, stop_check: Callable[[], bool] = None) -> bool:
        self.ban_count += 1
        current_time = time.time()
        
        if self.logger:
            self.logger(f"SOFT BAN #{self.ban_count} DETECTED")
        
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
        
        if self.logger:
            self.logger(f"Стратегия: {strategy} ({wait_time}с)")
        
        if self.ban_count >= 2:
            try:
                if self.logger:
                    self.logger("Сброс cookies...")
                self.driver_manager.driver.delete_all_cookies()
            except Exception as e:
                if self.logger:
                    self.logger(f"Cookie clear failed: {e}")
        
        if self.ban_count >= 3:
            try:
                if self.logger:
                    self.logger("Смена User-Agent...")
                new_ua = random.choice(USER_AGENTS)
                self.driver_manager.driver.execute_cdp_cmd(
                    'Network.setUserAgentOverride', 
                    {"userAgent": new_ua}
                )
            except Exception as e:
                if self.logger:
                    self.logger(f"UA change failed: {e}")
        
        step = 1
        elapsed = 0
        while elapsed < wait_time:
            if stop_check and stop_check():
                if self.logger:
                    self.logger("Ban recovery interrupted by stop request")
                return False
            
            remaining = wait_time - elapsed
            if self.logger and elapsed % 10 == 0:
                self.logger(f"Ожидание... осталось {remaining}с")
            
            time.sleep(step)
            elapsed += step
        
        if self.last_ban_time and (current_time - self.last_ban_time) < 300:
            if self.logger:
                self.logger("ПРЕДУПРЕЖДЕНИЕ: Частые баны! Рекомендуется остановка.")
        
        self.last_ban_time = current_time
        
        if self.logger:
            self.logger("Попытка продолжения...")
        
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
    def _rotate_user_agent(driver, logger=None):
        new_ua = random.choice(USER_AGENTS)
        if logger: logger(f"Rotating User-Agent to: {new_ua}")
        try: driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": new_ua})
        except: pass

    @staticmethod
    def safe_get(
        driver,
        url: str,
        stop_check: Callable[[], bool] = None,
        logger=None,
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
                PageLoader._rotate_user_agent(driver, logger)

            if driver_manager and hasattr(driver_manager, 'rate_limit_delay'):
                driver_manager.rate_limit_delay(stop_check=stop_check)

            if on_request:
                on_request()

            try:
                if logger:
                    logger(f"GET Request (Att {attempt+1}): {url}")
                t_start = time.time()
                driver.get(url)

                title = driver.title.lower()

                if "доступ ограничен" in title or "проблема с ip" in title:
                    if logger:
                        logger("SOFT BAN DETECTED")

                    if ban_strategy:
                        success = ban_strategy.handle_soft_ban(stop_check)
                        if not success:
                            return False
                        raise WebDriverException("Soft Ban - Retry")
                    else:
                        cooldown = 20
                        step = 1
                        elapsed = 0
                        while elapsed < cooldown:
                            if stop_check and stop_check():
                                if logger:
                                    logger("Soft ban cooldown interrupted")
                                return False
                            time.sleep(step)
                            elapsed += step
                        raise WebDriverException("Soft Ban")
                    
                if PageLoader.wait_for_load(driver, timeout=8):
                    if logger:
                        logger(f"Page loaded in {time.time() - t_start:.2f}s")
                    return True 
            
            except WebDriverException as e:
                if "Soft Ban" in str(e):
                    continue
                elif logger:
                    logger(f"Load Error: {e}")  
                if stop_check and stop_check():
                    return False    
                if attempt < max_retries:
                    delay = base_delay * (1.5 ** attempt) + random.uniform(1.0, 3.0)
                    step = 0.3
                    elapsed = 0.0   
                    if logger:
                        logger(f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})")   
                    while elapsed < delay:
                        if stop_check and stop_check():
                            if logger:
                                logger("Backoff interrupted by stop request")
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
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger

    def _human_type(self, element, text):
        try:
            if not element.is_displayed():
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.2)
            
            self.driver.execute_script("arguments[0].focus();", element)
            
            try:
                actions = ActionChains(self.driver)
                actions.move_to_element(element).click().perform()
            except:
                self.driver.execute_script("arguments[0].click();", element)
            
            time.sleep(0.2)
            
            try:
                element.send_keys(Keys.CONTROL + "a")
                element.send_keys(Keys.DELETE)
            except: 
                element.clear()
            
            time.sleep(0.1)
            
            for char in text:
                element.send_keys(char)
                base_delay = random.uniform(0.02, 0.08)
                variance = random.gauss(0, 0.01)
                delay = max(0.01, base_delay + variance)
                time.sleep(delay)

                if random.random() < 0.1:
                    time.sleep(random.uniform(0.15, 0.35))
            
            return True
        except Exception as e:
            raise e

    def _js_type(self, element, text):
        if self.logger: self.logger("Typing via JS fallback...")
        self.driver.execute_script("arguments[0].focus();", element)
        self.driver.execute_script("arguments[0].click();", element)
        self.driver.execute_script(f"arguments[0].value = '{text}';", element)
        self.driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", element)
        self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", element)
        time.sleep(0.5)

    def _type_query(self, keywords, fast_mode=False, retry=0):
        if not fast_mode and ("avito.ru" not in self.driver.current_url or len(self.driver.current_url) > 60):
            status = self._load_search_page(keywords)

            if status == "404" and retry == 0:
                if self.logger:
                    self.logger("Trying alternative URL...")
                self.driver.get("https://www.avito.ru/rossiya")
                time.sleep(3)
            elif status == "blocked":
                return None

        PageLoader.wait_for_load(self.driver, timeout=10)
        time.sleep(2.0)

        search_input = self._find_search_input()

        if not search_input:
            if self.logger:
                self.logger("Search input not found")

            if retry < 1:
                if self.logger:
                    self.logger(f"Retrying (attempt {retry + 1})...")
                self.driver.quit()
                self.driver = None
                time.sleep(2)
                return None
            return None

        try:
            self._human_type(search_input, keywords)
        except:
            try:
                self._js_type(search_input, keywords)
            except Exception as e:
                if self.logger:
                    self.logger(f"Input failed: {e}")
                return None

        time.sleep(1.5)

        dropdown = self._wait_for_dropdown()

        if not dropdown:
            if self.logger:
                self.logger("No dropdown, submitting...")
            try:
                search_input.send_keys(Keys.ENTER)
            except:
                pass
            return []

        return self._extract_dropdown_items(dropdown)

    def _find_search_input(self):
        search_input = None
        strategies = [
            ('input[placeholder*="Поиск"]', "placeholder"),
            ('input[name="q"]', "name=q"),
            ('input[data-marker*="search"]', "data-marker"),
            ('//header//input[@type="text"]', "header xpath")
        ]

        for selector, name in strategies:
            try:
                if selector.startswith('//'):
                    search_input = self.driver.find_element(By.XPATH, selector)
                else:
                    search_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                break
            except:
                continue
            
        if not search_input:
            all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
            if self.logger:
                self.logger(f"Total inputs: {len(all_inputs)}")
            for inp in all_inputs:
                try:
                    if inp.is_displayed() and inp.size['width'] > 100:
                        search_input = inp
                        if self.logger:
                            self.logger("Found fallback input")
                        break
                except:
                    continue
                
        return search_input

    def _load_search_page(self, keywords):
        if self.logger:
            self.logger("Loading search page...")

        try:
            self.driver.execute_cdp_cmd('Network.clearBrowserCache', {})
            self.driver.delete_all_cookies()
        except Exception as e:
            if self.logger:
                self.logger(f"Cache clear failed: {e}")

        params = {"q": keywords}
        search_url = f"https://www.avito.ru/moskva?{urlencode(params)}"
        self.driver.get(search_url)
        time.sleep(3)

        return self._check_page_status()

    def _check_page_status(self):
        title = self.driver.title.lower()

        if "404" in title or "не найдена" in title or "не существует" in title:
            if self.logger:
                self.logger("!!! 404 PAGE - Invalid URL !!!")
            return "404"

        if any(phrase in title for phrase in ["доступ ограничен", "проблема с ip", "captcha"]):
            if self.logger:
                self.logger("IP BLOCKED")
            return "blocked"

        return "ok"

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
                    type_str = "ГЛАВНАЯ" if has_icon else ("ОБЩАЯ" if has_arrow else "ЗАПРОС")
                    
                    results.append({"text": text, "type": type_str})
                except: pass
        except Exception as e:
            if self.logger: self.logger(f"Scan Exception: {e}")
        return results
    
    def perform_smart_search(self, keywords: str, forced_filters: List[str] = None) -> List[str]:
        collected_urls = []
        try:            
            items = self._type_query(keywords)
            if not items:
                if self.logger: self.logger("No dropdown items. Using fallback.")
                return []
            
            candidates = []
            seen_texts = set()
            
            for i, item in enumerate(items):
                try:
                    text = item.text.replace("\n", " ").strip()
                    if not text or text in seen_texts: 
                        continue
                    seen_texts.add(text)
                    
                    has_icon = len(item.find_elements(By.TAG_NAME, "img")) > 0
                    has_arrow = "←" in text or "→" in text
                    item_type = "CATEGORY" if has_icon else ("GENERAL" if has_arrow else "QUERY")
                    href = item.get_attribute("href") or ""
                    
                    candidates.append({
                        'index': i,
                        'text': text,
                        'type': item_type,
                        'is_main': has_icon,
                        'href': href
                    })
                except:
                    pass
            
            if not candidates:
                return []
            
            indices_to_click: List[int] = []
            
            if forced_filters:
                if self.logger: self.logger(f"Using FORCED filters: {forced_filters}")
                for c in candidates:
                    if c['text'] in forced_filters:
                        indices_to_click.append(c['index'])
            
            if not forced_filters or not indices_to_click:
                main = None
                for c in candidates:
                    if c['type'] == "CATEGORY" or c['is_main']:
                        main = c
                        break
                if main is None and candidates:
                    main = candidates[0]
                indices_to_click = [main['index']] if main is not None else []
            
            if self.logger: 
                names = [candidates[i]['text'] for i in indices_to_click if i < len(candidates)]
                self.logger(f"Targets: {names}")
            
            for idx, target_index in enumerate(indices_to_click):
                try:
                    if idx > 0:
                        items = self._type_query(keywords, fast_mode=True)
                    
                    if not items or len(items) <= target_index: 
                        continue
                    
                    target = items[target_index]
                    
                    href = target.get_attribute("href")
                    if href and "avito.ru" in href:
                        if self.logger: self.logger(f"Direct link -> {href}")
                        self.driver.get(href)
                        PageLoader.wait_for_load(self.driver)
                    else:
                        try: 
                            txt = target.text.replace("\n", " ")
                            if self.logger: self.logger(f"Clicking -> {txt}")
                        except:
                            pass

                        try:
                            ActionChains(self.driver).move_to_element(target).click().perform()
                        except:
                            self.driver.execute_script("arguments[0].click();", target)
                        
                        PageLoader.wait_for_load(self.driver)

                    time.sleep(2.0)
                    
                    url = self.driver.current_url

                    if self.logger:
                        self.logger(f"Selected category URL: {url}")
                    
                    if self._is_valid_url(url):
                        collected_urls.append(url)
                    else:
                        if self.logger:
                            self.logger("Selected URL did not pass _is_valid_url() check, will fallback later.")
                    
                    if idx < len(indices_to_click) - 1:
                        self.driver.back()
                        PageLoader.wait_for_load(self.driver)
                        time.sleep(1.0)
                
                except Exception as e:
                    if self.logger: self.logger(f"Click error: {e}")
            
            return collected_urls
            
        except Exception as e:
            if self.logger: self.logger(f"Smart Search Critical: {e}")
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
    def parse_search_item(element, logger=None) -> Optional[Dict[str, Any]]:
        try:
            try:
                link_element = element.find_element(By.CSS_SELECTOR, '[data-marker="item-title"]')
                link = link_element.get_attribute('href')
            except NoSuchElementException: return None
            if not link: return None
            title = link_element.text.strip()
            if not title: return None
            ad_id = ItemParser.extract_ad_id(link)
            price = 0
            try:
                price_text = element.find_element(By.CSS_SELECTOR, '[data-marker="item-price"]').text.replace(' ', '').replace('\u2009', '').replace('\xa0', '')
                match = re.search(r'(\d+)', price_text)
                if match: price = int(match.group(1))
            except: pass
            
            description = ""
            try:
                desc_el = element.find_element(By.CSS_SELECTOR, "div[class*='iva-item-bottomBlock'] p[class*='styles-module-root']")
                description = desc_el.text.strip()
                if logger and description:
                    logger(f"Description (bottomBlock): {len(description)} chars")
            except:
                pass
            
            if not description:
                try:
                    desc_el = element.find_element(By.CSS_SELECTOR, "div[class*='bottomBlock'] p[class*='styles-module']")
                    description = desc_el.text.strip()
                    if logger and description:
                        logger(f"Description (bottomBlock alt): {len(description)} chars")
                except:
                    pass

            date_text = "неизвестно"
            try:
                date_el = element.find_element(By.CSS_SELECTOR, '[data-marker="item-date"]')
                date_text = date_el.text.strip()
            except: pass

            city = "неизвестно"
            try:
                geo_el = element.find_element(By.CSS_SELECTOR, "div[class*='geo-root']")
                raw_geo = geo_el.text.strip()
                city = re.split(r'[,·]', raw_geo)[0].strip()
            except: pass

            seller_id = ""
            try:
                # Пробуем найти ссылку на профиль продавца
                seller_link = element.find_element(By.CSS_SELECTOR, 
                    "a[data-marker='seller-link/link'], a[href*='/profile/']")
                href = seller_link.get_attribute('href')
                if href:
                    # Извлекаем ID из URL (например: /profile/12345678/)
                    match = re.search(r'/profile/(\w+)', href)
                    if match:
                        seller_id = match.group(1)
            except:
                pass

            return {
                'id': ad_id, 'link': link, 'price': price,
                'title': title, 'date_text': date_text,
                'description': description, 'city': city, 'condition': 'неизвестно',
                'seller_id': seller_id,
                'parsed_at': datetime.now().isoformat()
            }
        except Exception as e:
            if logger: logger(f"Item Parse Error: {e}")
            return None

# Main class of the website parser
class AvitoParser(QObject):
    update_progress = pyqtSignal(str)
    update_requests_count = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, debug_mode: bool = False):
        super().__init__()
        self.driver_manager = DriverManager()
        self._stop_requested = False
        self._is_running = False
        self.debug_mode = debug_mode
        self.log_file = "debug_parser.log"
        self.max_total_items = None
        self.deep_checks_done = 0

        self.ban_strategy = BanRecoveryStrategy(
            self.driver_manager, 
            logger=self.log if self.debug_mode else None
        )

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def log(self, msg):
        if self.debug_mode:
            ts = datetime.now().strftime('%H:%M:%S')
            full_msg = f"[{ts}] {msg}"
            print(f"[PARSER] {full_msg}")
            try:
                with open(self.log_file, "a", encoding="utf-8") as f: f.write(full_msg + "\n")
            except: pass

    def request_stop(self):
        self._stop_requested = True
        self.update_progress.emit("Stopping search...")
        self.log("Stop requested by user")

    def is_stop_requested(self) -> bool: return self._stop_requested
    
    def get_dropdown_options(self, keywords: str) -> List[Dict[str, str]]:
        self.log(f"Scanning categories for: {keywords}")
        try:
            self.driver_manager._initialize_driver()
            time.sleep(random.uniform(2, 4))
            navigator = SearchNavigator(self.driver_manager.driver, self.log if self.debug_mode else None)
            return navigator.get_search_suggestions(keywords)
        except Exception as e:
            self.log(f"Scan Error: {e}")
            return []
        finally:
            pass
    
    def _build_tasks(
        self,
        keywords,
        min_price,
        max_price,
        search_all_regions: bool,
        forced_categories: List[str] | None,
        sort_type: str,
    ) -> List[tuple[str, str]]:
        target_urls: List[tuple[str, str]] = []

        if isinstance(keywords, (list, tuple)):
            query_str = " ".join(keywords)
        else:
            query_str = str(keywords)

        navigator = SearchNavigator(
            self.driver_manager.driver,
            self.log if self.debug_mode else None,
        )

        if forced_categories:
            self.update_progress.emit("Opening selected categories...")
            smart_urls = navigator.perform_smart_search(
                query_str,
                forced_filters=forced_categories,
            )
        else:
            self.update_progress.emit("Smart Search: Auto-detecting categories...")
            smart_urls = navigator.perform_smart_search(query_str)

        if smart_urls:
            for url in smart_urls:
                target_urls.append((url, "Smart Category"))
        else:
            if self.debug_mode:
                self.log("Smart search yielded no URLs. Using FALLBACK.")
            params = {"q": query_str}
            fallback_url = f"{BASE_URL_MOSCOW}?{urlencode(params)}"
            target_urls.append((fallback_url, "Global Search (Fallback)"))

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
            # По размеру скидки — код нужно будет уточнить, временно ставим как дефолт
            "discount": None,
        }
        sort_code = sort_map.get(sort_type)

        for raw_url, label in target_urls:
            try:
                if "avito.ru/moskva" in raw_url and len(raw_url) < 40 and "q=" not in raw_url:
                    if self.debug_mode:
                        self.log(f"Skipping suspicious URL: {raw_url}")
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
            if self.debug_mode:
                self.log("No valid tasks. Using Emergency Fallback.")
            params = {"q": query_str}
            fb_url = f"{BASE_URL_MOSCOW}?{urlencode(params)}"
            if sort_code is not None:
                fb_url += f"&s={sort_code}"
            final_tasks.append((fb_url, "Emergency Global"))

        return final_tasks
    
    def _run_tasks(
        self,
        final_tasks: List[tuple[str, str]],
        *,
        max_pages: int,
        max_items_per_page: int | None,
        max_total_items: int | None,
        search_mode: str,
        filter_defects: bool,
        ignore_keywords: List[str] | None,
        min_price=None,
        max_price=None,
        skip_duplicates: bool = False,
        allow_rewrite_duplicates: bool = False,
        existing_ids_base: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        all_results: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        ignore_keywords = ignore_keywords or []

        for i, (url, label) in enumerate(final_tasks):
            if self.is_stop_requested():
                if self.debug_mode:
                    self.log("Stop requested - returning collected results")
                break
            
            if self.max_total_items and self.deep_checks_done >= self.max_total_items:
                break

            if self.debug_mode:
                self.log(f"Processing Task {i+1}/{len(final_tasks)}: {label} -> {url}")
            self.update_progress.emit(f"Scanning: {label}...")

            self.process_region(
                url,
                max_pages,
                min_price,
                max_price,
                ignore_keywords,
                seen_ids,
                all_results,
                search_mode,
                max_items_per_page=max_items_per_page,
                max_total_items=max_total_items,
                filter_defects=filter_defects,
                skip_duplicates=skip_duplicates,
                allow_rewrite_duplicates=allow_rewrite_duplicates,
                existing_ids_base=existing_ids_base,
            )

        if self.debug_mode:
            self.log(f"--- FINISHED. Total Unique: {len(all_results)} ---")
        return all_results

    def search_items(
        self,
        keywords,
        ignore_keywords=None,
        *,
        max_pages: int = 10,
        max_items_per_page: int | None = None,
        max_total_items: int | None = None,
        min_price=None,
        max_price=None,
        sort_type="date",
        search_all_regions=False,
        search_mode="full",
        forced_categories: List[str] | None = None,
        filter_defects: bool = False,
        skip_duplicates: bool = False,
        allow_rewrite_duplicates: bool = False,
        merge_with_table: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if self._is_running:
            return []

        self._is_running = True
        self._stop_requested = False

        if self.debug_mode:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(f"\n{'='*20} SESSION START: {datetime.now().isoformat()} {'='*20}\n")
            except:
                pass

        self.log(f"--- START: {keywords} (Mode: {search_mode}) ---")
        if forced_categories:
            self.log(f"Forced Categories: {forced_categories}")

        try:
            self.update_progress.emit("Initializing browser...")
            self.driver_manager._initialize_driver()

            final_tasks = self._build_tasks(
                keywords=keywords,
                min_price=min_price,
                max_price=max_price,
                search_all_regions=search_all_regions,
                forced_categories=forced_categories,
                sort_type=sort_type,
            )

            existing_ids_base: Set[str] = set()
            if merge_with_table:
                existing_ids_base = self._load_existing_ids_for_queue(merge_with_table) if merge_with_table else set()
                if self.debug_mode:
                    self.log(f"Loaded {len(existing_ids_base)} base IDs from {merge_with_table}")

            self.max_total_items = max_total_items
            self.deep_checks_done = 0

            results = self._run_tasks(
            final_tasks,
            max_pages=max_pages,
            max_items_per_page=max_items_per_page,
            max_total_items=max_total_items,
            search_mode=search_mode,
            filter_defects=filter_defects,
            ignore_keywords=ignore_keywords or [],
            min_price=min_price,
            max_price=max_price,
            skip_duplicates=skip_duplicates,
            allow_rewrite_duplicates=allow_rewrite_duplicates,
            existing_ids_base=existing_ids_base,
        )

            return results

        except Exception as e:
            self.error_occurred.emit(str(e))
            self.log(f"CRITICAL ERROR: {e}")
            return []
        finally:
            self._is_running = False
            if self._stop_requested:
                self.log("Search stopped. Returning collected items gathered so far.")

    def process_region(
        self,
        base_url,
        max_pages,
        min_p,
        max_p,
        ignore_kws,
        seen_ids,
        results_list,
        search_mode,
        *,
        max_items_per_page: int | None = None,
        max_total_items: int | None = None,
        filter_defects: bool = False,
        skip_duplicates: bool = False,
        allow_rewrite_duplicates: bool = False,
        existing_ids_base: Optional[Set[str]] = None,
    ):
        is_deep_mode = (search_mode in ["full", "neuro"])
        ignore_kws = ignore_kws or []

        if max_pages and max_pages > 0:
            display_total = str(max_pages)
            page_limit = min(max_pages, ALL_PAGES_LIMIT)
        else:
            display_total = "ВСЕ"
            page_limit = ALL_PAGES_LIMIT
            if self.debug_mode:
                self.log(f"max_pages<=0, using ALL mode with safety limit: {ALL_PAGES_LIMIT}")

        page = 1

        blacklist_manager = get_blacklist_manager()
        blocked_seller_ids = blacklist_manager.get_active_seller_ids()

        if blocked_seller_ids and self.debug_mode:
            self.log(f"Blacklist active: {len(blocked_seller_ids)} sellers blocked")

        while True:
            if self.is_stop_requested():
                self.log(f"Stop requested at page {page}. Collected {len(results_list)} items.")
                break

            if max_total_items and len(results_list) >= max_total_items:
                return

            if page > page_limit:
                if self.debug_mode:
                    self.log(f"Reached page limit {page_limit}, stopping region parsing.")
                break

            self.update_progress.emit(f"Searching page {page}/{display_total}...")

            url = f"{base_url}&p={page}" if "?" in base_url else f"{base_url}?p={page}"

            ok = PageLoader.safe_get(
                self.driver_manager.driver,
                url,
                self.is_stop_requested,
                logger=self.log if self.debug_mode else None,
                on_request=lambda: self.update_requests_count.emit(1, 0),
                driver_manager=self.driver_manager,
                ban_strategy=self.ban_strategy,
            )

            if not ok:
                page += 1
                continue

            PageLoader.scroll_page(self.driver_manager.driver, self.is_stop_requested, max_attempts=3)
            time.sleep(0.5)
            self._wait_for_items()

            page_items = self._parse_page()
            if not page_items:
                break

            total_items = len(page_items)
            items_on_page = 0

            for i, item in enumerate(page_items):
                if self.is_stop_requested():
                    break
                if self.max_total_items and self.deep_checks_done >= self.max_total_items:
                    return

                ad_id = str(item.get("id") or "").strip()
                
                if ad_id and existing_ids_base and ad_id in existing_ids_base:
                    # Если найдено совпадение в базе
                    if skip_duplicates and not allow_rewrite_duplicates:
                        # Если режим "Обновлять дубликаты" ВЫКЛЮЧЕН -> пропускаем полностью
                        if self.debug_mode:
                            self.log(f"Skipped base-table duplicate (fast): {ad_id}")
                        continue
                    # Если режим ВКЛЮЧЕН -> идем дальше, парсим, обновляем
                # ====================================================

                if item["id"] in seen_ids:
                    # Пропуск дубликатов внутри текущей сессии
                    if self.debug_mode:
                        self.log(f"Skipped duplicate ID (session): {item['id']}")
                    continue
                
                item_seller_id = item.get('seller_id', '')
                if item_seller_id and item_seller_id in blocked_seller_ids:
                    if self.debug_mode:
                        self.log(f"BLOCKED by blacklist: seller_id={item_seller_id}, ad={item['id']}")
                    continue

                if self._should_skip(item, min_p, max_p, ignore_kws, filter_defects):
                    continue

                if search_mode == "primary":
                    item["city"] = "неизвестно"
                    item["condition"] = "неизвестно"

                elif is_deep_mode:
                    if self.max_total_items and self.deep_checks_done >= self.max_total_items:
                        return
                    
                    self.deep_checks_done += 1

                    self.update_requests_count.emit(1, 0)
                    short_title = item["title"][:25] + "..." if len(item["title"]) > 25 else item["title"]
                    
                    if self.max_total_items:
                        num = self.deep_checks_done
                        denom = self.max_total_items
                    else:
                        num = i + 1
                        denom = total_items
                    
                    self.update_progress.emit(f"Deep check {num}/{denom}: {short_title}")

                    details = self._deep_dive_get_details(item["link"])
                    if not details:
                        self.log(f"FILTERED (Tech): {item['id']}")
                        continue

                    item.update(details)

                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    results_list.append(item)
                    items_on_page += 1

                if max_items_per_page and items_on_page >= max_items_per_page:
                    break

            collected = len(results_list)
            if self.max_total_items:
                self.update_progress.emit(
                    f"Collected {collected} items so far (deep checks {self.deep_checks_done}/{self.max_total_items})"
                )
            else:
                self.update_progress.emit(
                    f"Collected {collected} items so far..."
                )

            if self.max_total_items and self.deep_checks_done >= self.max_total_items:
                return

            if not self._has_next_page(page):
                break

            page += 1

    def _deep_dive_get_details(self, url):
        try:
            if self.is_stop_requested():
                return None

            ok = PageLoader.safe_get(
                self.driver_manager.driver,
                url,
                stop_check=self.is_stop_requested,
                logger=self.log if self.debug_mode else None,
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
            if self.debug_mode:
                self.log(f"DeepDive Error: {e}")
            return None

    def _has_next_page(self, current_page: int) -> bool:
        try:
            next_btn = self.driver_manager.driver.find_elements(By.CSS_SELECTOR, '[data-marker="pagination-button/nextPage"]')
            if next_btn: return "styles-module-root_disabled" not in next_btn[0].get_attribute("class")
            return False
        except: return False

    def _wait_for_items(self):
        try: WebDriverWait(self.driver_manager.driver, 4).until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-marker="item"]')))
        except: pass

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
            
    def _parse_page(self) -> List[Dict[str, Any]]:
        items = []
        try:
            item_elements = self.driver_manager.driver.find_elements(By.CSS_SELECTOR, '[data-marker="item"]')
            for element in item_elements:
                if self.is_stop_requested(): break
                try:
                    parent = element.find_element(By.XPATH, "./..")
                    if "carousel" in parent.get_attribute("class").lower(): continue
                except: pass
                item = ItemParser.parse_search_item(element, self.log if self.debug_mode else None)
                if item: items.append(item)
        except: pass
        return items
    
    @staticmethod
    def _load_existing_ids_for_queue(merge_with_table: Optional[str]) -> Set[str]:
        """
        ФАЗА 5.1: загрузить множество ID объявлений из merge-таблицы.
        Если таблица не выбрана или не читается — возвращаем пустое множество.
        """
        existing_ids: Set[str] = set()

        if not merge_with_table:
            return existing_ids

        filepath = merge_with_table
        if not os.path.exists(filepath):
            return existing_ids

        try:
            # Сначала пробуем обычный JSON
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                # Фолбэк — gzip JSON
                with gzip.open(filepath, "rt", encoding="utf-8") as f:
                    data = json.load(f)

            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        aid = item.get("id")
                        if aid:
                            existing_ids.add(str(aid))
        except Exception as e:
            # тихий fallback, чтобы не ломать парсер
            print(f"[WARN] Failed to load existing ids for merge table {filepath}: {e}")

        return existing_ids

    def cleanup(self):
        self.driver_manager.cleanup()