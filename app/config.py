import os
import sys

# --- УПРАВЛЕНИЕ ПУТЯМИ ---

def get_internal_path(relative_path):
    """
    Путь к ВНУТРЕННИМ ресурсам (картинки, дефолтные конфиги).
    Работает и в IDE, и внутри EXE (_MEIPASS).
    """
    try:
        # PyInstaller создает временную папку в _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

def get_user_data_path(relative_path=""):
    """
    Путь к ВНЕШНИМ данным (результаты, настройки, логи).
    Всегда указывает на папку, где лежит сам скрипт или EXE файл.
    """
    if getattr(sys, 'frozen', False):
        # Если запущено как EXE - берем папку, где лежит EXE
        base_path = os.path.dirname(sys.executable)
    else:
        # Если запущено из Python - берем корневую папку проекта
        # (поднимаемся на уровень выше от config.py: app/config.py -> app/ -> root)
        _conf_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.dirname(_conf_dir)
        
    return os.path.join(base_path, relative_path)

# Переопределяем resource_path для совместимости, если он где-то используется напрямую
resource_path = get_internal_path

# --- КОНСТАНТЫ ПУТЕЙ ---

# Базовая директория приложения (рядом с exe)
BASE_APP_DIR = get_user_data_path()

# Папки данных
RESULTS_DIR = os.path.join(BASE_APP_DIR, "results")
MODELS_DIR = os.path.join(BASE_APP_DIR, "models")

# --- КОНСТАНТЫ ПРИЛОЖЕНИЯ ---

# URLs
BASE_URL_MOSCOW = 'https://www.avito.ru/moskva/tovary_dlya_kompyutera/komplektuyuschie-ASgBAgICAUTGB~pm'
BASE_URL_ALL = 'https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie-ASgBAgICAUTGB~pm'

# Browser Settings
CHROME_OPTIONS_ARGS = [
    "--headless=new",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--exclude-switches=enable-automation",
    "--disable-browser-side-navigation",
    "--disable-extensions",
    "--disable-plugins",
    "--disable-popup-blocking",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--dns-prefetch-disable",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-logging",
    "--disable-permissions-api",
    "--ignore-certificate-errors",
    "--disable-features=IsolateOrigins,site-per-process",
    "--window-size=1920,1080",
    "--start-maximized",
]

# User Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]

# Parser
ALL_PAGES_LIMIT = 100

# Delays
MIN_REQUEST_DELAY = 3.0
MAX_REQUEST_DELAY = 7.0
DEFAULT_TIMEOUT = 10

HUMAN_TYPING_MIN_DELAY = 0.05
HUMAN_TYPING_MAX_DELAY = 0.15
HUMAN_TYPING_PAUSE_CHANCE = 0.15
HUMAN_TYPING_PAUSE_DURATION = (0.3, 0.8)

RANDOM_SCROLL_CHANCE = 0.3
RANDOM_MOUSE_MOVE_CHANCE = 0.2

COOLDOWN_EVERY_MIN = 8
COOLDOWN_EVERY_MAX = 12
COOLDOWN_DURATION_MIN = 10.0
COOLDOWN_DURATION_MAX = 20.0

# LLM Settings
AI_CTX_SIZE = 8192
AI_GPU_LAYERS = -1
AI_SERVER_PORT = 51134
AI_BACKEND_PREFERENCE = "auto"
DEFAULT_MODEL_NAME = "google_gemma-3-4b-it-Q8_0.gguf"
DEFAULT_MODEL_REPO = "bartowski/google_gemma-3-4b-it-GGUF"