import spacy
import json
import os
import re
from typing import Dict, List, Any

from app.config import BASE_APP_DIR
from app.core.log_manager import logger

class SpacyFeatureExtractor:
    _instance = None

    # --- СЛОВАРИ ЗНАНИЙ (УНИВЕРСАЛЬНЫЕ) ---
    
    # Производители чипов (основа для CPU/GPU)
    CHIP_MAKERS = {'nvidia', 'amd', 'intel', 'apple'}
    
    # Вендоры устройств (ноутбуки, мониторы, сборки)
    VENDORS = {
        'asus', 'msi', 'gigabyte', 'palit', 'sapphire', 'zotac', 'evga', 
        'lenovo', 'hp', 'dell', 'acer', 'samsung', 'lg', 'aoc', 'benq', 
        'kingston', 'adata', 'wd', 'seagate', 'sony', 'huawei', 'honor',
        'xiaomi', 'thunderobot', 'maibenben', 'colorful', 'inno3d', 'pny'
    }

    # Ключевые слова серий (для склейки с моделью)
    SERIES_KEYWORDS = {
        'rtx', 'gtx', 'rx', 'arc', 'titan', 'quadro', # GPU
        'ryzen', 'core', 'athron', 'xeon', 'epyc', 'threadripper', 'pentium', 'celeron', # CPU
        'i3', 'i5', 'i7', 'i9', 'r3', 'r5', 'r7', 'r9', # CPU Short
        'macbook', 'air', 'pro', 'legion', 'vivobook', 'zenbook', 'rog', 'tuf', 'strix', # Laptops
        'playstation', 'xbox', 'nintendo' # Consoles
    }

    # Маркетинговый шум, который НЕ должен попасть в product_key
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
    
    # Слова, которые являются частью модели (исключения из шума)
    # Например, "ti" и "super" важны для GPU, "k" и "f" для CPU, но мы их обработаем в логике склейки
    MODEL_SUFFIXES = {'ti', 'super', 'xt', 'xtx', 'k', 'f', 'kf', 'x', 'x3d', 'h', 'hx', 'u', 'p'}

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

    def extract_semantic_data(self, title: str) -> Dict[str, Any]:
        if not title:
            return self._empty_result()

        # Предварительная очистка
        clean_title = re.sub(r'[^\w\s\-\.]', ' ', title.lower())
        doc = self.nlp(clean_title)

        tokens = [t for t in doc if not t.is_stop and not t.is_punct and len(t.text) > 1]
        lemmas = [t.lemma_.lower() for t in tokens]

        # 1. Определяем категорию
        category = self._detect_category(lemmas)

        # 2. Извлекаем бренды (Chip maker и Vendor)
        brands = self._extract_brands(lemmas)
        
        # 3. Извлекаем "сердце" названия - серию и модель
        model_info = self._extract_series_and_model(lemmas, category)

        # 4. Извлекаем характеристики
        features = self._extract_features_nlp(doc, lemmas)

        # 5. Генерируем ключи
        product_key = self._generate_product_key(category, brands, model_info, lemmas)
        cluster_key = self._generate_cluster_key(category, brands, model_info)

        # Генерация чистого имени для отображения
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

    def _detect_category(self, lemmas: List[str]) -> str:
        best_category = "MISC"
        max_score = 0

        for cat_name, rules in self.category_rules.items():
            keywords = rules.get("keywords", [])
            priority = rules.get("priority", 1)

            matches = sum(1 for lemma in lemmas if lemma in keywords)
            if matches > 0:
                score = matches * priority
                # Бонус за точное совпадение первого слова (часто категория идет первой)
                if lemmas and lemmas[0] in keywords:
                    score += 2
                
                if score > max_score:
                    max_score = score
                    best_category = cat_name

        return best_category

    def _extract_brands(self, lemmas: List[str]) -> Dict[str, str]:
        brands = {'chip': None, 'vendor': None}
        
        for lemma in lemmas:
            if lemma in self.CHIP_MAKERS:
                brands['chip'] = lemma
            elif lemma in self.VENDORS:
                # Если вендоров несколько, берем первый (обычно самый важный)
                if not brands['vendor']:
                    brands['vendor'] = lemma
                    
        return brands

    def _extract_series_and_model(self, lemmas: List[str], category: str) -> Dict[str, str]:
        """
        Ищет серию и модель. 
        Пример: ['geforce', 'rtx', '3060', 'ti'] -> Series: 'rtx', Model: '3060ti'
        """
        info = {'series': '', 'model': '', 'full_model': ''}
        
        # Индексы использованных токенов, чтобы не дублировать
        used_indices = set()
        
        # Поиск серии
        series_idx = -1
        for i, lemma in enumerate(lemmas):
            if lemma in self.SERIES_KEYWORDS:
                info['series'] = lemma
                series_idx = i
                used_indices.add(i)
                break
        
        # Поиск цифровой модели
        # Ищем цифры (3060, 12400) рядом с серией или просто цифры
        model_parts = []
        
        start_search = series_idx + 1 if series_idx != -1 else 0
        
        for i in range(start_search, len(lemmas)):
            token = lemmas[i]
            
            # Пропускаем уже использованные и шум
            if i in used_indices or token in self.NOISE_WORDS:
                continue
                
            # Паттерн модели: содержит цифры (3060, 5600x, 12700k)
            # Но не является просто 'gb', 'tb', 'mhz' (это фильтруется в NOISE_WORDS частично, но проверим)
            if re.search(r'\d', token):
                # Исключаем явные характеристики памяти/частоты, если они не попали в шум
                if any(x in token for x in ['gb', 'mb', 'tb', 'mhz', 'v', 'w']):
                    continue
                
                model_parts.append(token)
                used_indices.add(i)
                
                # Проверяем следующий токен на суффикс (ti, super, k, f)
                if i + 1 < len(lemmas):
                    next_token = lemmas[i+1]
                    if next_token in self.MODEL_SUFFIXES:
                        model_parts.append(next_token)
                        used_indices.add(i+1)
                
                # Обычно модель - это одно число + суффикс. Нашли - выходим.
                # Если это не набор типа "ryzen 5 5600"
                if len(model_parts) >= 1: 
                    # Дополнительная проверка для составных имен типа "core i5 12400"
                    # Если сейчас нашли "5" (от i5), ищем дальше основное число
                    if token in ['3', '5', '7', '9'] and len(token) == 1:
                        continue 
                    break
        
        info['model'] = "".join(model_parts)
        
        # Формируем полное название модели
        parts = []
        if info['series']: parts.append(info['series'])
        if info['model']: parts.append(info['model'])
        
        info['full_model'] = "".join(parts) # rtx3060ti
        return info

    def _extract_features_nlp(self, doc, lemmas: List[str]) -> Dict[str, str]:
        features = {}
        for i, token in enumerate(doc):
            # Поиск памяти (8gb, 16gb)
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
        """
        Генерирует строгий ключ: category_brand_series+model
        """
        key_parts = [category.lower()]
        
        # Выбор бренда зависит от категории
        # Для CPU/GPU важнее чипмейкер (nvidia, intel)
        # Для Ноутбуков/Мониторов важнее вендор (asus, lg)
        primary_brand = None
        
        if category in ['GPU', 'CPU', 'MOTHERBOARD']:
            primary_brand = brands.get('chip') or brands.get('vendor')
        else:
            primary_brand = brands.get('vendor') or brands.get('chip')
            
        if primary_brand:
            key_parts.append(primary_brand)
            
        # Добавляем модель (series + number)
        if model_info.get('full_model'):
            key_parts.append(model_info['full_model'])
        else:
            # Fallback: Если модель не найдена алгоритмически,
            # берем 2-3 "значимых" слова из остатка, исключая шум
            fallback_tokens = []
            for lemma in lemmas:
                if (lemma not in self.CHIP_MAKERS and 
                    lemma not in self.VENDORS and 
                    lemma not in self.NOISE_WORDS and
                    lemma != category.lower() and
                    len(lemma) > 2):
                    fallback_tokens.append(lemma)
            
            if fallback_tokens:
                # Берем не более 2 слов для чистоты
                key_parts.extend(fallback_tokens[:2])
            else:
                key_parts.append("unknown")

        # Финальная очистка
        raw_key = "_".join(key_parts)
        clean_key = re.sub(r'[^a-z0-9_]', '', raw_key)
        return clean_key

    def _generate_cluster_key(self, category: str, brands: Dict, model_info: Dict) -> str:
        """
        Кластер - это более общая группа. Например, rtx3060 и rtx3060ti могут быть в одном кластере,
        или rtx30series.
        Здесь упростим: кластер = категория + бренд + серия (без точной модели)
        """
        parts = [category.lower()]
        
        brand = brands.get('chip') if category in ['GPU', 'CPU'] else brands.get('vendor')
        if brand: parts.append(brand)
        
        if model_info.get('series'):
            parts.append(model_info['series'])
        elif model_info.get('full_model'):
            # Если серии нет, но есть модель, берем начало модели (грубая эвристика)
            parts.append(model_info['full_model'][:4])
            
        return "_".join(parts)

    def _generate_clean_name(self, category: str, brands: Dict, model_info: Dict) -> str:
        parts = []
        
        # Бренд
        brand = brands.get('chip') if category in ['GPU', 'CPU'] else brands.get('vendor')
        if brand: parts.append(brand.upper())
        
        # Серия и модель
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