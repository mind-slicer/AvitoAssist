import os
import time
import random
import pickle
import logging
from dataclasses import dataclass
from typing import Sequence, Optional, Tuple, Callable

# Импортируем undetected_chromedriver
import undetected_chromedriver as uc
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from app.config import (
    BASE_APP_DIR,
    USER_AGENTS,
    MIN_REQUEST_DELAY,
    MAX_REQUEST_DELAY,
    COOLDOWN_EVERY_MIN,
    COOLDOWN_EVERY_MAX,
    COOLDOWN_DURATION_MIN,
    COOLDOWN_DURATION_MAX,
    RANDOM_SCROLL_CHANCE,
    RANDOM_MOUSE_MOVE_CHANCE,
)

# Настраиваем логгер для undetected_chromedriver, чтобы не мусорил в консоль
logging.getLogger('uc').setLevel(logging.ERROR)

@dataclass
class DriverConfig:
    user_agents: Sequence[str] | None = None
    initial_ua: Optional[str] = None
    min_request_delay: float = MIN_REQUEST_DELAY
    max_request_delay: float = MAX_REQUEST_DELAY
    cooldown_every_min: int = COOLDOWN_EVERY_MIN
    cooldown_every_max: int = COOLDOWN_EVERY_MAX
    cooldown_range: Tuple[float, float] = (COOLDOWN_DURATION_MIN, COOLDOWN_DURATION_MAX)
    use_cookies: bool = True
    delete_cookies_on_start: bool = True
    # ВАЖНО: Для Авито эти значения должны быть False (включаем картинки и CSS)
    block_images: bool = False  
    block_css: bool = False
    enable_human_behavior: bool = True
    
    def __post_init__(self):
        if self.user_agents is None:
            self.user_agents = USER_AGENTS

class DriverManager:
    def __init__(self, config: DriverConfig | None = None):
        self.config = config or DriverConfig()
        self._driver = None
        self._request_count = 0
        self._last_request_time = 0
        self._cookies_path = os.path.join(BASE_APP_DIR, "avito_cookies.pkl")
        self._next_cooldown = random.randint(
            self.config.cooldown_every_min,
            self.config.cooldown_every_max
        )
        
        if (
            self.config.use_cookies
            and self.config.delete_cookies_on_start
            and os.path.exists(self._cookies_path)
        ):
            try:
                os.remove(self._cookies_path)
            except:
                pass
        
        # Выбор UA оставляем, но UC лучше работает с нативным
        if self.config.initial_ua:
            self.current_ua = self.config.initial_ua
        else:
            self.current_ua = random.choice(list(self.config.user_agents))
    
    @property
    def driver(self):
        if self._driver is None:
            self._initialize_driver()
        return self._driver
    
    def _initialize_driver(self):
        if self._driver:
            return
        
        # Опции Chrome
        options = uc.ChromeOptions()
        options.page_load_strategy = 'eager'
        
        # Базовые аргументы
        args = [
            "--no-first-run",
            "--no-service-autorun",
            "--password-store=basic",
            "--disable-blink-features=AutomationControlled",
            "--lang=ru-RU",
        ]
        
        for arg in args:
            options.add_argument(arg)

        # В UC user-agent лучше не подменять жестко, если он не совпадает с версией Chrome,
        # но если очень нужно - можно раскомментировать. 
        options.add_argument(f"--user-agent={self.current_ua}")

        # Настройки контента (разрешаем картинки и CSS для прохождения проверок)
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.geolocation": 2,
            "profile.managed_default_content_settings.media_stream": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }
        
        # Блокировка только если явно запрошено (для Авито не рекомендуется)
        if self.config.block_images:
            prefs["profile.managed_default_content_settings.images"] = 2
        if self.config.block_css:
            prefs["profile.managed_default_content_settings.stylesheets"] = 2
            
        options.add_experimental_option("prefs", prefs)
        
        try:
            # Инициализация undetected_chromedriver
            # headless=False важно, так как в headless режиме fingerprint сильно отличается
            self._driver = uc.Chrome(
                options=options,
                headless=True,
                use_subprocess=True,
            )
            
            self._driver.set_page_load_timeout(60)
            
            # Дополнительный размер окна для естественности
            self._driver.set_window_size(random.randint(1200, 1600), random.randint(800, 1000))
            
            if self.config.use_cookies:
                self._load_cookies()
                
        except Exception as e:
            if self._driver:
                try:
                    self._driver.close()
                except:
                    pass
                self._driver = None
            raise RuntimeError(f"Failed to initialize UC Driver: {e}")
    
    def random_mouse_movement(self):
        if not self.config.enable_human_behavior or not self._driver:
            return
        
        if random.random() > RANDOM_MOUSE_MOVE_CHANCE:
            return
        
        try:
            # UC иногда теряет связь при долгих простоях, оборачиваем в try
            actions = ActionChains(self._driver)
            x_offset = random.randint(-100, 100)
            y_offset = random.randint(-100, 100)
            # Двигаем от текущего положения (если возможно) или просто небольшое движение
            actions.move_by_offset(x_offset, y_offset)
            actions.perform()
            time.sleep(random.uniform(0.1, 0.3))
        except:
            pass
    
    def random_scroll(self):
        if not self.config.enable_human_behavior or not self._driver:
            return
        
        if random.random() > RANDOM_SCROLL_CHANCE:
            return
        
        try:
            scroll_amount = random.randint(100, 400)
            self._driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.3, 0.8))
        except:
            pass
    
    def _load_cookies(self):
        """Загрузка кук. Используем главную страницу, а не 404."""
        if not self.config.use_cookies:
            return
            
        if os.path.exists(self._cookies_path):
            try:
                # Заходим на домен, чтобы можно было проставить куки
                self._driver.get("https://www.avito.ru/")
                # Даем немного времени на инициализацию защиты
                time.sleep(2)
                
                with open(self._cookies_path, "rb") as f:
                    cookies = pickle.load(f)
                    
                for cookie in cookies:
                    try:
                        self._driver.add_cookie(cookie)
                    except Exception:
                        continue
                        
                # Обновляем страницу, чтобы применить куки
                self._driver.refresh()
                time.sleep(2)
            except Exception as e:
                print(f"Cookie load error: {e}")
                pass
    
    def _save_cookies(self):
        if not self.config.use_cookies or not self._driver:
            return
        try:
            cookies = self._driver.get_cookies()
            if cookies:
                with open(self._cookies_path, "wb") as f:
                    pickle.dump(cookies, f)
        except:
            pass
    
    def rate_limit_delay(self, stop_check: Callable[[], bool] | None = None):
        cfg = self.config
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        # Базовая задержка между запросами
        if time_since_last < cfg.min_request_delay:
            base_delay = random.uniform(cfg.min_request_delay, cfg.max_request_delay)
            # Иногда делаем паузу длиннее
            if random.random() < 0.1:
                base_delay *= random.uniform(1.5, 2.0)
            
            remaining = base_delay - time_since_last
            step = 0.2
            elapsed = 0.0
            
            while elapsed < remaining:
                if stop_check and stop_check():
                    return
                sleep_time = min(step, remaining - elapsed)
                time.sleep(sleep_time)
                elapsed += sleep_time
        
        # Случайные движения мыши во время ожидания
        if self.config.enable_human_behavior and random.random() < 0.3:
            self.random_mouse_movement()
        
        self._last_request_time = time.time()
        self._request_count += 1
        
        # Длительный кулдаун (эмуляция "перекура")
        if self._request_count >= self._next_cooldown:
            cd_min, cd_max = cfg.cooldown_range
            cooldown = random.uniform(cd_min, cd_max)
            
            if random.random() < 0.05:
                cooldown *= random.uniform(2.0, 3.0)
            
            # print(f"Cooldown: {cooldown:.1f}s") # debug
            
            step = 0.5
            elapsed = 0.0
            
            while elapsed < cooldown:
                if stop_check and stop_check():
                    return
                sleep_time = min(step, cooldown - elapsed)
                time.sleep(sleep_time)
                elapsed += sleep_time
            
            self._next_cooldown = self._request_count + random.randint(
                cfg.cooldown_every_min,
                cfg.cooldown_every_max
            )
    
    def cleanup(self):
        if self._driver:
            if self.config.use_cookies:
                self._save_cookies()
            try:
                self._driver.close()
            except:
                pass
            self._driver = None
            self._request_count = 0