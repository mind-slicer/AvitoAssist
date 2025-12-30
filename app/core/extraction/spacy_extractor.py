import spacy
import json
import os
import re
from typing import Dict, List, Any, Optional

from app.config import BASE_APP_DIR
from app.core.log_manager import logger

class SpacyFeatureExtractor:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SpacyFeatureExtractor, cls).__new__(cls)
            cls._instance._init_model()
        return cls._instance

    def _init_model(self):
        logger.info("Загрузка NLP модели (ru_core_news_sm)...", token="nlp_load")
        try:
            self.nlp = spacy.load("ru_core_news_sm")
            self.category_rules = self._load_category_rules()
            logger.success("NLP модель загружена.", token="nlp_load")
        except OSError:
            logger.error("Модель не найдена. Установите: python -m spacy download ru_core_news_sm")
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

        doc = self.nlp(title)

        # 1. Лемматизация и фильтрация
        tokens = [t for t in doc if not t.is_stop and not t.is_punct and len(t.text) > 1]
        lemmas = [t.lemma_.lower() for t in tokens]

        # 2. Определение категории
        category = self._detect_category(lemmas)

        # 3. Извлечение сущностей (Бренды)
        entities = self._extract_entities(doc, lemmas)
        
        # 4. Извлечение характеристик (память, состояние) - НОВОЕ
        features = self._extract_features_nlp(doc, lemmas)

        # 5. Генерация ключей
        product_key = self._generate_product_key(category, entities, lemmas)
        cluster_key = self._generate_cluster_key(category, product_key)
        
        # 6. Чистое имя
        clean_name = self._generate_clean_name(tokens) or title

        return {
            'category': category,
            'product_key': product_key,
            'cluster_key': cluster_key,
            'entity_type': 'PRODUCT',
            'clean_name': clean_name,
            'brand': entities.get('brand', ''),
            'model': entities.get('model', ''),
            'features': features, # Словарь с capacity, condition и т.д.
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
                if score > max_score:
                    max_score = score
                    best_category = cat_name
        
        return best_category

    def _extract_entities(self, doc, lemmas: List[str]) -> Dict[str, str]:
        entities = {'brand': ''}
        
        # Приоритет 1: NER от SpaCy
        for ent in doc.ents:
            if ent.label_ == "ORG":
                entities['brand'] = ent.text
                break
        
        # Приоритет 2: Латиница (часто бренды это первое латинское слово)
        if not entities['brand']:
            for lemma in lemmas:
                if re.match(r'^[a-z]+$', lemma) and len(lemma) > 2:
                    # Исключаем единицы измерения и распространенные сокращения
                    if lemma not in ['gb', 'tb', 'ddr', 'mhz', 'ssd', 'hdd', 'rgb']:
                        entities['brand'] = lemma
                        break
        return entities

    def _extract_features_nlp(self, doc, lemmas: List[str]) -> Dict[str, str]:
        features = {}
        
        # Поиск объема (число + gb/tb)
        # Проходим по исходному документу, чтобы сохранить порядок
        for i, token in enumerate(doc):
            if token.like_num:
                # Смотрим следующий токен
                if i + 1 < len(doc):
                    next_token = doc[i+1].lemma_.lower()
                    if next_token in ['gb', 'гб', 'tb', 'тб', 'гт']:
                        features['capacity'] = f"{token.text}{next_token.replace('гб','gb').replace('тб','tb')}"
        
        # Поиск состояния (по леммам)
        condition_keywords = {
            'new': ['новый', 'запечатать', 'new', 'пломба'],
            'used': ['бу', 'б/у', 'использовать'],
            'ideal': ['идеал', 'отличный', 'ideal']
        }
        
        for state, keys in condition_keywords.items():
            if any(k in lemmas for k in keys):
                features['condition'] = state
                break
                
        return features

    def _generate_product_key(self, category: str, entities: Dict, lemmas: List[str]) -> str:
        parts = [category.lower()]
        
        if entities.get('brand'):
            parts.append(entities['brand'].lower())
            
        # Добавляем модели/цифры, исключая мусор
        for lemma in lemmas:
            # Числа или комбинации букв+цифр (rtx3060, i5, 12400f)
            if re.match(r'^[a-z0-9\-]+$', lemma) and (any(c.isdigit() for c in lemma) or len(lemma) > 3):
                if lemma not in parts and lemma != category.lower() and lemma != entities.get('brand', '').lower():
                    parts.append(lemma)
        
        # Очистка и обрезка
        key = "_".join(parts[:5]) 
        key = re.sub(r'[^a-z0-9_]', '', key)
        return key

    def _generate_cluster_key(self, category: str, product_key: str) -> str:
        parts = product_key.split('_')
        if len(parts) > 2:
            return "_".join(parts[:3])
        return product_key
        
    def _generate_clean_name(self, tokens) -> str:
        # Собираем только значимые части речи
        parts = [t.text for t in tokens if t.pos_ in ['NOUN', 'PROPN', 'ADJ', 'NUM', 'X']]
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