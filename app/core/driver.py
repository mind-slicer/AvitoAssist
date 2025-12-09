import os
import time
import random
import pickle
import subprocess
from dataclasses import dataclass
from typing import Sequence, Optional, Tuple, Callable
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

from app.config import (
    CHROME_OPTIONS_ARGS,
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
    block_images: bool = True
    block_css: bool = True
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
        
        if self.config.initial_ua:
            self.current_ua = self.config.initial_ua
        else:
            self.current_ua = random.choice(list(self.config.user_agents))
    
    @property
    def driver(self):
        if self._driver is None:
            self._initialize_driver()
        return self._driver
    
    def _kill_dead_process(self):
        try:
            subprocess.run("taskkill /F /IM chromedriver.exe /T", shell=True, 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
    
    def _initialize_driver(self):
        if self._driver:
            return
        
        self._kill_dead_process()
        options = Options()
        options.page_load_strategy = 'normal'
        
        for arg in CHROME_OPTIONS_ARGS:
            options.add_argument(arg)
        
        options.add_argument(f"--user-agent={self.current_ua}")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option('useAutomationExtension', False)
        
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "profile.managed_default_content_settings.cookies": 1,
            "profile.managed_default_content_settings.javascript": 1,
            "profile.managed_default_content_settings.plugins": 2,
            "profile.managed_default_content_settings.popups": 2,
            "profile.managed_default_content_settings.geolocation": 2,
            "profile.managed_default_content_settings.media_stream": 2,
        }
        
        if self.config.block_images:
            prefs["profile.managed_default_content_settings.images"] = 2
        if self.config.block_css:
            prefs["profile.managed_default_content_settings.stylesheets"] = 2
        
        options.add_experimental_option("prefs", prefs)
        
        try:
            driver_path = ChromeDriverManager().install()
            service = Service(driver_path)
            self._driver = webdriver.Chrome(service=service, options=options)
            self._driver.set_page_load_timeout(30)
            
            self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    
                    Object.defineProperty(navigator, 'plugins', { 
                        get: () => {
                            const plugins = [
                                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                                { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                            ];
                            return plugins;
                        }
                    });
                    
                    Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
                    
                    window.navigator.chrome = {
                        runtime: {},
                        loadTimes: function() {},
                        csi: function() {},
                        app: {}
                    };
                    
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications'
                            ? Promise.resolve({ state: Notification.permission })
                            : originalQuery(parameters)
                    );
                    
                    const getParameter = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {
                        const vendors = ['Intel Inc.', 'NVIDIA Corporation', 'AMD'];
                        const renderers = [
                            'Intel Iris OpenGL Engine',
                            'NVIDIA GeForce GTX 1060',
                            'AMD Radeon RX 580'
                        ];
                        if (parameter === 37445) return vendors[Math.floor(Math.random() * vendors.length)];
                        if (parameter === 37446) return renderers[Math.floor(Math.random() * renderers.length)];
                        return getParameter.call(this, parameter);
                    };
                    
                    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
                    
                    Object.defineProperty(navigator, 'getBattery', {
                        get: () => async () => ({
                            charging: Math.random() > 0.5,
                            chargingTime: Infinity,
                            dischargingTime: Math.random() * 10000 + 5000,
                            level: Math.random() * 0.5 + 0.5
                        })
                    });
                    
                    Object.defineProperty(navigator, 'hardwareConcurrency', {
                        get: () => [4, 6, 8, 12, 16][Math.floor(Math.random() * 5)]
                    });
                    
                    Object.defineProperty(navigator, 'deviceMemory', {
                        get: () => [4, 8, 16][Math.floor(Math.random() * 3)]
                    });
                    
                    const toBlob = HTMLCanvasElement.prototype.toBlob;
                    const toDataURL = HTMLCanvasElement.prototype.toDataURL;
                    const getImageData = CanvasRenderingContext2D.prototype.getImageData;
                    
                    const noisify = function(canvas, context) {
                        const shift = {
                            'r': Math.floor(Math.random() * 10) - 5,
                            'g': Math.floor(Math.random() * 10) - 5,
                            'b': Math.floor(Math.random() * 10) - 5,
                            'a': Math.floor(Math.random() * 10) - 5
                        };
                        const width = canvas.width;
                        const height = canvas.height;
                        if (width && height) {
                            const imageData = getImageData.apply(context, [0, 0, width, height]);
                            for (let i = 0; i < height; i++) {
                                for (let j = 0; j < width; j++) {
                                    const n = ((i * (width * 4)) + (j * 4));
                                    imageData.data[n + 0] = imageData.data[n + 0] + shift.r;
                                    imageData.data[n + 1] = imageData.data[n + 1] + shift.g;
                                    imageData.data[n + 2] = imageData.data[n + 2] + shift.b;
                                    imageData.data[n + 3] = imageData.data[n + 3] + shift.a;
                                }
                            }
                            context.putImageData(imageData, 0, 0);
                        }
                    };
                    
                    console.debug = () => {};
                    
                    if (window.top === window.self) {
                        window.chrome = window.navigator.chrome;
                    }
                """
            })
            
            if self.config.use_cookies:
                self._load_cookies()
                
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Chrome Driver: {e}")
    
    def random_mouse_movement(self):
        if not self.config.enable_human_behavior:
            return
        
        if random.random() > RANDOM_MOUSE_MOVE_CHANCE:
            return
        
        try:
            actions = ActionChains(self._driver)
            x_offset = random.randint(-200, 200)
            y_offset = random.randint(-200, 200)
            actions.move_by_offset(x_offset, y_offset)
            actions.perform()
            time.sleep(random.uniform(0.1, 0.3))
        except:
            pass
    
    def random_scroll(self):
        if not self.config.enable_human_behavior:
            return
        
        if random.random() > RANDOM_SCROLL_CHANCE:
            return
        
        try:
            scroll_amount = random.randint(100, 500)
            self._driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.3, 0.8))
        except:
            pass
    
    def _load_cookies(self):
        if not self.config.use_cookies:
            return
        if os.path.exists(self._cookies_path):
            try:
                self._driver.get("https://www.avito.ru/404")
                time.sleep(1)
                with open(self._cookies_path, "rb") as f:
                    cookies = pickle.load(f)
                for cookie in cookies:
                    try:
                        self._driver.add_cookie(cookie)
                    except:
                        pass
                self._driver.refresh()
            except:
                pass
    
    def _save_cookies(self):
        if not self.config.use_cookies:
            return
        if self._driver:
            try:
                with open(self._cookies_path, "wb") as f:
                    pickle.dump(self._driver.get_cookies(), f)
            except:
                pass
    
    def rate_limit_delay(self, stop_check: Callable[[], bool] | None = None):
        cfg = self.config
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < cfg.min_request_delay:
            base_delay = random.uniform(cfg.min_request_delay, cfg.max_request_delay)
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
        
        if self.config.enable_human_behavior and random.random() < 0.3:
            self.random_mouse_movement()
        
        self._last_request_time = time.time()
        self._request_count += 1
        
        if self._request_count >= self._next_cooldown:
            cd_min, cd_max = cfg.cooldown_range
            cooldown = random.uniform(cd_min, cd_max)
            
            if random.random() < 0.05:
                cooldown *= random.uniform(2.0, 3.0)
            
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
                self._driver.quit()
            except:
                pass
            self._driver = None
            self._request_count = 0