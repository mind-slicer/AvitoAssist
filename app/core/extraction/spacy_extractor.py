import spacy
import json
import os
import re
import threading
import hashlib
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
        'machenike', 'irbis', 'hasee', 'yeston', 'afox', 'biostar', 'gainward',
        'leadtek', 'sparkle', 'his', 'xfx', 'powercolor', 'albatron', 'galaxy', 'kfa2',
        'titan', 'mucai', 'sunwind', 'dexp', 'lian li', 'nzxt', 'fractal', 'zalman'
    }

    SERIES_KEYWORDS = {
        'rtx', 'gtx', 'rx', 'arc', 'titan', 'quadro',
        'ryzen', 'core', 'athron', 'xeon', 'epyc', 'threadripper', 'pentium', 'celeron',
        'i3', 'i5', 'i7', 'i9', 'r3', 'r5', 'r7', 'r9',
        'macbook', 'air', 'pro', 'legion', 'vivobook', 'zenbook', 'rog', 'tuf', 'strix',
        'ideapad', 'thinkpad', 'nitro', 'predator', 'alienware', 'xps', 'latitude',
        'inspiron', 'omen', 'victus', 'pavilion', 'envy', 'matebook', 'magicbook',
        'playstation', 'xbox', 'nintendo', 'cosmos', 'gf', 'katana', 'sword', 'pulse',
        'agp', 's3', 'tnt2', 'riva', 'rage', 'voodoo', 'matrox', 'fx', 'hd', 'r7', 'r9'
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
        result, _ = self.extract_semantic_data_with_debug(title, description, price)
        return result

    def extract_semantic_data_with_debug(self, title: str, description: str = "", price: int = 0) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        if not title:
            return self._empty_result(), {}

        # 1. Предобработка
        clean_title = re.sub(r'[^\w\s\-\.\+]', ' ', title.lower())
        doc = self.nlp(clean_title)
        tokens = [t for t in doc if not t.is_stop and not t.is_punct and len(t.text) > 1]
        lemmas = [t.lemma_.lower() for t in tokens]

        raw_text_search = (title + " " + description[:100]).lower()

        debug_info = {
            'lemmas': lemmas,
            'category_scores': {},
            'matched_keywords': [],
            'banned_trigger': [],
            'brands_found': {},
            'model_patterns': []
        }

        # 2. Определение категории (НОВАЯ ЛОГИКА WATERFALL)
        category, scores = self._detect_category_with_scores(lemmas, title, description, price)
        debug_info['category_scores'] = scores

        # 3. Извлечение брендов
        brands = self._extract_brands(lemmas, raw_text_search)
        debug_info['brands_found'] = brands

        # 4. Извлечение модели
        model_info = self._extract_series_and_model(lemmas, category)
        if not model_info['full_model']:
            # Fallback patterns
            model_patterns = [
                r'\b([A-Z]{0,3}\d{2,4}[A-Z]{0,3})\b',
                r'\b(VER\d{3}[A-Z]{0,5})\b',
                r'\b(REV[\s\.]?\d+\.\d+)\b',
            ]
            for pattern in model_patterns:
                match = re.search(pattern, title.upper())
                if match:
                    extracted_model = match.group(1).replace(' ', '').replace('.', '')
                    if len(extracted_model) > 3:
                        model_info['full_model'] = extracted_model.lower()
                        for keyword in self.SERIES_KEYWORDS:
                            if keyword in lemmas:
                                model_info['series'] = keyword
                                break
                        break

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
                clean_name = " | ".join(parts) if parts else "PC Build"
            else:
                clean_name = "PC Build (Generic)"
        else:
            clean_name = self._generate_clean_name(category, brands, model_info, lemmas)

        # 7. Генерация ключей
        product_key = self._generate_product_key(category, brands, model_info, lemmas)
        cluster_key = self._generate_cluster_key(category, brands, model_info)

        # Отладка
        if hasattr(self, 'category_rules'):
            # Просто для информации, какая категория какие слова нашла бы
            pass

        brand_final = brands.get('vendor') or brands.get('chip') or ''
        # Бренд по серии
        if not brand_final and model_info.get('series'):
            series = model_info['series'].lower()
            if series in ['rtx', 'gtx', 'geforce', 'titan', 'quadro']:
                brand_final = 'nvidia'
            elif series in ['rx', 'radeon', 'hd']:
                brand_final = 'amd'
            elif series in ['core', 'pentium', 'celeron', 'xeon', 'arc']:
                brand_final = 'intel'
            elif series in ['ryzen', 'athlon', 'threadripper', 'epyc']:
                brand_final = 'amd'

        model_final = model_info.get('full_model', '')

        semantic_data = {
            'category': category,
            'product_key': product_key,
            'cluster_key': cluster_key,
            'entity_type': 'ENTITY_TYPE',
            'clean_name': clean_name,
            'brand': brand_final,
            'model': model_final,
            'features': features,
            'raw_tokens': lemmas
        }

        return semantic_data, debug_info

    def _detect_category_with_scores(self, lemmas: List[str], raw_title: str, description: str = "", price: int = 0) -> tuple[str, Dict[str, float]]:
        """
        Waterfall/Cascade categorization logic.
        Priority: Service > Container (Laptop/PC/Monitor) > Modifier (Start of title) > Bundle > Components.
        """
        raw_text_full = (raw_title + " " + description[:100]).lower()
        lemmas_set = set(lemmas)
        scores = {}

        # --- PHASE 1: SERVICE DETECTOR ---
        rent_keywords = {'аренда', 'сдам', 'прокат', 'скупка', 'ремонт', 'обслуживание', 'диагностика', 'выкуп'}
        if not rent_keywords.isdisjoint(lemmas_set):
            return 'SERVICE', {'SERVICE': 1000.0}

        # --- PHASE 2: GPU/ACC FORCED START ---
        clean_start = raw_title.strip().lower()
        gpu_starters = ('видеокарта', 'videocard', 'gpu', 'видюха')
        
        # Если начинается с "Видеокарта...", это точно не Ноутбук, не Сборка и не Монитор
        if clean_start.startswith(gpu_starters):
            # Но проверяем, не на запчасти ли это (тогда Condition For Parts, но категория все равно GPU)
            # Или это "Видеокарта... кулер" (тогда Cooling)
            if 'кулер' in clean_start or 'вентилятор' in clean_start:
                 return 'COOLING', {'COOLING': 2000.0}
            return 'GPU', {'GPU': 2000.0}

        # --- PHASE 3: HIGH-LEVEL CONTAINER DETECTOR ---
        # 1. Laptop
        # TRINITY CHECK: Brand + CPU + GPU = Laptop (e.g. "Lenovo i5 RTX 2060")
        laptop_brands = {'asus', 'acer', 'hp', 'dell', 'lenovo', 'msi', 'honor', 'huawei', 'thunderobot', 'machenike', 'maibenben'}
        has_laptop_brand = not laptop_brands.isdisjoint(lemmas_set)
        has_cpu_kw = any(x in lemmas_set for x in ['core', 'ryzen', 'i5', 'i7', 'i3', 'intel', 'amd'])
        has_gpu_kw = any(x in lemmas_set for x in ['rtx', 'gtx', 'geforce'])
        
        if has_laptop_brand and has_cpu_kw and has_gpu_kw:
             return 'LAPTOP', {'LAPTOP': 1500.0}

        laptop_strong = self.category_rules['LAPTOP']['strong_keywords']
        if any(kw in lemmas_set for kw in laptop_strong) or any(kw in raw_text_full for kw in laptop_strong if len(kw)>4):
            # Guard: check for spare parts
            parts_ban = self.category_rules['LAPTOP']['banned_keywords']
            is_part = False
            for part in parts_ban:
                if part in raw_text_full:
                    is_part = True
                    break
            if not is_part:
                return 'LAPTOP', {'LAPTOP': 1000.0}

        # 2. Monitor
        monitor_strong = self.category_rules['MONITOR']['strong_keywords']
        if any(kw in lemmas_set for kw in monitor_strong):
             if 'матрица' not in lemmas_set and 'разбита' not in lemmas_set:
                 return 'MONITOR', {'MONITOR': 1000.0}

        # 3. PC Build
        pc_strong = self.category_rules['PC_BUILD']['strong_keywords']
        if any(kw in raw_text_full for kw in pc_strong):
            return 'PC_BUILD', {'PC_BUILD': 1000.0}
        
        # --- PHASE 4: MODIFIER / START-OF-STRING DETECTOR ---
        
        # 1. Accessory Starters
        acc_starters = ('коробка', 'держатель', 'кабель', 'крепление', 'подставка', 'переходник', 'райзер', 'планка', 'мост', 'шлейф', 'заглушка', 'винты')
        if clean_start.startswith(acc_starters):
            return 'ACCESSORY', {'ACCESSORY': 2000.0}
            
        # 2. Cooling Starters
        cool_starters = ('кулер', 'вентилятор', 'радиатор', 'охлаждение', 'сво', 'водянка')
        if clean_start.startswith(cool_starters):
            return 'COOLING', {'COOLING': 2000.0}

        # --- PHASE 5: BUNDLE / COMBO DETECTOR ---
        is_bundle = self._detect_bundle(lemmas_set, raw_title)
        if is_bundle:
            return 'PC_BUILD', {'PC_BUILD': 800.0}

        # --- PHASE 6: COMPONENT SCORING (The "Iron" Phase) ---
        hardware_cats = ['GPU', 'CPU', 'MOTHERBOARD', 'RAM', 'STORAGE', 'PSU', 'CASE', 'COOLING', 'ACCESSORY']
        
        for cat_name in hardware_cats:
            rules = self.category_rules.get(cat_name, {})
            strong_keys = rules.get("strong_keywords", [])
            banned_keys = rules.get("banned_keywords", [])
            base_priority = rules.get("priority", 10)

            # Banned Check (Strict)
            is_banned = False
            for ban in banned_keys:
                if ban in raw_text_full: # Strict substring check
                    is_banned = True
                    break
            
            if is_banned:
                scores[cat_name] = -1000.0
                continue

            # Scoring
            score = 0
            for kw in strong_keys:
                # Strong score if in TITLE
                if kw in lemmas_set:
                    score += 100
                # Weak score if ONLY in DESCRIPTION
                elif len(kw) > 3 and kw in raw_text_full:
                    score += 20
            
            # Special logic for old GPUs (GT 220, etc)
            if cat_name == 'GPU' and score > 0:
                score += 50

            if score > 0:
                scores[cat_name] = score + base_priority

        # --- PHASE 7: FINAL CONFLICT RESOLUTION ---
        
        # 1. GPU PROTECTION: If GPU is found, Cooling and Accessory die.
        if scores.get('GPU', 0) > 0:
             scores['COOLING'] = -1000.0
             scores['ACCESSORY'] = -1000.0
             scores['MONITOR'] = -1000.0
             scores['PSU'] = -1000.0

        # 2. CPU vs GPU conflict (e.g. "Intel Core i3... + GTX 1060") -> PC Build
        if scores.get('CPU', 0) > 0 and scores.get('GPU', 0) > 0 and scores.get('MOTHERBOARD', 0) > 0:
             return 'PC_BUILD', {'PC_BUILD': 500.0}

        # 3. PSU vs Accessory (Cable)
        if scores.get('PSU', 0) > 0:
             scores['ACCESSORY'] = -100.0

        # Select winner
        valid_scores = {k: v for k, v in scores.items() if v > 0}
        if not valid_scores:
            return "MISC", scores
            
        best_category = max(valid_scores, key=valid_scores.get)
        return best_category, scores

    def _detect_bundle(self, lemmas_set: set, raw_title: str) -> bool:
        """Detects combo kits like 'Motherboard + CPU + RAM'"""
        has_cpu = any(x in lemmas_set for x in ['cpu', 'процессор', 'xeon', 'i3', 'i5', 'i7', 'ryzen'])
        has_mobo = any(x in lemmas_set for x in ['материнская', 'плата', 'motherboard', 'x79', 'x99', 'b450', 'b550'])
        has_ram = any(x in lemmas_set for x in ['ram', 'память', 'озу', 'ddr4', 'ddr3'])
        
        if (has_cpu and has_mobo) or (has_mobo and has_ram and has_cpu):
            return True
            
        bundle_keywords = ['комплект', 'связка', 'сборка на', 'тушка', 'основа', 'набор']
        if any(bk in raw_title.lower() for bk in bundle_keywords):
            if has_cpu or has_mobo or has_ram:
                return True
                
        return False

    def _extract_brands(self, lemmas: List[str], raw_text: str = "") -> Dict[str, str]:
        brands = {'chip': None, 'vendor': None}

        for lemma in lemmas:
            if lemma in self.VENDORS:
                brands['vendor'] = lemma
                break 
            
        for lemma in lemmas:
            if lemma in self.CHIP_MAKERS:
                brands['chip'] = lemma
                break
            
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

    def _extract_series_and_model(self, lemmas: List[str], category: str) -> Dict:
        series = ""
        model = ""
        full_model = ""

        for keyword in self.SERIES_KEYWORDS:
            if keyword in lemmas:
                series = keyword
                break
            
        for lemma in lemmas:
            if re.match(r'^[a-z]*\d{3,5}[a-z]{0,4}$', lemma):
                model = lemma
                break
            # Спец. проверка для очень старых карт типа GT 210
            if category == 'GPU' and re.match(r'^\d{3,4}$', lemma):
                if lemma not in ['512', '256', '128', '1024', '2048', '2000', '1000', '3000', '5000']: 
                    model = lemma
                    break
            
        if series and model:
            full_model = f"{series}{model}".upper()
        elif series:
            full_model = series.upper()
        elif model:
            full_model = model.upper()

        return {'series': series, 'model': model, 'full_model': full_model}

    def _extract_features_nlp(self, doc, lemmas: List[str]) -> Dict[str, str]:
        features = {}

        for i, token in enumerate(doc):
            if token.like_num:
                if i + 1 < len(doc):
                    next_token = doc[i+1].lemma_.lower()
                    if next_token in ['gb', 'гб', 'tb', 'тб', 'mb', 'мб']:
                        features['capacity'] = f"{token.text}{next_token.replace('гб','gb').replace('тб','tb').replace('мб','mb')}"

        condition_keywords = {
            'new': ['новый', 'запечатать', 'new', 'пломба', 'магазин'],
            'used': ['бу', 'б/у', 'использовать'],
            'ideal': ['идеал', 'отличный', 'ideal'],
            'for_parts': ['запчасти', 'разбор', 'неисправн', 'донор', 'труп', 'ремонт', 'артефакт', 'отвал', 'текстолит', 'прогар']
        }

        found_cond = False
        for state, keys in condition_keywords.items():
            if any(k in lemmas for k in keys):
                features['condition'] = state
                found_cond = True
                break

        if not found_cond:
            raw = doc.text.lower()
            if 'на запчасти' in raw or 'под восстановление' in raw:
                features['condition'] = 'for_parts'

        return features

    def _extract_build_components(self, title: str, description: str) -> Dict[str, List[str]]:
        if not description or len(description) < 20:
            return {}

        text = f"{title}. {description[:500]}".lower()

        components = {
            'gpu': [],
            'cpu': [],
            'ram': [],
            'storage': []
        }

        gpu_patterns = [
            r'\b(rtx|gtx|rx|arc)\s*(\d{3,4}(?:\s?ti|super|xt|xtx)?)\b',
            r'\b(geforce|radeon|nvidia|amd)\s+(rtx|gtx|rx)?\s*(\d{3,4}(?:\s?ti)?)\b'
        ]

        for pattern in gpu_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                gpu_str = ' '.join(filter(None, match)).upper()
                if gpu_str and gpu_str not in components['gpu']:
                    components['gpu'].append(gpu_str)

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

        ram_patterns = [r'\b(\d+)\s*(?:gb|гб)\s+(?:ram|озу|памяти)\b']
        for pattern in ram_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                components['ram'].append(f"{match}GB")

        storage_patterns = [r'\b(\d+)\s*(?:gb|tb|гб|тб)\s+(?:ssd|hdd|nvme)\b']
        for pattern in storage_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                components['storage'].append(match.upper())

        return {k: v for k, v in components.items() if v}

    def _generate_product_key(self, category: str, brands: Dict, model_info: Dict, lemmas: List[str]) -> str:
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
        
        if cat_lower == 'service':
            if 'аренда' in lemmas: return "service_rent"
            if 'скупка' in lemmas or 'выкуп' in lemmas: return "service_buyout"
            if 'ремонт' in lemmas: return "service_repair"
            return "service_general"

        vendor = brands.get('vendor', '')
        chip = brands.get('chip', '')
        series = model_info.get('series', '')

        if not chip and not vendor and series:
            if series in ['rtx', 'gtx', 'geforce', 'titan']:
                chip = 'nvidia'
            elif series in ['rx', 'radeon', 'hd']:
                chip = 'amd'
            elif series in ['core', 'pentium', 'celeron', 'xeon', 'arc']:
                chip = 'intel'
            elif series in ['ryzen', 'athlon', 'threadripper', 'epyc']:
                chip = 'amd'

        brand_part = chip if chip else vendor
        model_part = model_info.get('model', '')
        if not model_part:
            model_part = model_info.get('series', '')

        parts = [cat_lower]
        if brand_part:
            normalized_brand = re.sub(r'[-\s]+', '_', brand_part.lower())
            normalized_brand = re.sub(r'[^a-z0-9_]', '', normalized_brand)
            normalized_brand = re.sub(r'_+', '_', normalized_brand).strip('_')
            if normalized_brand:
                parts.append(normalized_brand)

        if model_part:
            normalized_model = re.sub(r'[\s-]+', '', model_part.lower())
            normalized_model = re.sub(r'[^a-z0-9]', '', normalized_model)
            if normalized_model:
                parts.append(normalized_model)

        parts = [p for p in parts if p] 

        key = '_'.join(parts)
        key = re.sub(r'[^\w_]', '', key)
        key = re.sub(r'_+', '_', key)

        if not key or key == cat_lower or len(key.split('_')[-1]) < 2:
            if cat_lower in ['accessory', 'misc', 'cooling']:
                title_hash = hashlib.md5(''.join(lemmas[:5]).encode()).hexdigest()[:6]
                key = f"{cat_lower}_{title_hash}"
            else:
                found_key = False
                for lemma in lemmas:
                    if lemma not in self.NOISE_WORDS and len(lemma) > 2 and not lemma.isdigit():
                        normalized = re.sub(r'[^a-z0-9]', '', lemma.lower())
                        if normalized:
                            key = f"{cat_lower}_{normalized}"
                            found_key = True
                            break
                if not found_key:
                    hash_suffix = hashlib.md5(''.join(lemmas[:5]).encode()).hexdigest()[:6]
                    key = f"{cat_lower}_unknown_{hash_suffix}"

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
        parts = []

        brand = brands.get('chip') if category in ['GPU', 'CPU'] else brands.get('vendor')
        if brand:
            parts.append(brand.upper())

        if model_info.get('series'):
            parts.append(model_info['series'].upper())
        if model_info.get('model'):
            parts.append(model_info['model'].upper())

        if not parts:
            meaningful_words = []
            if lemmas:
                for lemma in lemmas[:15]:
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