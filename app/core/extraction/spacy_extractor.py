import spacy
import json
import os
import re
import threading
from typing import Dict, List, Any

from app.config import BASE_APP_DIR
from app.core.log_manager import logger

class SpacyFeatureExtractor:
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    CHIP_MAKERS = {'nvidia', 'amd', 'intel', 'apple'}
    
    VENDORS = {
        'asus', 'msi', 'gigabyte', 'palit', 'sapphire', 'zotac', 'evga', 
        'lenovo', 'hp', 'dell', 'acer', 'samsung', 'lg', 'aoc', 'benq', 
        'kingston', 'adata', 'wd', 'seagate', 'sony', 'huawei', 'honor',
        'xiaomi', 'thunderobot', 'maibenben', 'colorful', 'inno3d', 'pny',
        'machcreator', 'chuwi', 'haier', 'digma', 'machenike'
    }

    SERIES_KEYWORDS = {
        'rtx', 'gtx', 'rx', 'arc', 'titan', 'quadro',
        'ryzen', 'core', 'athron', 'xeon', 'epyc', 'threadripper', 'pentium', 'celeron',
        'i3', 'i5', 'i7', 'i9', 'r3', 'r5', 'r7', 'r9',
        'macbook', 'air', 'pro', 'legion', 'vivobook', 'zenbook', 'rog', 'tuf', 'strix', 
        'ideapad', 'thinkpad', 'nitro', 'predator', 'alienware', 'xps', 'latitude', 
        'inspiron', 'omen', 'victus', 'pavilion', 'envy', 'matebook', 'magicbook',
        'playstation', 'xbox', 'nintendo', 'cosmos', 'gf', 'katana', 'sword', 'pulse'
    }

    NOISE_WORDS = {
        'gaming', 'edition', 'oc', 'overclock', 'ultra', 'pro', 'max', 'plus', 
        'evo', 'x', 'z', 'super', 'ti', 'lhr', 'box', 'oem', 'new', 'used', 
        'white', 'black', 'rgb', 'wifi', 'dvd', 'cd', 'hero', 'master', 'elite',
        'eagle', 'vision', 'trio', 'ventus', 'suprim', 'strix', 'tuf', 'aorus',
        'fatboy', 'nitro', 'pulse', 'mech', 'dual', 'windforce', 'phoenix',
        'phantom', 'gamerock', 'jetstream', 'stormx', 'verto', 'epic', 'extreme',
        'waterforce', 'se', 'xt', 'xtx', 'gddr6', 'gddr6x', 'gddr5', 'ddr4', 'ddr5',
        'ssd', 'hdd', 'nvme', 'sata', 'm2', 'pci', 'express', 'usb', 'hdmi',
        'displayport', 'vga', 'dvi', 'hz', 'mhz', 'ghz', 'inch', 'ips', 'va', 'tn', 'oled'
    }
    
    MODEL_SUFFIXES = {'ti', 'super', 'xt', 'xtx', 'k', 'f', 'kf', 'x', 'x3d', 'h', 'hx', 'u', 'p', 'hs'}

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SpacyFeatureExtractor, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not SpacyFeatureExtractor._initialized:
            with SpacyFeatureExtractor._lock:
                if not SpacyFeatureExtractor._initialized:
                    self._init_model()
                    SpacyFeatureExtractor._initialized = True

    def _init_model(self):
        logger.info("Загрузка NLP модели (ru_core_news_md)...", token="nlp_load")
        try:
            self.nlp = spacy.load("ru_core_news_md")
            self.category_rules = self._load_category_rules()
            logger.success("NLP модель загружена.", token="nlp_load")
        except OSError:
            logger.error("Модель не найдена. Установите: python -m spacy download ru_core_news_md")
            self.nlp = spacy.blank("ru")
            self.category_rules = {}

    def _load_category_rules(self) -> Dict:
        path = os.path.join(os.path.dirname(__file__), "category_rules.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка правил категорий: {e}")
            return {}

    def extract_semantic_data(self, title: str, description: str = "", price: int = 0) -> Dict[str, Any]:
        if not title:
            return self._empty_result()

        clean_title = re.sub(r'[^\w\s\-\.]', ' ', title.lower())
        doc = self.nlp(clean_title)
        tokens = [t for t in doc if not t.is_stop and not t.is_punct and len(t.text) > 1]
        lemmas = [t.lemma_.lower() for t in tokens]

        # 1. Detect Category (with description peeking)
        category = self._detect_category(lemmas, title, description, price)

        # 2. Extract Brands
        brands = self._extract_brands(lemmas)

        # 3. Extract Series/Model
        model_info = self._extract_series_and_model(lemmas, category)

        # 4. Features
        features = self._extract_features_nlp(doc, lemmas)

        # === 5. СПЕЦИАЛЬНАЯ ОБРАБОТКА ДЛЯ СБОРОК ===
        if category == 'PC_BUILD':
            components = self._extract_build_components(title, description)

            # Формируем clean_name из компонентов
            if components:
                parts = []
                if components.get('cpu'):
                    parts.append(f"CPU: {components['cpu'][0]}")
                if components.get('gpu'):
                    parts.append(f"GPU: {components['gpu'][0]}")
                if components.get('ram'):
                    parts.append(f"RAM: {components['ram'][0]}")

                clean_name = " | ".join(parts) if parts else "PC Build"
            else:
                clean_name = "PC Build (Generic)"

            features['components'] = components
        else:
            clean_name = self._generate_clean_name(category, brands, model_info)

        # 6. Keys
        product_key = self._generate_product_key(category, brands, model_info, lemmas)
        cluster_key = self._generate_cluster_key(category, brands, model_info)

        return {
            'category': category,
            'product_key': product_key,
            'cluster_key': cluster_key,
            'entity_type': 'PRODUCT',
            'clean_name': clean_name,
            'brand': brands.get('vendor') or brands.get('chip') or '',
            'model': model_info.get('full_model', ''),
            'features': features,
            'raw_tokens': lemmas
        }

    def _detect_category(self, lemmas: List[str], raw_title: str, description: str = "", price: int = 0) -> str:
        """
        Умное определение категории с разделением весов и жесткими банами.
        """
        raw_text = (raw_title + " " + description[:100]).lower()
        scores = {}

        for cat_name, rules in self.category_rules.items():
            strong_keys = rules.get("strong_keywords", [])
            weak_keys = rules.get("weak_keywords", [])
            banned_keys = rules.get("banned_keywords", [])
            base_priority = rules.get("priority", 10)

            current_score = 0
            is_banned = False

            # 1. Проверка на БАН (Hard Ban)
            for ban_word in banned_keys:
                # Проверяем в леммах И в сыром тексте для надежности
                if ban_word in lemmas or ban_word in raw_text:
                    # Исключение: если это "скупка", но категория ACCESSORY или SERVICE - не баним
                    # Но пока просто жесткий бан
                    is_banned = True
                    break
            
            if is_banned:
                continue

            # 2. Сильные ключи (Strong Keywords) - дают много очков
            for key in strong_keys:
                is_match = False
                if " " in key:
                    if key in raw_text: is_match = True
                elif key in lemmas:
                    is_match = True
                
                if is_match:
                    # УСИЛЕНИЕ ДЛЯ СУЩНОСТЕЙ
                    if cat_name in ['LAPTOP', 'PC_BUILD', 'MONITOR']:
                        current_score += 300  # Было 100. Теперь Ноутбук перевесит 3 упоминания процессора
                    else:
                        current_score += 100

            # 3. Слабые ключи (Weak Keywords) - дают мало очков, только как поддержка
            for key in weak_keys:
                if key in lemmas:
                    current_score += 5

            if current_score > 0:
                # Умножаем на базовый приоритет категории, чтобы LAPTOP (100) побеждал GPU (50) при прочих равных
                scores[cat_name] = current_score + base_priority

        # 4. Эвристика цены (Price Heuristics)
        scores = self._apply_price_heuristics(scores, price)

        if not scores:
            return "MISC"

        # Сортировка по убыванию очков
        best_category = max(scores, key=scores.get)
        
        # 5. Разрешение конфликтов (Tie Breaking)
        # Если очки равны или близки, используем специфическую логику
        if scores.get('PC_BUILD', 0) > 50 and scores.get('PC_BUILD') == scores.get('CASE'):
             return 'PC_BUILD' # Приоритет ПК над корпусом

        return best_category

    def _apply_price_heuristics(self, scores: Dict[str, float], price: int) -> Dict[str, float]:
        """
        Корректировка очков на основе цены.
        Помогает отсеять коробки и аксессуары от реальных товаров.
        """
        if price <= 0:
            return scores

        # Если цена очень низкая (< 1500 руб), это вряд ли рабочий ноутбук или современная видеокарта
        if price < 1500:
            if 'LAPTOP' in scores:
                scores['LAPTOP'] -= 200 # Штраф, скорее всего это запчасть или батарея
            if 'PC_BUILD' in scores:
                scores['PC_BUILD'] -= 200
            
            # А вот для аксессуаров, кулеров и старых GPU это нормальная цена
            if 'ACCESSORY' in scores:
                scores['ACCESSORY'] += 50
            if 'COOLING' in scores:
                scores['COOLING'] += 50
            
            # Для GPU ставим под сомнение, но не убиваем полностью (затычки бывают дешевыми)
            # Но если есть ACCESSORY, даем ему преимущество
            if 'GPU' in scores and 'ACCESSORY' in scores:
                scores['GPU'] -= 50

        # Если цена очень высокая (> 20 000 руб), это вряд ли просто кулер
        if price > 20000:
            if 'COOLING' in scores:
                scores['COOLING'] -= 50
            if 'ACCESSORY' in scores:
                scores['ACCESSORY'] -= 50
            if 'CASE' in scores:
                scores['CASE'] -= 20

        return scores

    def _extract_brands(self, lemmas: List[str]) -> Dict[str, str]:
        brands = {'chip': None, 'vendor': None}
        for lemma in lemmas:
            if lemma in self.CHIP_MAKERS:
                brands['chip'] = lemma
            elif lemma in self.VENDORS:
                if not brands['vendor']:
                    brands['vendor'] = lemma
        return brands

    def _extract_series_and_model(self, lemmas: List[str], category: str) -> Dict[str, str]:
        info = {'series': '', 'model': '', 'full_model': ''}
        used_indices = set()
        
        banned_series = set()
        if category == 'LAPTOP':
            banned_series = {'rtx', 'gtx', 'rx', 'ryzen', 'core', 'intel', 'amd', 'geforce', 'radeon'}

        # Поиск серии
        series_idx = -1
        for i, lemma in enumerate(lemmas):
            if lemma in self.SERIES_KEYWORDS:
                if lemma in banned_series:
                    continue 
                info['series'] = lemma
                series_idx = i
                used_indices.add(i)
                break
        
        # Поиск модели (цифры)
        model_parts = []
        start_search = series_idx + 1 if series_idx != -1 else 0
        
        for i in range(start_search, len(lemmas)):
            token = lemmas[i]
            if i in used_indices or token in self.NOISE_WORDS: continue
            
            # Паттерн модели
            if re.search(r'\d', token):
                if any(x in token for x in ['gb', 'mb', 'tb', 'mhz', 'v', 'w']): continue
                model_parts.append(token)
                used_indices.add(i)
                
                # Суффиксы (Ti, K, H, U)
                if i + 1 < len(lemmas):
                    next_token = lemmas[i+1]
                    if next_token in self.MODEL_SUFFIXES:
                        model_parts.append(next_token)
                        used_indices.add(i+1)
                
                if len(model_parts) >= 1: 
                    if token in ['3', '5', '7', '9'] and len(token) == 1: continue 
                    break
        
        info['model'] = "".join(model_parts)
        parts = []
        if info['series']: parts.append(info['series'])
        if info['model']: parts.append(info['model'])
        info['full_model'] = "".join(parts)
        return info

    def _extract_features_nlp(self, doc, lemmas: List[str]) -> Dict[str, str]:
        features = {}
        for i, token in enumerate(doc):
            if token.like_num:
                if i + 1 < len(doc):
                    next_token = doc[i+1].lemma_.lower()
                    if next_token in ['gb', 'гб', 'tb', 'тб']:
                        features['capacity'] = f"{token.text}{next_token.replace('гб','gb').replace('тб','tb')}"

        condition_keywords = {
            'new': ['новый', 'запечатать', 'new', 'пломба', 'магазин'],
            'used': ['бу', 'б/у', 'использовать'],
            'ideal': ['идеал', 'отличный', 'ideal']
        }
        for state, keys in condition_keywords.items():
            if any(k in lemmas for k in keys):
                features['condition'] = state
                break
        return features

    def _extract_build_components(self, title: str, description: str) -> Dict[str, List[str]]:
        """
        Извлекает компоненты из описания сборки.
        Возвращает dict с найденными GPU, CPU, RAM и т.д.
        """
        if not description or len(description) < 20:
            return {}

        # Объединяем title + первые 500 символов description
        text = f"{title}. {description[:500]}".lower()

        components = {
            'gpu': [],
            'cpu': [],
            'ram': [],
            'storage': []
        }

        # GPU паттерны
        gpu_patterns = [
            r'\b(rtx|gtx|rx|arc)\s*(\d{4}(?:\s?ti|super|xt|xtx)?)\b',
            r'\b(geforce|radeon|nvidia|amd)\s+(rtx|gtx|rx)?\s*(\d{4}(?:\s?ti)?)\b'
        ]

        for pattern in gpu_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                gpu_str = ' '.join(filter(None, match)).upper()
                if gpu_str and gpu_str not in components['gpu']:
                    components['gpu'].append(gpu_str)

        # CPU паттерны
        cpu_patterns = [
            r'\b(ryzen|core)\s+([i579])\s*[-\s]*(\d{4,5}[a-z]{0,3})\b',
            r'\b(i[3579])\s*[-\s]*(\d{4,5}[kf]{0,2})\b',
            r'\b(r[3579])\s+(\d{4}[x]?)\b'
        ]

        for pattern in cpu_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                cpu_str = ' '.join(filter(None, match)).upper()
                if cpu_str and cpu_str not in components['cpu']:
                    components['cpu'].append(cpu_str)

        # RAM
        ram_patterns = [r'\b(\d+)\s*(?:gb|гб)\s+(?:ram|озу|памяти)\b']
        for pattern in ram_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                components['ram'].append(f"{match}GB")

        # Storage
        storage_patterns = [r'\b(\d+)\s*(?:gb|tb|гб|тб)\s+(?:ssd|hdd|nvme)\b']
        for pattern in storage_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                components['storage'].append(match.upper())

        return {k: v for k, v in components.items() if v}

    def _generate_product_key(self, category: str, brands: Dict, model_info: Dict, lemmas: List[str]) -> str:
        """
        Генерирует уникальный ключ продукта.
        """
        cat_lower = category.lower()

        # === СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ СБОРОК ===
        if cat_lower == 'pc_build':
            # Для сборок не создаем детальный ключ, т.к. это набор компонентов
            # Вместо этого - общий ключ по назначению

            # Определяем тип сборки
            build_type = 'generic'

            if any(w in lemmas for w in ['игровой', 'gaming', 'геймерский', 'game']):
                build_type = 'gaming'
            elif any(w in lemmas for w in ['офисный', 'office', 'работа', 'учеба']):
                build_type = 'office'
            elif any(w in lemmas for w in ['рабочая', 'workstation', 'профессиональный']):
                build_type = 'workstation'
            elif any(w in lemmas for w in ['mini', 'мини', 'компактный', 'малый']):
                build_type = 'mini'

            return f"pc_build_{build_type}"

        # === ДЛЯ ОСТАЛЬНЫХ КАТЕГОРИЙ - СТАРАЯ ЛОГИКА ===
        vendor = brands.get('vendor', '')
        chip = brands.get('chip', '')

        # Приоритет: chip > vendor
        brand_part = chip if chip else vendor

        # Модель
        model_part = model_info.get('short_model', '')

        if not brand_part and not model_part:
            return f"{cat_lower}_unknown"

        # Формируем ключ
        parts = [cat_lower]
        if brand_part:
            parts.append(brand_part.lower())
        if model_part:
            parts.append(model_part.lower())

        key = '_'.join(parts)

        # Очистка
        key = re.sub(r'[^\w_]', '', key)
        key = re.sub(r'_+', '_', key)

        return key.strip('_') or f"{cat_lower}_unknown"

    def _generate_cluster_key(self, category: str, brands: Dict, model_info: Dict) -> str:
        parts = [category.lower()]
        
        brand = brands.get('chip') if category in ['GPU', 'CPU'] else brands.get('vendor')
        if brand: parts.append(brand)
        
        if model_info.get('series'):
            parts.append(model_info['series'])
        elif model_info.get('full_model'):
            parts.append(model_info['full_model'][:4])
            
        return "_".join(parts)

    def _generate_clean_name(self, category: str, brands: Dict, model_info: Dict) -> str:
        parts = []
        brand = brands.get('chip') if category in ['GPU', 'CPU'] else brands.get('vendor')
        if brand: parts.append(brand.upper())
        if model_info.get('series'): parts.append(model_info['series'].upper())
        if model_info.get('model'): parts.append(model_info['model'].upper())
        
        if not parts:
            return f"{category} Unknown"
        return " ".join(parts)

    def _empty_result(self):
        return {
            'category': 'MISC',
            'product_key': 'misc_item',
            'cluster_key': 'misc_general',
            'entity_type': 'CATEGORY',
            'clean_name': 'Unknown',
            'features': {}
        }
    
    ### DEBUG
    def extract_semantic_data_with_debug(self, title: str, description: str = "", price: int = 0) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Версия extract_semantic_data с промежуточными данными для диагностики.
        """
        if not title:
            return self._empty_result(), {}

        # Подготовка текста как в основном методе
        clean_title = re.sub(r'[^\w\s\-\.]', ' ', title.lower())
        doc = self.nlp(clean_title)
        tokens = [t for t in doc if not t.is_stop and not t.is_punct and len(t.text) > 1]
        lemmas = [t.lemma_.lower() for t in tokens]
        
        # Сырой текст для поиска фраз
        raw_text_search = (title + " " + description[:100]).lower()

        # Debug данные
        debug_info = {
            'lemmas': lemmas,
            'category_scores': {},
            'matched_keywords': [], # Сюда запишем, какие слова сработали
            'banned_trigger': [],   # Сюда запишем, из-за чего категорию забанило
            'brands_found': {},
            'model_patterns': []
        }

        # 1. Detect Category (вызываем обновленный метод с price)
        category, scores = self._detect_category_with_scores(lemmas, title, description, price)
        debug_info['category_scores'] = scores

        # 2. Extract Brands
        brands = self._extract_brands(lemmas)
        debug_info['brands_found'] = brands

        # 3. Extract Series/Model
        model_info = self._extract_series_and_model(lemmas, category)

        # 4. Features
        features = self._extract_features_nlp(doc, lemmas)

        # 5. Сборки
        if category == 'PC_BUILD':
            components = self._extract_build_components(title, description)
            features['components'] = components
            debug_info['components'] = components
            
            if components:
                parts = []
                if components.get('cpu'): parts.append(f"CPU: {components['cpu'][0]}")
                if components.get('gpu'): parts.append(f"GPU: {components['gpu'][0]}")
                if components.get('ram'): parts.append(f"RAM: {components['ram'][0]}")
                clean_name = " | ".join(parts) if parts else "PC Build"
            else:
                clean_name = "PC Build (Generic)"
        else:
            clean_name = self._generate_clean_name(category, brands, model_info)

        # 6. Keys
        product_key = self._generate_product_key(category, brands, model_info, lemmas)
        cluster_key = self._generate_cluster_key(category, brands, model_info)

        # --- Сбор DEBUG информации о ключевых словах ---
        for cat_name, rules in self.category_rules.items():
            # Проверяем сильные ключи
            for key in rules.get("strong_keywords", []):
                if " " in key:
                    if key in raw_text_search:
                        debug_info['matched_keywords'].append(f"{cat_name} [STRONG]: '{key}'")
                elif key in lemmas:
                    debug_info['matched_keywords'].append(f"{cat_name} [STRONG]: '{key}'")
            
            # Проверяем слабые ключи
            for key in rules.get("weak_keywords", []):
                if key in lemmas:
                    debug_info['matched_keywords'].append(f"{cat_name} [WEAK]: '{key}'")
            
            # Проверяем баны
            for key in rules.get("banned_keywords", []):
                if key in lemmas or key in raw_text_search:
                    debug_info['banned_trigger'].append(f"{cat_name} BANNED by: '{key}'")

        semantic_data = {
            'category': category,
            'product_key': product_key,
            'cluster_key': cluster_key,
            'entity_type': 'PRODUCT',
            'clean_name': clean_name,
            'brand': brands.get('vendor') or brands.get('chip') or '',
            'model': model_info.get('full_model', ''),
            'features': features,
            'raw_tokens': lemmas
        }

        return semantic_data, debug_info

    def _detect_category_with_scores(self, lemmas: List[str], raw_title: str, description: str = "", price: int = 0) -> tuple[str, Dict[str, float]]:
        """
        Версия детектора, возвращающая победителя и таблицу очков для отладки.
        Полностью дублирует логику _detect_category.
        """
        raw_text = (raw_title + " " + description[:100]).lower()
        scores = {}

        for cat_name, rules in self.category_rules.items():
            strong_keys = rules.get("strong_keywords", [])
            weak_keys = rules.get("weak_keywords", [])
            banned_keys = rules.get("banned_keywords", [])
            base_priority = rules.get("priority", 10)

            current_score = 0
            is_banned = False

            # 1. Проверка на БАН
            for ban_word in banned_keys:
                if ban_word in lemmas or ban_word in raw_text:
                    is_banned = True
                    # Для дебага можно записать отрицательный скор, чтобы видеть бан
                    scores[cat_name] = -999.0 
                    break
            
            if is_banned:
                continue

            # 2. Сильные ключи (+100)
            for key in strong_keys:
                is_match = False
                if " " in key:
                    if key in raw_text: is_match = True
                elif key in lemmas:
                    is_match = True
                
                if is_match:
                    # УСИЛЕНИЕ ДЛЯ СУЩНОСТЕЙ
                    if cat_name in ['LAPTOP', 'PC_BUILD', 'MONITOR']:
                        current_score += 300  # Было 100. Теперь Ноутбук перевесит 3 упоминания процессора
                    else:
                        current_score += 100

            # 3. Слабые ключи (+5)
            for key in weak_keys:
                if key in lemmas:
                    current_score += 5

            if current_score > 0:
                scores[cat_name] = current_score + base_priority

        # 4. Эвристика цены
        scores = self._apply_price_heuristics(scores, price)

        if not scores:
            # Если все по нулям, проверяем, нет ли "забаненных" категорий для отчетности
            # Если нет даже забаненных, возвращаем пустой MISC
            return "MISC", scores

        # Ищем победителя (исключая забаненных с -999)
        valid_scores = {k: v for k, v in scores.items() if v > -100}
        
        if not valid_scores:
            best_category = "MISC"
        else:
            best_category = max(valid_scores, key=valid_scores.get)
            
            # 5. Разрешение конфликтов (Tie Breaking)
            if valid_scores.get('PC_BUILD', 0) > 50 and valid_scores.get('PC_BUILD') == valid_scores.get('CASE'):
                 best_category = 'PC_BUILD'

        return best_category, scores