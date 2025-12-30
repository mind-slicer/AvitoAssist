import spacy
import json
import os
import re
from typing import Dict, List, Any, Optional

from app.config import BASE_APP_DIR
from app.core.log_manager import logger

class SpacyFeatureExtractor:
    _instance = None

    # Производители чипов (основа для CPU/GPU)
    CHIP_MAKERS = {'nvidia', 'amd', 'intel', 'apple'}
    
    # Вендоры устройств (ноутбуки, мониторы, сборки)
    VENDORS = {
        'asus', 'msi', 'gigabyte', 'palit', 'sapphire', 'zotac', 'evga', 
        'lenovo', 'hp', 'dell', 'acer', 'samsung', 'lg', 'aoc', 'benq', 
        'kingston', 'adata', 'wd', 'seagate', 'sony', 'huawei', 'honor',
        'xiaomi', 'thunderobot', 'maibenben', 'colorful', 'inno3d', 'pny',
        'machcreator', 'chuwi', 'haier', 'digma', 'machenike'
    }

    SERIES_KEYWORDS = {
        'rtx', 'gtx', 'rx', 'arc', 'titan', 'quadro', # GPU
        'ryzen', 'core', 'athron', 'xeon', 'epyc', 'threadripper', 'pentium', 'celeron', # CPU
        'i3', 'i5', 'i7', 'i9', 'r3', 'r5', 'r7', 'r9', # CPU Short
        # Laptops Specific
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
            cls._instance = super(SpacyFeatureExtractor, cls).__new__(cls)
            cls._instance._init_model()
        return cls._instance

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

    def extract_semantic_data(self, title: str, description: str = "") -> Dict[str, Any]:
        if not title:
            return self._empty_result()

        clean_title = re.sub(r'[^\w\s\-\.]', ' ', title.lower())
        doc = self.nlp(clean_title)

        tokens = [t for t in doc if not t.is_stop and not t.is_punct and len(t.text) > 1]
        lemmas = [t.lemma_.lower() for t in tokens]

        # 1. Detect Category (with description peeking)
        category = self._detect_category(lemmas, description)

        # 2. Extract Brands
        brands = self._extract_brands(lemmas)
        
        # 3. Extract Series/Model
        model_info = self._extract_series_and_model(lemmas, category)

        # 4. Features
        features = self._extract_features_nlp(doc, lemmas)

        # 5. Keys
        product_key = self._generate_product_key(category, brands, model_info, lemmas)
        cluster_key = self._generate_cluster_key(category, brands, model_info)
        clean_name = self._generate_clean_name(category, brands, model_info)

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

    def _detect_category(self, lemmas: List[str], description: str = "") -> str:
        """
        Определяет категорию с учетом title и (опционально) начала description.
        Применяет систему штрафов за запрещенные слова.
        """
        best_category = "MISC"
        max_score = 0
        
        # Анализируем заголовок
        scores = self._score_lemmas(lemmas)
        
        # Если победитель не очевидный или это GPU/CPU (где часто путают с ноутбуками),
        # заглядываем в описание
        top_cat = max(scores, key=scores.get) if scores else "MISC"
        
        if description and len(description) > 10:
            # Peek first 200 chars
            desc_peek = description[:250].lower()
            # Простая токенизация для скорости
            desc_tokens = re.findall(r'\w+', desc_peek)
            
            # Считаем очки по описанию с весом 0.5 (оно менее важно, чем заголовок)
            desc_scores = self._score_lemmas(desc_tokens, weight_multiplier=0.5)
            
            # Суммируем
            for cat, sc in desc_scores.items():
                scores[cat] = scores.get(cat, 0) + sc

        # Финальный выбор
        # Приоритет LAPTOP/PC_BUILD при равных очках
        for cat, score in scores.items():
            if score > max_score:
                max_score = score
                best_category = cat
            elif score == max_score and score > 0:
                # Разрешение конфликтов
                if cat in ['LAPTOP', 'PC_BUILD'] and best_category in ['GPU', 'CPU', 'MOTHERBOARD']:
                    best_category = cat

        return best_category

    def _score_lemmas(self, lemmas: List[str], weight_multiplier: float = 1.0) -> Dict[str, float]:
        scores = {}
        
        for cat_name, rules in self.category_rules.items():
            keywords = rules.get("keywords", [])
            banned = rules.get("banned_keywords", [])
            priority = rules.get("priority", 1)
            
            current_score = 0
            
            # Плюсуем за ключевые слова
            for lemma in lemmas:
                if lemma in keywords:
                    current_score += (1 * priority * weight_multiplier)
                # Бонус за точные модели
                if cat_name == 'LAPTOP' and lemma in self.VENDORS:
                    current_score += 0.5 # Бренд в ноутбуке повышает шанс
            
            # Минусуем за запрещенные слова (сильный штраф)
            for lemma in lemmas:
                if lemma in banned:
                    current_score -= 50 # Мгновенная дисквалификация
            
            if current_score > 0:
                scores[cat_name] = current_score
                
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

    def _generate_product_key(self, category: str, brands: Dict, model_info: Dict, lemmas: List[str]) -> str:
        key_parts = [category.lower()]
        
        # ЛОГИКА БРЕНДОВ:
        # Для CPU/GPU/MOTHERBOARD приоритет Chip Maker (Intel, Nvidia)
        # Для остального - Vendor (Asus, Acer)
        primary_brand = None
        
        if category in ['GPU', 'CPU', 'MOTHERBOARD']:
            primary_brand = brands.get('chip') or brands.get('vendor')
            # Защита от дурака: Если категория CPU, а бренд Acer -> это ошибка.
            if category == 'CPU' and primary_brand in self.VENDORS and primary_brand not in self.CHIP_MAKERS:
                primary_brand = None # Сбрасываем, чтобы не плодить cpu_acer
        else:
            primary_brand = brands.get('vendor') or brands.get('chip')
            
        if primary_brand:
            key_parts.append(primary_brand)
            
        if model_info.get('full_model'):
            key_parts.append(model_info['full_model'])
        else:
            # Fallback
            fallback_tokens = []
            for lemma in lemmas:
                if (lemma not in self.CHIP_MAKERS and 
                    lemma not in self.VENDORS and 
                    lemma not in self.NOISE_WORDS and
                    lemma != category.lower() and
                    len(lemma) > 2):
                    fallback_tokens.append(lemma)
            
            if fallback_tokens:
                key_parts.extend(fallback_tokens[:2])
            else:
                key_parts.append("unknown")

        raw_key = "_".join(key_parts)
        clean_key = re.sub(r'[^a-z0-9_]', '', raw_key)
        return clean_key

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