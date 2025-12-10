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
        stop_check: Callable[[], bool] = None,
        on_request: Callable[[], None] = None,
        driver_manager=None,
        rotate_ua_for_avito: bool = False,
        ban_strategy=None,
    ) -> bool:
        max_retries = 2
        base_delay = 3  
        
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
                    logger.warning("SOFT BAN DETECTED (Page Title)")

                    if ban_strategy:
                        success = ban_strategy.handle_soft_ban(stop_check)
                        if not success:
                            return False
                        raise WebDriverException("Soft Ban - Retry")
                    else:
                        time.sleep(20)
                        raise WebDriverException("Soft Ban")
                    
                if PageLoader.wait_for_load(driver, timeout=10):
                    logger.dev(f"Page loaded in {time.time() - t_start:.2f}s")
                    return True
            
            except WebDriverException as e:
                if "Soft Ban" in str(e):
                    continue
                
                if "timed out receiving message from renderer" in str(e).lower():
                    logger.dev("Renderer timeout (ignored due to eager strategy)")
                    return True

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

        # Проверка необходимости навигации
        if "avito.ru" not in current_url:
            need_navigation = True
            logger.dev("Текущий URL не Авито, требуется переход...")
        elif any(keyword in current_url for keyword in ["/catalog", "/audio", "/noutbuki", "/planshety", "/kompyutery", "/bytovaya"]):
            need_navigation = True
            logger.dev(f"Текущий URL - страница категории ({current_url}), требуется переход...")
        else:
            try:
                test_input = self.driver.find_element(By.CSS_SELECTOR, AvitoSelectors.SEARCH_INPUTS[0])
                if not test_input.is_displayed():
                    need_navigation = True
                    logger.dev("Поисковая строка не видима, требуется переход...")
            except:
                need_navigation = True
                logger.dev("Поисковая строка не найдена, требуется переход...")

        # ИСПРАВЛЕНИЕ: Всегда переходим, если нужно
        if need_navigation:
            logger.dev("Переход на главную страницу Авито...")
            if not PageLoader.safe_get(self.driver, "https://www.avito.ru/moskva"):
                logger.warning("Не удалось загрузить главную страницу")
                return None
            time.sleep(0.5 if fast_mode else 2)

        # ИСПРАВЛЕНИЕ: Более надежный поиск элемента
        search_input = None
        for i, selector in enumerate(AvitoSelectors.SEARCH_INPUTS):
            try:
                search_input = WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if search_input.is_displayed():
                    logger.dev(f"Найдена поисковая строка (selector #{i+1}): {selector}")
                    break
                search_input = None
            except Exception as e:
                logger.dev(f"Селектор #{i+1} не сработал: {selector}")
                continue
            
        if not search_input:
            logger.warning("Поисковая строка не найдена после всех попыток...")
            logger.dev(f"Текущий URL: {self.driver.current_url}")
            logger.dev(f"Заголовок страницы: {self.driver.title}")
            return None

        # Ввод текста
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

        # ИСПРАВЛЕНИЕ: Лучшая обработка dropdown
        dropdown = None
        try:
            dropdown = WebDriverWait(self.driver, 8).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, AvitoSelectors.DROPDOWN))
            )
            logger.dev("✓ Dropdown появился")
        except TimeoutException:
            logger.dev("✗ Dropdown не появился за 8 секунд", level="WARNING")
            return None  # ИСПРАВЛЕНИЕ: Возвращаем None
        except Exception as e:
            logger.dev(f"✗ Dropdown error: {e}", level="WARNING")
            return None  # ИСПРАВЛЕНИЕ: Возвращаем None

        # Сбор элементов
        items = []
        try:
            found = dropdown.find_elements(By.CSS_SELECTOR, AvitoSelectors.DROPDOWN_ITEMS)
            items.extend(found)
            logger.dev(f"✓ Найдено {len(items)} элементов в dropdown")
        except Exception as e:
            logger.dev(f"✗ Ошибка сбора элементов: {e}")

        return items if items else None  # ИСПРАВЛЕНИЕ: Возвращаем None если пусто

    def _is_valid_url(self, url: str) -> bool:
        if not url or "avito.ru" not in url:
            logger.dev(f"URL validation FAIL: not avito.ru")
            return False

        url_clean = url.split('#')[0].rstrip('/')

        if not url_clean or url_clean in [
            "https://www.avito.ru",
            "https://avito.ru",
            "https://www.avito.ru/moskva",
            "https://www.avito.ru/rossiya"
        ]:
            logger.dev(f"URL validation FAIL: main page after anchor removal")
            return False

        trimmed = url_clean.rstrip("/")

        # Проверка на главные страницы (не подходят для парсинга)
        invalid_pages = [
            "https://www.avito.ru/moskva",
            "https://www.avito.ru/rossiya",
            "https://www.avito.ru",
            "https://avito.ru"
        ]

        if trimmed in invalid_pages:
            logger.dev(f"URL validation FAIL: main page")
            return False

        parsed = urlparse(url_clean) 
        qs = parse_qs(parsed.query)
        path = parsed.path

        if "q" in qs and qs["q"][0].strip():
            logger.dev(f"URL validation OK: has search query 'q'")
            return True

        path_segments = path.count("/")
        if path_segments >= 3:
            logger.dev(f"URL validation OK: path has {path_segments} segments")
            return True

        logger.dev(f"URL validation FAIL: insufficient criteria")
        logger.dev(f" - query params: {qs}")
        logger.dev(f" - path segments: {path_segments}")
        logger.dev(f" - path: {path}")
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
    
    def perform_smart_search(self, keywords: str, forced_filters: List[str] = None) -> List[str]:
        collected_urls = []
        try:
            logger.info(f"Умный поиск: '{keywords}'...", token="smart_search")

            items = self._type_query(keywords)
            if not items:
                logger.warning("Меню категорий не открылось.")
                return []

            candidates = []
            seen_texts = set()

            # Нормализация текста для сравнения
            def normalize(s): 
                return str(s).replace('\xa0', ' ').replace('\n', ' ').strip().lower()

            for i, item in enumerate(items):
                try:
                    text = item.text.replace("\n", " ").strip()
                    if not text: continue
                    
                    # Сохраняем, даже если текст повторяется (на случай разных ссылок/типов)
                    # Но для seen_texts используем оригинал
                    if text not in seen_texts:
                        seen_texts.add(text)

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
            
            # --- ЛОГИКА ВЫБОРА КАТЕГОРИЙ ---
            if forced_filters:
                logger.info(f"Ищем выбранные категории ({len(forced_filters)} шт)...")
                for f in forced_filters:
                    f_norm = normalize(f)
                    matched_candidate = None
                    
                    # 1. Точное совпадение (приоритет)
                    for c in candidates:
                        if f_norm == normalize(c['text']):
                            matched_candidate = c
                            break
                    
                    # 2. Частичное совпадение (если точного нет)
                    if not matched_candidate:
                        for c in candidates:
                            c_norm = normalize(c['text'])
                            if f_norm in c_norm or c_norm in f_norm:
                                matched_candidate = c
                                break
                    
                    if matched_candidate:
                        if matched_candidate['text'] not in target_texts:
                            target_texts.append(matched_candidate['text'])
                            logger.dev(f"✓ Категория найдена: '{f}' -> '{matched_candidate['text']}'")
                    else:
                        logger.warning(f"⚠ Категория '{f}' не найдена в списке Авито для этого запроса.")
                        # Выводим кандидатов, чтобы понять причину (в dev режиме)
                        # debug_names = [c['text'] for c in candidates]
                        # logger.dev(f"Доступные: {debug_names}")

            # Если ничего не выбрали или фильтры не заданы - автовыбор (старая логика)
            if not target_texts and not forced_filters:
                main = None
                # Приоритет: Категория с иконкой -> Общая -> Любая
                for c in candidates:
                    if c['is_main'] and c['type'] == "CATEGORY": main = c; break
                if not main:
                    for c in candidates:
                        if c['type'] == "GENERAL": main = c; break
                if not main:
                    for c in candidates:
                        if c['type'] == "CATEGORY": main = c; break
                if not main and candidates: main = candidates[0]

                if main: target_texts = [main['text']]

            if not target_texts: 
                logger.warning("Не выбрано ни одной категории для перехода.")
                return []

            # --- ЦИКЛ ПЕРЕХОДА ---
            # Используем target_texts, который теперь точно содержит всё, что мы нашли
            for idx, target_text in enumerate(target_texts):
                try:
                    logger.info(f"Переход {idx+1}/{len(target_texts)}: {target_text}")
                    
                    # 1. Быстрый путь: href из кэша
                    cached_candidate = next((c for c in candidates if c['text'] == target_text), None)
                    
                    if cached_candidate and cached_candidate.get('href') and self._is_valid_url(cached_candidate['href']):
                        try:
                            logger.dev(f"Быстрый переход по href: {cached_candidate['href']}")
                            self.driver.get(cached_candidate['href'])
                            PageLoader.wait_for_load(self.driver, timeout=10)
                            time.sleep(1.5)
                            
                            if self._is_valid_url(self.driver.current_url):
                                collected_urls.append(self.driver.current_url)
                                continue 
                        except Exception as e:
                            logger.dev(f"Ошибка быстрого перехода: {e}")

                    # 2. Медленный путь (UI)
                    target_candidate = None
                    if idx == 0 and cached_candidate:
                        target_candidate = cached_candidate
                    else:
                        items = self._type_query(keywords, fast_mode=True)
                        if items:
                            for item in items:
                                try:
                                    if item.text.replace("\n", " ").strip() == target_text:
                                        target_candidate = {
                                            'text': target_text,
                                            'href': item.get_attribute("href") or "",
                                            'element': item,
                                            'index': 0 
                                        }
                                        break
                                except: pass

                    if not target_candidate:
                        logger.warning(f"Элемент '{target_text}' потерян при повторном поиске")
                        continue

                    # Навигация (Клавиатура -> Клик -> JS)
                    nav_success = False
                    
                    # Попытка клавиатурой (самая надежная для меню)
                    try:
                        search_input = None
                        for selector in AvitoSelectors.SEARCH_INPUTS:
                            try:
                                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                                if el.is_displayed():
                                    search_input = el; break
                            except: continue
                        
                        if search_input:
                            search_input.click()
                            time.sleep(0.3)
                            # Важно: индекс может сместиться, но пробуем по старому
                            target_idx = target_candidate.get('index', 0)
                            for _ in range(target_idx + 1):
                                search_input.send_keys(Keys.ARROW_DOWN)
                                time.sleep(0.05)
                            search_input.send_keys(Keys.ENTER)
                            time.sleep(1.5)
                            nav_success = True
                    except: pass

                    if not nav_success:
                        try:
                            self.driver.execute_script("arguments[0].click();", target_candidate['element'])
                            time.sleep(1.5)
                            nav_success = True
                        except: pass

                    # Сбор URL
                    waited = 0
                    while waited < 8:
                        time.sleep(0.5)
                        waited += 0.5
                        if self._is_valid_url(self.driver.current_url) and self.driver.current_url not in collected_urls:
                            collected_urls.append(self.driver.current_url)
                            break

                except Exception as e:
                    logger.error(f"Сбой перехода '{target_text}': {e}")
                    continue

            return collected_urls

        except Exception as e:
            logger.error(f"Критическая ошибка умного поиска: {e}")
            return []

# --- Item Parser ---
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
            #if sel_link:
            #    href = sel_link.get('href')
            #    if href: 
            #        match_user = re.search(r'/(?:user|companies|brands)/([^/]+)', href)
            #        if match_user:
            #            seller_id = match_user.group(1)
            #            seller_id = seller_id.split('?')[0]
            #        else:
            #            match_profile = re.search(r'/profile/([^/?]+)', href)
            #            if match_profile:
            #                seller_id = match_profile.group(1)
            if sel_link:
                href = sel_link.get('href')
                if href:
                    # Robust ID extraction handles /user/, /companies/, /brands/
                    parts = [p for p in href.split('/') if p and p not in ['profile', 'user', 'brands', 'companies']]
                    if parts:
                        seller_id = parts[-1].split('?')[0]
            
            views = 0

            return {
                'id': ad_id, 'link': link, 'price': price,
                'title': title, 'date_text': date_text,
                'description': description, 'city': city, 'condition': 'неизвестно',
                'seller_id': seller_id,
                'views': views,
                'parsed_at': datetime.now().isoformat()
            }
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
        
        # TODO
        sort_map = {
            "default": None, 
            "price_asc": "1",
            "price_desc": "2",
            "date": "104",
            "discount": None,
        }
        sort_code = sort_map.get(sort_type, None)

        for raw_url, cat_label in category_urls:
            try:
                parsed = urlparse(raw_url)
                qs = parse_qs(parsed.query)
                if min_price: qs["pmin"] = [str(min_price)]
                if max_price: qs["pmax"] = [str(max_price)]
                if sort_code: qs["s"] = [sort_code]
                
                path = parsed.path
                path_parts = [p for p in path.strip('/').split('/') if p]
                
                qs_encoded = urlencode(qs, doseq=True)
                
                if path_parts and path_parts[0] not in ['rossiya']: # Если это не РФ сразу
                    url_local = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{qs_encoded}"
                     
                    if url_local not in unique_check:
                        unique_check.add(url_local)
                        final_tasks.append((url_local, f"{cat_label} (Локально)"))

                # --- ЗАДАЧА 2: ВСЕ РЕГИОНЫ (Если включено) ---
                if search_all_regions:
                    # Подменяем регион на 'rossiya'
                    if path_parts:
                        path_parts_global = list(path_parts)
                        path_parts_global[0] = "rossiya" # Меняем первый сегмент (регион)
                        new_path = "/" + "/".join(path_parts_global)
                    else:
                        new_path = "/rossiya"
                    
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
            logger.info(f"Загружено {len(existing_ids_base)} исключений (ранее найденные товары).")
        
        total_tasks = len(final_tasks)
        max_total_global = self.max_total_items
        
        current_limit_ceiling = 0
        
        kwargs_filtered = {
            k: v for k, v in kwargs.items() 
            if k not in ['max_total_items', 'existing_ids_base']
        }
        
        for i, (url, label) in enumerate(final_tasks):
            if self.is_stop_requested(): break
            
            if max_total_global:
                current_limit_ceiling += max_total_global
            else:
                current_limit_ceiling = None

            logger.info(f"Задача {i+1}/{total_tasks}: {label}...")
            
            self.process_region(
                base_url=url,
                seen_ids=seen_ids,
                results_list=all_results,
                existing_ids_base=existing_ids_base,
                max_total_items=current_limit_ceiling,
                total_expected_items=current_limit_ceiling,
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
            
            forced_cats = kwargs.get('forced_categories')
            sort_type = kwargs.get('sort_type', 'date')
            all_regions = kwargs.get('search_all_regions', False)
            min_p = kwargs.get('min_price')
            max_p = kwargs.get('max_price')

            final_tasks = self._build_tasks(
                keywords, min_p, max_p, all_regions, forced_cats, sort_type
            )
            
            self.max_total_items = kwargs.get('max_total_items')
            self.deep_checks_done = 0
            kwargs['ignore_keywords'] = ignore_keywords or []

            results = self.run_tasks(final_tasks, **kwargs)
            return results

        except Exception as e:
            self.error_occurred.emit(str(e))
            logger.error(f"Error: {e}")
            return []
        finally:
            self._is_running = False
            logger.info("Готово.")

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
        if max_pages is None or max_pages <= 0:
             page_limit = ALL_PAGES_LIMIT
        else:
             page_limit = min(max_pages, ALL_PAGES_LIMIT)
        
        page = 1
        ignore_keywords = ignore_keywords or []
        blacklist_manager = get_blacklist_manager()

        while True:
            blocked_seller_ids = blacklist_manager.get_active_seller_ids()
            current_progress = 0
            if total_expected_items and total_expected_items > 0:
                total_done = len(results_list)
                if total_done >= total_expected_items:
                    current_progress = 100
                else:
                    current_progress = int((total_done / total_expected_items) * 100)
                logger.dev(f"Прогресс (общий): {total_done}/{total_expected_items} ({current_progress}%)")
            elif max_total_items and max_total_items > 0:
                if len(results_list) >= max_total_items:
                    current_progress = 100
                else:
                    current_progress = int((len(results_list) / max_total_items) * 100)
                logger.dev(f"Прогресс (категория): {len(results_list)}/{max_total_items} ({current_progress}%)")
            else:
                current_progress = int((page / page_limit) * 100)
                logger.dev(f"Прогресс (страницы): {page}/{page_limit} ({current_progress}%)")

            self.progress_value.emit(current_progress)

            # --- ПРОВЕРКА ЛИМИТА ДО ЗАГРУЗКИ СТРАНИЦЫ ---
            if max_total_items and len(results_list) >= max_total_items:
                logger.info(f"Лимит задачи достигнут ({len(results_list)}/{max_total_items}).")
                break

            if self.is_stop_requested(): 
                break

            if page > page_limit:
                logger.info("Лимит страниц достигнут.")
                break

            logger.progress(f"Сканирование страницы {page}...", token="parser_page")

            url = f"{base_url}&p={page}" if "?" in base_url else f"{base_url}?p={page}"

            ok = PageLoader.safe_get(
                self.driver_manager.driver, url, self.is_stop_requested,
                on_request=lambda: self.update_requests_count.emit(1, 0),
                driver_manager=self.driver_manager,
                ban_strategy=self.ban_strategy
            )

            if not ok:
                # Если страница не грузится, пробуем следующую
                page += 1
                continue

            PageLoader.scroll_page(self.driver_manager.driver, self.is_stop_requested)
            
            page_items = self._parse_page()
            if not page_items:
                logger.info("Товары на странице не найдены (возможно, конец списка).")
                break

            items_added_on_page = 0
            
            for item in page_items:
                if self.is_stop_requested(): break

                # --- 1. ПРОВЕРКА НА ЛИМИТ (Сразу) ---
                if max_total_items and len(results_list) >= max_total_items:
                    logger.info("Лимит товаров достигнут в процессе обработки страницы.")
                    return # Выходим полностью, задача выполнена

                ad_id = str(item.get("id") or "").strip()

                # --- 2. ПРОВЕРКА ДУБЛИКАТОВ ---
                if ad_id in seen_ids:
                    continue
                
                if ad_id and existing_ids_base and ad_id in existing_ids_base:
                    if skip_duplicates and not allow_rewrite_duplicates:
                        continue
                
                # --- 3. ПРОВЕРКА BLACKLIST ---
                raw_seller_id = str(item.get('seller_id', ''))
                if raw_seller_id and raw_seller_id.lower() in blocked_seller_ids:
                    logger.info(f"Пропущен продавец из ЧС: {raw_seller_id}...")
                    continue
                
                # --- 4. ФИЛЬТРЫ ---
                if self._should_skip(item, min_price, max_price, ignore_keywords, filter_defects):
                    continue
                
                # --- 5. DEEP DIVE (Глубокий анализ) ---
                if is_deep_mode:
                    # Лимит на количество "глубоких" запросов (если нужно, можно привязать к max_total_items)
                    self.deep_checks_done += 1
                    
                    short = item["title"][:30]
                    logger.progress(f"Анализ товара: {short}", token="parser_deep")
                    self.update_requests_count.emit(1, 0)
                    
                    details = self._deep_dive_get_details(item["link"])
                    if not details:
                        continue # Если не удалось получить детали (или забанили), пропускаем
                    
                    item.update(details)

                    real_seller_id = str(item.get('seller_id', ''))
                    if real_seller_id and real_seller_id.lower() in blocked_seller_ids:
                        logger.info(f"Пропущен продавец из ЧС (этап 2, DeepDive): {real_seller_id}...")
                        continue

                # --- 6. СОХРАНЕНИЕ РЕЗУЛЬТАТА ---
                if item['id'] not in seen_ids:
                    seen_ids.add(item['id'])
                    results_list.append(item)
                    items_added_on_page += 1

                    # Отправка сигнала прогресса
                    if total_expected_items and total_expected_items > 0:
                        total_done = len(results_list)
                        p = min(100, int((total_done / total_expected_items) * 100))
                        self.progress_value.emit(p)
                    elif max_total_items and max_total_items > 0:
                        p = min(100, int((len(results_list) / max_total_items) * 100))
                        self.progress_value.emit(p)
                    
                if max_items_per_page and items_added_on_page >= max_items_per_page: 
                    break

            if items_added_on_page > 0:
                logger.info(f"Стр {page}: +{items_added_on_page} товаров", token=f"page_done_{page}")

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
                driver_manager=self.driver_manager,
                ban_strategy=self.ban_strategy,
            )
            if not ok:
                return None

            wait = random.uniform(1.5, 2.5)
            time.sleep(wait)

            if self.is_stop_requested():
                return None

            body_text = self.driver_manager.driver.execute_script(
                "return document.body.innerText;"
            ).lower()

            # TODO
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
                'views': 0,
                'seller_id': '',
                'price': 0
            }

            try:
                # Пробуем через микроразметку (самый надежный способ)
                price_meta = self.driver_manager.driver.find_element(By.CSS_SELECTOR, "[itemprop='price']")
                price_val = price_meta.get_attribute("content")
                if price_val:
                    details['price'] = int(price_val)
                else:
                    # Если content пуст, берем текст
                    text_price = price_meta.text.replace('\xa0', '').replace(' ', '').replace('₽', '')
                    details['price'] = int(text_price)
            except:
                try:
                    # Запасной вариант: Avito data-marker
                    price_el = self.driver_manager.driver.find_element(By.CSS_SELECTOR, "[data-marker='item-view/item-price']")
                    text_price = price_el.text.replace('\xa0', '').replace(' ', '').replace('₽', '')
                    details['price'] = int(text_price)
                except:
                    pass

            try:
                seller_links = self.driver_manager.driver.find_elements(By.CSS_SELECTOR, "a[href*='/user/'], a[href*='/companies/'], a[href*='/brands/']")
                for link in seller_links:
                    href = link.get_attribute('href')
                    if href:
                        match = re.search(r'/(?:user|companies|brands)/([^/]+)', href)
                        if match:
                            details['seller_id'] = match.group(1).split('?')[0]
                            break
            except: pass

            try:
                desc_el = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR, "[data-marker='item-view/item-description']"
                )
                details['description'] = desc_el.text.strip()
            except: pass

            try:
                addr_container = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR, "[itemprop='address']"
                )
                details['city'] = addr_container.text.strip().split(',')[0].strip()
            except:
                try:
                    addr_el = self.driver_manager.driver.find_element(
                        By.CSS_SELECTOR, "[data-marker='delivery-item-address-text']"
                    )
                    details['city'] = addr_el.text.strip().split(',')[0].strip()
                except: pass

            try:
                params_el = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR, "[data-marker='item-view/item-params']"
                )
                for line in params_el.text.split('\n'):
                    if "Состояние" in line:
                        details['condition'] = line.replace("Состояние", "").replace(":", "").strip()
                        break
            except: pass

            try:
                date_el = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR, "[data-marker='item-view/item-date']"
                )
                details['date_text'] = date_el.text.replace("· ", "").strip()
            except: pass

            try:
                views_el = self.driver_manager.driver.find_element(By.CSS_SELECTOR, "[data-marker='item-view/total-views']")
                txt = views_el.text
                m = re.search(r'(\d+)', txt.replace(' ', ''))
                if m: details['views'] = int(m.group(1))
            except:
                try:
                    src = self.driver_manager.driver.page_source
                    m = re.search(r'(\d+)\s+просмотр', src)
                    if m: details['views'] = int(m.group(1))
                except: pass

            return details

        except Exception as e:
            return None

    def _has_next_page(self, current_page: int) -> bool:
        try:
            btn = self.driver_manager.driver.find_elements(By.CSS_SELECTOR, AvitoSelectors.PAGINATION_NEXT)
            if btn: return AvitoSelectors.DISABLED_CLASS not in btn[0].get_attribute("class")
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
            source = self.driver_manager.driver.page_source
            soup = BeautifulSoup(source, 'lxml')
            elements = soup.select(AvitoSelectors.ITEM_CONTAINER)
            
            for el in elements:
                if self.is_stop_requested(): break
                if el.find_parent(class_=lambda x: x and 'carousel' in x.lower()): continue
                
                item = ItemParser.parse_search_item(el)
                if item: items.append(item)
        except Exception as e:
            logger.error(f"Ошибка парсинга страницы: {e}")
        return items

    def cleanup(self):
        self.driver_manager.cleanup()