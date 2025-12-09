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
            self.driver.get("https://www.avito.ru/moskva")
            PageLoader.wait_for_load(self.driver, timeout=10)
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
            if items is None:
                logger.warning("Не удалось выполнить поиск. Использую запасной вариант...")
                return []
    
            if not items:
                logger.warning("Категории не появились. Использую запасной вариант...")
                return []
    
            # ✅ Собираем информацию о категориях (ТЕКСТ + ЭЛЕМЕНТ + HREF)
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
    
                    # ✅ Получаем href ДО клика
                    href = item.get_attribute("href") or ""
    
                    candidates.append({
                        'index': i,
                        'text': text,
                        'type': item_type,
                        'is_main': has_icon,
                        'href': href,
                        'element': item
                    })
    
                    logger.dev(f"Кандидат: '{text}' | type={item_type} | href={href[:50] if href else 'NO HREF'}")
    
                except Exception as e:
                    logger.dev(f"Ошибка сбора кандидата {i}: {e}")
                    pass
                
            if not candidates:
                logger.info("Подходящих категорий не найдено...", token="smart_search")
                return []
    
            # ✅ Определяем ТЕКСТЫ целевых категорий
            target_texts = []
    
            if forced_filters:
                logger.info(f"Принудительные фильтры: {forced_filters}")
                for f in forced_filters:
                    found = False
                    for c in candidates:
                        if f.lower() in c['text'].lower() or c['text'].lower() in f.lower():
                            if c['text'] not in target_texts:
                                target_texts.append(c['text'])
                                logger.info(f"Найдено совпадение: '{c['text']}' для фильтра '{f}'...")
                                found = True
                                break
                    if not found:
                        logger.warning(f"Не найдено совпадение для фильтра '{f}'...")
    
            # ✅ ИСПРАВЛЕНИЕ 4: Улучшенный выбор категории
            if not target_texts:
                logger.info("Используется основная категория...")
                main = None
    
                # Приоритет 1: КАТЕГОРИЯ с иконкой (is_main=True)
                for c in candidates:
                    if c['is_main'] and c['type'] == "CATEGORY":
                        main = c
                        logger.dev(f"Выбрана главная категория (с иконкой): '{c['text']}'")
                        break
                    
                # Приоритет 2: СПЕЦИАЛЬНАЯ категория (со стрелкой ←)
                if main is None:
                    for c in candidates:
                        if c['type'] == "GENERAL":
                            main = c
                            logger.dev(f"Выбрана специальная категория (со стрелкой): '{c['text']}'")
                            break
                        
                # Приоритет 3: Первая КАТЕГОРИЯ (без стрелки, но с иконкой)
                if main is None:
                    for c in candidates:
                        if c['type'] == "CATEGORY":
                            main = c
                            logger.dev(f"Выбрана категория (без иконки): '{c['text']}'")
                            break
                        
                # Fallback: Первый элемент (если ничего не найдено)
                if main is None and candidates:
                    main = candidates[0]
                    logger.warning(f"Не найдено категорий, использую первый элемент: '{main['text']}'")
    
                if main:
                    target_texts = [main['text']]
    
            if not target_texts:
                logger.warning("Не удалось определить целевые категории...")
                return []
    
            # ✅ УЛУЧШЕННАЯ ЛОГИКА ПЕРЕХОДА
            for idx, target_text in enumerate(target_texts):
                try:
                    # Для первого клика используем уже загруженные элементы
                    if idx == 0:
                        target_candidate = next((c for c in candidates if c['text'] == target_text), None)
                    else:
                        # Для последующих кликов делаем новый поиск
                        items = self._type_query(keywords, fast_mode=True)
                        if not items:
                            logger.warning(f"Не удалось получить список категорий (попытка {idx+1})")
                            continue
                        
                        # Ищем элемент по ТЕКСТУ
                        target_element = None
                        target_href = None
                        for item in items:
                            try:
                                item_text = item.text.replace("\n", " ").strip()
                                if item_text == target_text:
                                    target_element = item
                                    target_href = item.get_attribute("href") or ""
                                    break
                            except:
                                pass
                            
                        if not target_element:
                            logger.warning(f"Категория '{target_text}' не найдена в новом списке")
                            continue
                        
                        target_candidate = {
                            'text': target_text,
                            'href': target_href,
                            'element': target_element,
                            'index': 0  # Для последующих кликов индекс неизвестен
                        }
    
                    if not target_candidate:
                        logger.warning(f"Не найден кандидат для '{target_text}'")
                        continue
                    
                    logger.info(f"Переход {idx+1}/{len(target_texts)}: {target_text}")
    
                    # СТРАТЕГИЯ 1: Попробовать использовать href напрямую
                    if target_candidate.get('href') and self._is_valid_url(target_candidate['href']):
                        logger.dev(f"Используем прямой href: {target_candidate['href']}")
                        old_url = self.driver.current_url
    
                        self.driver.get(target_candidate['href'])
                        PageLoader.wait_for_load(self.driver, timeout=10)
                        time.sleep(2.0)
    
                        current_url = self.driver.current_url
                        if current_url != old_url and self._is_valid_url(current_url):
                            collected_urls.append(current_url)
                            logger.success(f"✓ URL получен (прямой переход): {current_url}")
                            continue
                        else:
                            logger.warning(f"Прямой переход не удался, пробуем навигацию...")
    
                    # СТРАТЕГИЯ 2: Эмуляция клавиатурного выбора
                    target_element = target_candidate['element']
                    old_url = self.driver.current_url.split('#')[0]
                    navigation_success = False
                    
                    # Метод 1: Клавиатурная навигация (самый надежный)
                    logger.dev(f"Метод 1: Клавиатурная навигация...")
                    try:
                        # Получаем индекс целевого элемента
                        target_index = target_candidate.get('index', 0)
                        
                        # Находим поисковую строку заново
                        search_input = None
                        for selector in AvitoSelectors.SEARCH_INPUTS:
                            try:
                                search_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                                if search_input.is_displayed():
                                    break
                                search_input = None
                            except:
                                continue
                            
                        if search_input:
                            # Фокусируемся на поисковой строке
                            search_input.click()
                            time.sleep(0.3)
                            
                            # Нажимаем стрелку вниз нужное количество раз
                            for _ in range(target_index + 1):
                                search_input.send_keys(Keys.ARROW_DOWN)
                                time.sleep(0.15)
                            
                            # Нажимаем Enter
                            search_input.send_keys(Keys.ENTER)
                            logger.dev("✓ Клавиатурная навигация выполнена (Arrow Down + Enter)")
                            
                            # Ждем навигации
                            time.sleep(1.5)
                            navigation_success = True
                        else:
                            logger.dev("✗ Поисковая строка не найдена")
                    except Exception as e:
                        logger.dev(f"✗ Клавиатурная навигация: {e}")
                    
                    # Метод 2: Прямой клик + принудительный переход
                    if not navigation_success:
                        logger.dev(f"Метод 2: Прямой клик по элементу...")
                        try:
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                                target_element
                            )
                            time.sleep(0.5)
                            
                            # Пробуем ActionChains
                            ActionChains(self.driver).move_to_element(target_element).pause(0.3).click().perform()
                            logger.dev("✓ ActionChains клик выполнен")
                            time.sleep(1.5)
                            navigation_success = True
                        except Exception as e:
                            logger.dev(f"✗ Клик: {e}")
                    
                    # Метод 3: JavaScript клик (запасной вариант)
                    if not navigation_success:
                        logger.dev(f"Метод 3: JavaScript клик...")
                        try:
                            self.driver.execute_script("arguments[0].click();", target_element)
                            logger.dev("✓ JS клик выполнен")
                            time.sleep(1.5)
                            navigation_success = True
                        except Exception as e:
                            logger.dev(f"✗ JS клик: {e}")
                    
                    # Если все методы провалились, все равно проверяем URL
                    if not navigation_success:
                        logger.warning(f"Все методы навигации провалились для '{target_text}', проверяем URL...")
                    
                    # ✅ ПРОВЕРКА ИЗМЕНЕНИЯ URL
                    max_wait = 15
                    waited = 0
                    url_changed = False
    
                    while waited < max_wait:
                        time.sleep(0.5)
                        waited += 0.5
                        current_url = self.driver.current_url.split('#')[0]
    
                        # Проверяем не только изменение, но и валидность
                        if current_url != old_url:
                            logger.dev(f"URL изменился после {waited:.1f}s: {current_url}")
    
                            # Дополнительная проверка: URL должен быть валидным
                            if self._is_valid_url(current_url):
                                url_changed = True
                                break
                            else:
                                logger.dev("URL изменился, но не прошел валидацию, продолжаем ждать...")
    
                    if not url_changed:
                        logger.warning(f"URL не изменился после всех попыток (ждали {max_wait}s)")
                        logger.dev(f"Старый URL: {old_url}")
                        logger.dev(f"Текущий URL: {self.driver.current_url}")
    
                        # Последняя попытка: может быть, страница загрузилась с якорем?
                        current_full = self.driver.current_url
                        if self._is_valid_url(current_full):
                            logger.info("URL с якорем валиден, используем его...")
                            collected_urls.append(current_full)
                            continue
                        else:
                            # Окончательно не удалось
                            logger.error(f"Не удалось получить валидный URL для '{target_text}'")
                            continue
                        
                    # ✅ URL изменился и валиден - добавляем в результат
                    PageLoader.wait_for_load(self.driver, timeout=5)
                    time.sleep(1.5)
                    
                    current_url = self.driver.current_url
                    if self._is_valid_url(current_url):
                        collected_urls.append(current_url)
                        logger.success(f"✓ URL получен (навигация): {current_url}")
                    else:
                        logger.warning(f"✗ URL не прошел валидацию: {current_url}")
                        logger.dev(f"Проверка валидности:")
                        logger.dev(f" - avito.ru in url: {'avito.ru' in current_url}")
                        logger.dev(f" - path segments: {urlparse(current_url).path.count('/')}")
                        logger.dev(f" - query params: {parse_qs(urlparse(current_url).query)}")
    
                except Exception as e:
                    logger.error(f"Ошибка перехода к '{target_text}': {e}")
                    import traceback
                    logger.dev(f"Traceback:\n{traceback.format_exc()}")
                    continue
                                    
            return collected_urls
    
        except Exception as e:
            logger.error(f"Ошибка умного поиска: {e}")
            import traceback
            logger.dev(f"Traceback:\n{traceback.format_exc()}")
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
            "default": None, 
            "price_asc": "1",
            "price_desc": "2",
            "date": "104",
            "discount": None,
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

    def run_tasks(self, final_tasks, **kwargs) -> List[Dict[str, Any]]:
        all_results = []
        seen_ids = set()
        existing_ids_base = kwargs.get('existing_ids_base', set())
        total_tasks = len(final_tasks)
        max_total_global = self.max_total_items
        max_per_category = max_total_global  # Убрали разделение на категории

        if max_total_global:
            # Больше не делим на количество категорий
            # max_per_category = max_total_global // total_tasks
            max_per_category = max_total_global
            logger.info(f"Получение до {max_per_category} товаров в каждой из {total_tasks} категорий...")

        # Рассчитываем общий ожидаемый результат для прогресс-бара
        total_expected_items = max_total_global * total_tasks if max_total_global else None

        kwargs_filtered = {k: v for k, v in kwargs.items() if k != 'max_total_items'}

        for i, (url, label) in enumerate(final_tasks):
            if self.is_stop_requested():
                break
            logger.info(f"Категория {i+1}/{total_tasks}: {label}...")
            category_results = []
            self.process_region(
                base_url=url,
                seen_ids=seen_ids,
                results_list=category_results,
                existing_ids_base=existing_ids_base,
                max_total_items=max_per_category,
                total_expected_items=total_expected_items,
                current_task_index=i,
                total_tasks=total_tasks,
                **kwargs_filtered
            )
            all_results.extend(category_results)
            logger.success(f"Категория {i+1}: получено {len(category_results)} товаров...")

        logger.success(f"Итого собрано: {len(all_results)} товаров из {total_tasks} категорий...")
        return all_results

    def search_items(self, keywords, ignore_keywords=None, **kwargs) -> List[Dict[str, Any]]:
        if self._is_running: return []
        self._is_running = True
        self._stop_requested = False
        
        # Сброс прогресса
        self.progress_value.emit(0)

        logger.success(f"--- ЗАПУСК ПАРСЕРА: {keywords} ---")

        try:
            logger.progress("Инициализация браузера...", token="init")
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
            logger.error(f"Критическая ошибка: {e}")
            return []
        finally:
            self._is_running = False
            logger.info("Парсинг завершен...")

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
        blocked_seller_ids = blacklist_manager.get_active_seller_ids()

        while True:
            current_progress = 0
            if total_expected_items and total_expected_items > 0:
                items_done_in_current = len(results_list)
                items_done_in_previous = current_task_index * max_total_items
                total_done = items_done_in_previous + items_done_in_current
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

            if self.is_stop_requested(): 
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
                page += 1
                continue

            PageLoader.scroll_page(self.driver_manager.driver, self.is_stop_requested)
            
            page_items = self._parse_page()
            if not page_items: break

            items_added_on_page = 0
            for item in page_items:
                if self.is_stop_requested(): break
                if max_total_items and len(results_list) >= max_total_items:
                    if total_expected_items:
                         items_done_in_current = max_total_items
                         items_done_in_previous = current_task_index * max_total_items
                         total_done = items_done_in_previous + items_done_in_current
                         p = int((total_done / total_expected_items) * 100)
                         self.progress_value.emit(p)
                    else:
                         self.progress_value.emit(100)
                    return

                ad_id = str(item.get("id") or "").strip()

                if ad_id and existing_ids_base and ad_id in existing_ids_base:
                    if skip_duplicates and not allow_rewrite_duplicates:
                        continue
                
                if ad_id in seen_ids:
                    continue

                item_seller_id = item.get('seller_id', '')
                if item_seller_id and item_seller_id in blocked_seller_ids:
                    # logger.dev(f"Seller blocked: {item_seller_id}")
                    continue
                
                if self._should_skip(item, min_price, max_price, ignore_keywords, filter_defects):
                    continue
                
                if is_deep_mode:
                    if max_total_items and self.deep_checks_done >= max_total_items: return
                    self.deep_checks_done += 1
                    
                    short = item["title"][:30]
                    logger.progress(f"Анализ товара: {short}", token="parser_deep")
                    self.update_requests_count.emit(1, 0)
                    
                    details = self._deep_dive_get_details(item["link"])
                    if not details:
                        continue
                    
                    item.update(details)
                
                if ad_id not in seen_ids:
                    seen_ids.add(ad_id)
                    results_list.append(item)
                    items_added_on_page += 1

                    if total_expected_items and total_expected_items > 0:
                        items_done_in_current = len(results_list)
                        items_done_in_previous = current_task_index * max_total_items
                        total_done = items_done_in_previous + items_done_in_current
                        
                        p = min(100, int((total_done / total_expected_items) * 100))
                        self.progress_value.emit(p)
                        
                    elif max_total_items and max_total_items > 0:
                        p = min(100, int((len(results_list) / max_total_items) * 100))
                        self.progress_value.emit(p)
                    
                if max_items_per_page and items_added_on_page >= max_items_per_page: break

            if items_added_on_page > 0:
                logger.info(f"Стр {page}: +{items_added_on_page} товаров", token=f"page_done_{page}")

            if not self._has_next_page(page): break
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
                seller_link = self.driver_manager.driver.find_element(
                    By.CSS_SELECTOR,
                    "a[data-marker='seller-info/label'], a[href*='/profile/']"
                )
                href = seller_link.get_attribute('href')
                if href:
                    match = re.search(r'/profile/(\w+)', href)
                    if match: seller_id = match.group(1)
            except: pass
            
            if seller_id: details['seller_id'] = seller_id

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