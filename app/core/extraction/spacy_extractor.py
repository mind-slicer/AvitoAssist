import spacy
import json
import os
import re
import threading
from typing import Dict, List, Any, Tuple

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
        'machcreator', 'chuwi', 'haier', 'digma', 'osio', 'infinix', 'tecno',
        'machenike', 'irbis', 'hasee'
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
        """
        Чистый метод для продакшена. Вызывает полный анализ, но возвращает только результат.
        """
        result, _ = self.extract_semantic_data_with_debug(title, description, price)
        return result

    def extract_semantic_data_with_debug(self, title: str, description: str = "", price: int = 0) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Единственный метод, содержащий логику парсинга.
        Возвращает (semantic_data, debug_info).
        """
        if not title:
            return self._empty_result(), {}

        # 1. Предобработка
        clean_title = re.sub(r'[^\w\s\-\.]', ' ', title.lower())
        doc = self.nlp(clean_title)
        tokens = [t for t in doc if not t.is_stop and not t.is_punct and len(t.text) > 1]
        lemmas = [t.lemma_.lower() for t in tokens]

        # Подготовка текста для поиска ключевых слов (заголовок + начало описания)
        raw_text_search = (title + " " + description[:100]).lower()

        debug_info = {
            'lemmas': lemmas,
            'category_scores': {},
            'matched_keywords': [],
            'banned_trigger': [],
            'brands_found': {},
            'model_patterns': []
        }

        # 2. Определение категории
        category, scores = self._detect_category_with_scores(lemmas, title, description, price)
        debug_info['category_scores'] = scores

        # 3. Извлечение брендов
        brands = self._extract_brands(lemmas, raw_text_search)
        debug_info['brands_found'] = brands

        # 4. Извлечение модели
        model_info = self._extract_series_and_model(lemmas, category)

        # 5. Извлечение характеристик
        features = self._extract_features_nlp(doc, lemmas)

        # 6. Специфика PC_BUILD
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
            clean_name = self._generate_clean_name(category, brands, model_info, lemmas)

        # 7. Генерация ключей
        product_key = self._generate_product_key(category, brands, model_info, lemmas)
        cluster_key = self._generate_cluster_key(category, brands, model_info)

        # 8. Сбор отладочной информации о сработавших правилах (для логов)
        if hasattr(self, 'category_rules'):
            for cat_name, rules in self.category_rules.items():
                for key in rules.get("strong_keywords", []):
                    if " " in key:
                        if key in raw_text_search:
                            debug_info['matched_keywords'].append(f"{cat_name} [STRONG]: '{key}'")
                    elif key in lemmas:
                        debug_info['matched_keywords'].append(f"{cat_name} [STRONG]: '{key}'")

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
        VERSION 5 (GOLD MASTER):
        1. Service Enforcement: 'Скупка' теперь жестко банит категории железа (GPU/CPU).
        2. Absolute Desktop Guard: Слово 'видеокарта' в заголовке мгновенно убивает LAPTOP.
        3. Accessory Boost: Если найден модификатор (райзер), ACCESSORY побеждает даже без сильных ключей.
        """
        raw_text_full = (raw_title + " " + description[:200]).lower()
        lemmas_set = set(lemmas)
        scores = {}

        # 1. Списки ключевых слов
        hardware_cats = {'GPU', 'CPU', 'MOTHERBOARD', 'RAM', 'STORAGE', 'PSU', 'LAPTOP', 'PC_BUILD', 'MONITOR', 'CASE'}
        
        accessory_modifiers = {
            'коробка', 'box', 'упаковка', 'держатель', 'подставка', 'кронштейн', 'стойка',
            'кабель', 'шлейф', 'переходник', 'удлинитель', 'мост', 'bridge', 'райзер', 'riser',
            'кулер', 'cooler', 'fan', 'вентилятор', 'радиатор', 'кожух', 'вертушка', 'охлаждение',
            'термопрокладки', 'термопаста', 'винты', 'крепление'
        }
        
        service_modifiers = {
            'скупка', 'выкуп', 'куплю', 'покупка', 'обмен', 'ремонт', 'диагностика', 
            'trade-in', 'трейд-ин', 'настройка', 'чистка', 'обслуживание', 'мастер', 'услуги',
            'трафарет', 'прогар', 'отвал', 'аренда', 'прокат'
        }

        # 2. Базовый подсчет (Standard Scoring)
        for cat_name, rules in self.category_rules.items():
            strong_keys = rules.get("strong_keywords", [])
            weak_keys = rules.get("weak_keywords", [])
            banned_keys = rules.get("banned_keywords", [])
            base_priority = rules.get("priority", 10)

            current_score = 0
            strong_match_count = 0

            # Strong Matches
            for strong_word in strong_keys:
                if " " not in strong_word:
                    if strong_word in lemmas_set:
                        strong_match_count += 1
                        current_score += 100
                else:
                    if re.search(r'\b' + re.escape(strong_word) + r'\b', raw_text_full):
                        strong_match_count += 1
                        current_score += 120

            # Banned Keywords Check
            is_banned = False
            for ban_word in banned_keys:
                if " " not in ban_word:
                    if ban_word in lemmas_set: 
                        is_banned = True; break
                elif strong_match_count == 0:
                    if re.search(r'\b' + re.escape(ban_word) + r'\b', raw_text_full):
                        is_banned = True; break
            
            if is_banned:
                scores[cat_name] = -1000.0
                continue

            # Weak Matches
            for weak_word in weak_keys:
                if " " not in weak_word:
                    if weak_word in lemmas_set: current_score += 30
                else:
                    if re.search(r'\b' + re.escape(weak_word) + r'\b', raw_text_full): current_score += 35

            if current_score > 0:
                scores[cat_name] = current_score + base_priority
            elif cat_name == 'SERVICE': # Service has default priority
                scores[cat_name] = base_priority

        # 3. Price Heuristics
        scores = self._apply_price_heuristics(scores, price, lemmas_set, raw_text_full)

        # 4. CONFLICT RESOLUTION (The "Brain" of the logic)
        
        has_accessory_mod = not accessory_modifiers.isdisjoint(lemmas_set)
        has_service_mod = not service_modifiers.isdisjoint(lemmas_set)
        
        # A. ACCESSORY GUARD: Если есть "Коробка/Райзер" -> Убиваем железо, бустим аксессуары
        if has_accessory_mod:
            for cat in hardware_cats:
                if cat not in ['COOLING', 'CASE', 'MONITOR']: 
                    if scores.get(cat, 0) > 0: scores[cat] -= 500.0
            
            # Force enable ACCESSORY if it was weak
            if scores.get('ACCESSORY', -1000) < 100:
                scores['ACCESSORY'] = 200.0
            else:
                scores['ACCESSORY'] += 200.0

        # B. SERVICE GUARD: Если есть "Скупка/Ремонт" -> Убиваем ВСЁ железо
        if has_service_mod:
            for cat in hardware_cats:
                # Разрешаем "запчасти" для некоторых категорий, но скупка убивает всё
                if 'скупка' in lemmas_set or 'куплю' in lemmas_set or 'выкуп' in lemmas_set:
                    scores[cat] = -1000.0
                else:
                    # Для "ремонта" просто сильно снижаем
                    if scores.get(cat, 0) > 0: scores[cat] -= 400.0
            
            scores['SERVICE'] = scores.get('SERVICE', 0) + 300.0

        # C. REVERSE SERVICE TRAP: Если найдено железо, и НЕТ слов сервиса -> Убиваем SERVICE
        # (Спасает дешевые видеокарты от попадания в Service)
        is_hardware_strong = any(scores.get(c, 0) > 20 for c in hardware_cats)
        if is_hardware_strong and not has_service_mod:
            scores['SERVICE'] = -500.0

        # D. ABSOLUTE DESKTOP GUARD: "Видеокарта" != "Ноутбук"
        # Если слово "видеокарта" есть в заголовке, это НЕ ноутбук. Точка.
        if 'видеокарта' in lemmas_set or 'videocard' in lemmas_set:
            scores['LAPTOP'] = -1000.0
            # Также бустим GPU, если он был сомнителен
            if scores.get('GPU', 0) > -100:
                scores['GPU'] += 50.0

        # E. LAPTOP vs GPU TIE-BREAKER
        # Если все еще спорно (например MSI Gaming X), проверяем контекст
        if scores.get('LAPTOP', 0) > 0 and scores.get('GPU', 0) > 0:
            diff = abs(scores['LAPTOP'] - scores['GPU'])
            if diff < 150:
                # Если есть явные признаки ноута (экран, батарея...)
                if re.search(r'\b(1[3-7])[\.,]\d["\']?', raw_title): 
                    scores['GPU'] -= 500.0
                # Если есть явные признаки GPU (GB, GDDR) и нет слова "ноутбук"
                elif 'gddr' in raw_text_full and 'ноутбук' not in lemmas_set:
                    scores['LAPTOP'] -= 500.0

        # F. LAPTOP vs CPU TIE-BREAKER
        # Если побеждает CPU, но есть признаки ноутбука (экран, батарея, вендор ноута)
        if scores.get('CPU', 0) > scores.get('LAPTOP', 0) and scores.get('LAPTOP', 0) > 0:
            # Если есть размер экрана (15.6, 17.3 и т.д.) - это точно ноут, а не проц
            if re.search(r'\b(1[3-7])[\.,]\d["\']?', raw_title):
                scores['CPU'] -= 500.0
            # Если цена слишком высока для старого проца (> 15000), и это не топовый i9/Ryzen9
            elif price > 15000 and 'i9' not in lemmas_set and 'threadripper' not in lemmas_set:
                 # Эвристика: дорогой "i5" без слов "процессор" часто оказывается ноутбуком
                 if 'процессор' not in lemmas_set and 'cpu' not in lemmas_set:
                     scores['LAPTOP'] += 100.0

        # 5. Final Selection
        valid_scores = {k: v for k, v in scores.items() if v > -500}
        if not valid_scores: return "MISC", scores
        
        best_category = max(valid_scores, key=valid_scores.get)
        return best_category, scores

    def _apply_price_heuristics(self, scores: Dict[str, float], price: int, lemmas_set: set, raw_text: str) -> Dict[str, float]:
        if price <= 0:
            return scores

        # Проверка явных маркеров состояния
        broken_markers = {'запчасти', 'разбор', 'неисправн', 'донор', 'труп', 'ремонт', 'артефакт', 'отвал', 'сломан'}
        accessory_markers = {'кулер', 'вентилятор', 'охлаждение', 'стойка', 'подставка', 'наклейка', 'чехол', 'коврик'}
        
        is_broken = any(marker in lemmas_set or marker in raw_text for marker in broken_markers)
        is_accessory = any(marker in lemmas_set or marker in raw_text for marker in accessory_markers)

        # Низкая цена (< 1500 руб)
        if price < 1500:
            # Если явно указано "на запчасти" или аксессуар - не трогаем категорию
            if is_broken or is_accessory:
                if 'ACCESSORY' in scores:
                    scores['ACCESSORY'] += 150
                if 'COOLING' in scores:
                    scores['COOLING'] += 100
                # Снижаем LAPTOP/PC_BUILD, но не убиваем
                if 'LAPTOP' in scores:
                    scores['LAPTOP'] -= 100
                if 'PC_BUILD' in scores:
                    scores['PC_BUILD'] -= 100
            else:
                # Нет явных маркеров - мягкое снижение для дорогих категорий
                if 'LAPTOP' in scores:
                    scores['LAPTOP'] -= 200
                if 'PC_BUILD' in scores:
                    scores['PC_BUILD'] -= 200
                if 'ACCESSORY' in scores:
                    scores['ACCESSORY'] += 100

            # GPU за 500р может быть ретро-картой или трупом
            if 'GPU' in scores:
                if is_broken:
                    scores['GPU'] -= 50  # Небольшое снижение
                else:
                    scores['GPU'] -= 30  # Минимальное снижение

        # Очень высокая цена (> 25 000 руб)
        if price > 25000:
            if 'COOLING' in scores:
                scores['COOLING'] -= 150
            if 'ACCESSORY' in scores:
                scores['ACCESSORY'] -= 150
            if 'LAPTOP' in scores:
                scores['LAPTOP'] += 100
            if 'PC_BUILD' in scores:
                scores['PC_BUILD'] += 80
            if 'GPU' in scores and price < 80000:
                scores['GPU'] += 30
            elif 'GPU' in scores and price >= 120000:
                scores['GPU'] -= 50

        if 20000 <= price <= 60000:
            # Проверяем наличие типичных маркеров ноутбука
            has_screen_size = bool(re.search(r'\d{2}\.\d', raw_text))  # 15.6, 17.3
            has_cpu_mention = any(x in lemmas_set for x in ['core', 'ryzen', 'i5', 'i7', 'r5', 'r7'])
            has_ram_mention = 'ram' in raw_text or 'озу' in raw_text

            if has_screen_size and (has_cpu_mention or has_ram_mention):
                if 'LAPTOP' in scores:
                    scores['LAPTOP'] += 80  # Сильный буст
                if 'GPU' in scores:
                    scores['GPU'] -= 40  # Снижаем вероятность

        return scores

    def _extract_brands(self, lemmas: List[str], raw_text: str = "") -> Dict[str, str]:
        """
        ИСПРАВЛЕННАЯ: vendor имеет приоритет над chipmaker для контекста ноутбуков.
        """
        brands = {'chip': None, 'vendor': None}

        # Сначала ищем vendor (производитель устройства)
        for lemma in lemmas:
            if lemma in self.VENDORS:
                brands['vendor'] = lemma
                break  # Берем первый найденный
            
        # Затем chipmaker (производитель чипа)
        for lemma in lemmas:
            if lemma in self.CHIP_MAKERS:
                brands['chip'] = lemma
                break
            
        # Дополнительно ищем составные бренды в raw_text
        if raw_text:
            compound_brands = {
                'geforce': 'nvidia',
                'radeon': 'amd',
                'iris': 'intel'
            }
            for keyword, chip in compound_brands.items():
                if keyword in raw_text and not brands['chip']:
                    brands['chip'] = chip

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
            if i in used_indices or token in self.NOISE_WORDS:
                continue

            # Паттерн модели
            if re.search(r'\d', token):
                if any(x in token for x in ['gb', 'mb', 'tb', 'mhz', 'v', 'w']):
                    continue

                model_parts.append(token)
                used_indices.add(i)

                # Суффиксы (Ti, K, H, U)
                if i + 1 < len(lemmas):
                    next_token = lemmas[i+1]
                    if next_token in self.MODEL_SUFFIXES:
                        model_parts.append(next_token)
                        used_indices.add(i+1)

                if len(model_parts) >= 1:
                    if token in ['3', '5', '7', '9'] and len(token) == 1:
                        continue
                    break

        info['model'] = "".join(model_parts)

        parts = []
        if info['series']:
            parts.append(info['series'])
        if info['model']:
            parts.append(info['model'])
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
            'ideal': ['идеал', 'отличный', 'ideal'],
            'for_parts': ['запчасти', 'разбор', 'неисправн', 'донор', 'труп', 'ремонт', 'артефакт', 'отвал']
        }

        found_cond = False
        for state, keys in condition_keywords.items():
            if any(k in lemmas for k in keys):
                features['condition'] = state
                found_cond = True
                break

        # Если не нашли по леммам, ищем фразы для "на запчасти" в сыром тексте (для надежности)
        if not found_cond:
            raw = doc.text.lower()
            if 'на запчасти' in raw or 'под восстановление' in raw:
                features['condition'] = 'for_parts'

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
        ИСПРАВЛЕННАЯ генерация product_key.
        Решает проблему коллизий и улучшает fallback.
        """
        cat_lower = category.lower()

        if cat_lower == 'pc_build':
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

        vendor = brands.get('vendor', '')
        chip = brands.get('chip', '')
        series = model_info.get('series', '')

        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Умный fallback бренда
        if not chip and not vendor and series:
            if series in ['rtx', 'gtx', 'geforce', 'titan']:
                chip = 'nvidia'
            elif series in ['rx', 'radeon']:
                chip = 'amd'
            elif series in ['core', 'pentium', 'celeron', 'xeon', 'arc']:
                chip = 'intel'
            elif series in ['ryzen', 'athlon', 'threadripper', 'epyc']:
                chip = 'amd'

        # Приоритет: chip > vendor (для железа)
        brand_part = chip if chip else vendor

        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Нормализация модели
        model_part = model_info.get('model', '')
        if not model_part:
            model_part = model_info.get('series', '')

        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Улучшенный fallback
        # Если нет бренда И модели, пытаемся создать уникальный ключ из лемм
        if not brand_part and not model_part:
            # Ищем первое существенное слово (не из NOISE_WORDS)
            significant_word = None
            for lemma in lemmas[:10]:  # Проверяем первые 10 лемм (было 5)
                if lemma not in self.NOISE_WORDS and len(lemma) > 2:  # Было > 3
                    # НОВОЕ: Пропускаем чистые числа
                    if not lemma.isdigit():
                        significant_word = lemma
                        break
                    
            if significant_word:
                normalized = re.sub(r'[^a-z0-9]', '', significant_word.lower())
                return f"{cat_lower}_{normalized}"
            else:
                # Абсолютный fallback - добавляем хеш для уникальности
                import hashlib
                hash_suffix = hashlib.md5(''.join(lemmas[:5]).encode()).hexdigest()[:6]
                return f"{cat_lower}_unknown_{hash_suffix}"

        # Формируем ключ
        parts = [cat_lower]
        
        if brand_part:
            # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Нормализация с сохранением разделителей
            # Заменяем все не-буквенно-цифровые символы на пустоту, но сначала заменяем разделители на _
            normalized_brand = re.sub(r'[-\s]+', '_', brand_part.lower())
            normalized_brand = re.sub(r'[^a-z0-9_]', '', normalized_brand)
            normalized_brand = re.sub(r'_+', '_', normalized_brand).strip('_')
            parts.append(normalized_brand)

        if model_part:
            # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Нормализация модели с сохранением суффиксов
            # "RTX 4090 Ti" -> "rtx4090ti", "RTX-4090" -> "rtx4090"
            # Сначала убираем пробелы и дефисы
            normalized_model = re.sub(r'[\s-]+', '', model_part.lower())
            # Затем убираем все остальное кроме букв и цифр
            normalized_model = re.sub(r'[^a-z0-9]', '', normalized_model)
            parts.append(normalized_model)

        key = '_'.join(parts)
        key = re.sub(r'[^\w_]', '', key)
        key = re.sub(r'_+', '_', key)

        if key.endswith('_'):
            if cat_lower in ['service', 'accessory', 'misc']:
                import hashlib
                title_hash = hashlib.md5(' '.join(lemmas[:5]).encode()).hexdigest()[:6]
                key = f"{cat_lower}_{title_hash}"

        return key.strip('_') or f"{cat_lower}_item"

    def _generate_cluster_key(self, category: str, brands: Dict, model_info: Dict) -> str:
        parts = [category.lower()]

        brand = brands.get('chip') if category in ['GPU', 'CPU'] else brands.get('vendor')
        if brand:
            parts.append(brand)

        if model_info.get('series'):
            parts.append(model_info['series'])
        elif model_info.get('full_model'):
            parts.append(model_info['full_model'][:4])

        return "_".join(parts)

    def _generate_clean_name(self, category: str, brands: Dict, model_info: Dict, lemmas: List[str] = None) -> str:
        """
        ИСПРАВЛЕННАЯ генерация clean_name.
        Более информативные имена для элементов без бренда.
        """
        parts = []

        brand = brands.get('chip') if category in ['GPU', 'CPU'] else brands.get('vendor')
        if brand:
            parts.append(brand.upper())

        if model_info.get('series'):
            parts.append(model_info['series'].upper())
        if model_info.get('model'):
            parts.append(model_info['model'].upper())

        if not parts:
            # Берем первые значимые слова (не NOISE_WORDS)
            meaningful_words = []
            for lemma in lemmas[:15]:  # Проверяем первые 15 лемм
                if lemma not in self.NOISE_WORDS and len(lemma) > 2 and not lemma.isdigit():
                    meaningful_words.append(lemma.upper())
                    if len(meaningful_words) >= 3:
                        break
                    
            if meaningful_words:
                return f"{category} ({' '.join(meaningful_words)})"

            return f"{category} (Unknown Model)"

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