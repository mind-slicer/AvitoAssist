import os
import sys


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
    "--disable-web-security",
    
    "--dns-prefetch-disable",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-logging",
    "--disable-permissions-api",
    
    "--ignore-certificate-errors",
    "--ignore-ssl-errors",
    "--disable-features=IsolateOrigins,site-per-process",
    
    "--disk-cache-size=1",
    "--media-cache-size=1",
    "--disable-application-cache"
]

# User Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
]

# Parser
ALL_PAGES_LIMIT = 100

# Delays
MIN_REQUEST_DELAY = 1.5
MAX_REQUEST_DELAY = 3.5
DEFAULT_TIMEOUT = 10

def resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except Exception:
        if getattr(sys, 'frozen', False): base_path = os.path.dirname(sys.executable)
        else: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if getattr(sys, 'frozen', False):
    BASE_APP_DIR = os.path.dirname(sys.executable)
else:
    _conf_dir = os.path.dirname(os.path.abspath(__file__))
    BASE_APP_DIR = os.path.dirname(_conf_dir)

# JSON results
RESULTS_DIR = os.path.join(BASE_APP_DIR, "results")

# LLM Settings
AI_CTX_SIZE = 8192
AI_GPU_LAYERS = -1
AI_SERVER_PORT = 51134
AI_BACKEND_PREFERENCE = "auto"
MODELS_DIR = os.path.join(BASE_APP_DIR, "models")
DEFAULT_MODEL_NAME = "google_gemma-3-4b-it-Q8_0.gguf"
DEFAULT_MODEL_REPO = "bartowski/google_gemma-3-4b-it-GGUF"