import re
from typing import Dict, List, Set

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    TfidfVectorizer = None
    cosine_similarity = None


class SmartDefectFilter:
    _instance = None

    SAFE_CONTEXT_PATTERNS = [
        r"без\s+(?:каких.?либо\s+)?(?:скрытых\s+)?(?:дефектов|проблем|нюансов|косяков)",
        r"не\s+(?:имеет|имеются)\s+(?:никаких\s+)?(?:дефектов|проблем)",
        r"полностью\s+(?:рабочий|исправен)",
        r"любые\s+проверки",
        r"состояние\s+новых",
        r"работает\s+без\s+нареканий",
        r"не\s+грет",
        r"не\s+после\s+майнинга"
    ]

    DEFAULT_PATTERNS = {
        'critical': [
            r"\bна\s+запчаст", r"\bна\s+разбор", r"\bдонор", r"\bтруп", r"\bкирпич",
            r"\bне\s+включ", r"\bне\s+стартует", r"\bне\s+запускается", r"\bнет\s+изображения",
            r"\bчерный\s+экран", r"\bциклическая\s+перезагрузка", r"\bбутлуп"
        ],
        'gpu_specific': [
            r"\bартефакт", r"\bартефач", r"\bполосы\s+на", r"\bкод\s+43", 
            r"\bотвал", r"\bпрогрев", r"\bребол", r"\bпрожар", r"\bпосле\s+майнинга"
        ],
        'physical': [
            r"\bразбит", r"\bтрещин", 
            r"\bскол(?:а|ы|ов|е|ах)?\b", 
            r"\bпогнут", r"\bзалит", 
            r"\bутоплен", r"\bкорроз", r"\bржавчин", 
            r"\bбит(?:ый|ая|ое|ые|ым|ых)\b", 
            r"\bпотек"
        ],
        'general_bad': [
            r"\bдефект", r"\bнюанс", r"\bкосяк", r"\bпроблемн", r"\bглючит", 
            r"\bзависает", 
            r"\bлага(?:ет|ют|л|л[аи])\b",
            r"\bне\s*рабоч", 
            r"\bпод\s+восстановление",
            r"\bтребует\s+ремонт", r"\bпод\s+ремонт"
        ]
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SmartDefectFilter, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.user_keywords: Set[str] = set()
        self.regex_cache = {}
        self._compile_defaults()

    def _compile_defaults(self):
        # Компилируем защиту (белый список)
        self.safe_regex = [re.compile(p, re.IGNORECASE) for p in self.SAFE_CONTEXT_PATTERNS]
        
        # Компилируем базовые дефекты
        self.defect_regex = {}
        for cat, patterns in self.DEFAULT_PATTERNS.items():
            self.defect_regex[cat] = re.compile("|".join(patterns), re.IGNORECASE)

    def update_user_keywords(self, keywords_text: str):
        """Обновляет пользовательский список из строки (разделитель - запятая)"""
        if not keywords_text:
            self.user_keywords = set()
            self.user_regex = None
            return

        # Разбиваем, чистим, убираем пустые
        raw_list = [w.strip() for w in keywords_text.split(',') if w.strip()]
        self.user_keywords = set(raw_list)
        
        if self.user_keywords:
            # Для пользовательских слов тоже добавляем границу слова, если это не фраза
            # (Экранируем спецсимволы, чтобы пользователь не сломал Regex)
            patterns = []
            for w in self.user_keywords:
                esc = re.escape(w)
                # Если слово начинается с буквы/цифры, добавляем границу \b
                if w and w[0].isalnum():
                    patterns.append(rf"\b{esc}")
                else:
                    patterns.append(esc)
            
            self.user_regex = re.compile("|".join(patterns), re.IGNORECASE)
        else:
            self.user_regex = None

    def check(self, title: str, description: str) -> tuple[bool, str]:
        """
        Главный метод проверки.
        :return: (True, "причина") если найден дефект, иначе (False, "")
        """
        # Объединяем текст для контекста
        text = (f"{title} . {description}").lower()

        # 1. Проверяем "белый список" (исключения)
        # Если нашли "без дефектов", то флаг strict_mode выключаем (игнорируем слабые слова)
        is_declared_safe = False
        for pattern in self.safe_regex:
            if pattern.search(text):
                is_declared_safe = True
                break

        found_defects = []

        # 2. Проверяем пользовательские слова (наивысший приоритет)
        if self.user_regex:
            matches = self.user_regex.findall(text)
            for m in matches:
                if self._check_negative_context(text, m): continue
                found_defects.append(f"[User] {m}")

        # 3. Проверяем встроенные категории
        for category, regex in self.defect_regex.items():
            matches = regex.findall(text)
            for match in matches:
                # Если товар "безопасен", игнорируем общие слова типа "нюанс"
                if is_declared_safe and category == 'general_bad':
                    continue
                
                # Проверяем контекст ("БЕЗ царапин")
                if self._check_negative_context(text, match):
                    continue

                found_defects.append(match)

        if found_defects:
            return True, ", ".join(set(found_defects))
        
        return False, ""

    def _check_negative_context(self, text: str, match_word: str) -> bool:
        """Проверяет, нет ли перед словом отрицания (не, без, кроме)"""
        start_idx = text.find(match_word)
        if start_idx > 0:
            # Смотрим 15 символов до найденного слова
            context = text[max(0, start_idx - 15):start_idx]
            # Проверяем наличие отрицаний. 
            # Добавлена проверка пробела после предлога, чтобы не ловить части слов
            if any(neg in context for neg in ["без ", "нет ", "не ", "кроме ", "no "]):
                return True
        return False

# Singleton instance
defect_filter = SmartDefectFilter()


class FeatureExtractor:
    SEMANTIC_RULES = {
        'GPU': {
            'trigger': r'\b(rtx|gtx|rx|arc)\b',
            'vendor': {
                'nvidia': r'\b(rtx|gtx|nvidia)\b',
                'amd': r'\b(rx|radeon|amd)\b',
                'intel': r'\b(arc|intel)\b'
            },
            'model_pattern': r'\b((?:rtx|gtx|rx)\s*\d{3,4}(?:\s*(?:ti|super|xt|xtx))?)\b'
        },
        'CPU': {
            'trigger': r'\b(ryzen|core|xeon|threadripper|epyc)\b',
            'vendor': {
                'intel': r'\b(core|xeon|intel)\b',
                'amd': r'\b(ryzen|threadripper|epyc|amd)\b'
            },
            'model_pattern': r'\b((?:i\d|ryzen\s*\d)\s*-?\s*\d{3,5}[a-z]*)\b'
        },
        'MOBO': {
            'trigger': r'\b(b450|b550|x570|z490|z590|z690|z790|lga|am4|am5)\b',
            'vendor': {},
            'model_pattern': r'\b([bzxhqa]\d{3}[a-z]?)\b'
        },
        'RAM': {
            'trigger': r'\b(ddr\d|dimm|sodimm)\b',
            'vendor': {},
            'model_pattern': r'\b(ddr\d)\b'
        }
    }

    PATTERNS = {
        'capacity': r'\b(\d+)\s*(gb|гб|tb|тб)\b',
        'gpu_model': r'\b(rtx|gtx|rx)\s*(\d{3,4})\s*(ti|super|xt|xtx|oc|gaming)?\b',
        'cpu_model': r'\b(core\s*i\d|ryzen\s*\d)\s*-?\s*(\d{4,5}[kKfFhHxX]?)\b',
        'condition': r'\b(new|новый|sealed|запеч|б/?у|used|ideal|идеал|lhr|не майнил|пломб[аы])\b',
        'kit': r'\b(box|коробк[аи]|чек|гарантия|full\s*set|полный\s*комплект)\b'
    }

    STOP_WORDS = {
        'продам', 'куплю', 'новый', 'новая', 'новое', 'бу', 'б/у',
        'игровой', 'мощный', 'пк', 'компьютер', 'для', 'на',
        'срочно', 'торг', 'обмен', 'оригинал', 'гарантия', 'чек',
        'состояние', 'идеал', 'полный', 'комплект', 'запечатан',
        'видеокарта', 'процессор', 'ноутбук', 'телефон', 'смартфон',
        'цена', 'руб', 'рублей', 'договорная'
    }

    @staticmethod
    def extract_semantic_data(title: str) -> Dict[str, str]:
        """
        Возвращает структурированные данные:
        {
            'category': 'GPU' | 'CPU' | 'MOBO' | 'MISC',
            'sub_category': 'Nvidia' | 'AMD' | ...,
            'product_key': 'nvidia_rtx_3060_ti',
            'clean_name': 'RTX 3060 Ti'
        }
        """
        t_lower = title.lower()
        result = {
            'category': 'MISC',
            'sub_category': 'general',
            'product_key': '',
            'clean_name': title
        }

        # 1. Определение категории
        for cat_name, rules in FeatureExtractor.SEMANTIC_RULES.items():
            if re.search(rules['trigger'], t_lower):
                result['category'] = cat_name
                
                # 2. Определение подкатегории (вендора)
                for sub_name, sub_pattern in rules['vendor'].items():
                    if re.search(sub_pattern, t_lower):
                        result['sub_category'] = sub_name
                        break
                
                # 3. Извлечение конкретной модели
                match = re.search(rules['model_pattern'], t_lower)
                if match:
                    model_raw = match.group(1)
                    # Нормализация: убираем пробелы, тире, приводим к стандарту
                    clean_model = re.sub(r'\s+', ' ', model_raw).strip()
                    result['clean_name'] = clean_model
                    
                    # Генерация ключа продукта
                    key_parts = [
                        result['sub_category'] if result['sub_category'] != 'general' else '',
                        clean_model
                    ]
                    result['product_key'] = "_".join(filter(None, key_parts)).replace(' ', '_')
                
                break # Категория найдена, выходим

        # Фоллбэк для MISC категорий - старый метод
        if result['category'] == 'MISC':
            result['product_key'] = FeatureExtractor.generate_legacy_key(t_lower)
            
        return result

    @staticmethod
    def generate_product_key(title: str) -> str:
        """Обертка для обратной совместимости"""
        data = FeatureExtractor.extract_semantic_data(title)
        return data['product_key']

    @staticmethod
    def generate_legacy_key(t_lower: str) -> str:
        """Старая логика генерации ключей для неопределенных категорий"""
        cleaned = re.sub(r'[^\w\s]', '', t_lower)
        words = cleaned.split()
        meaningful_words = [
            w for w in words
            if w not in FeatureExtractor.STOP_WORDS
            and len(w) > 1
            and not w.isdigit()
        ]
        if meaningful_words:
            return "_".join(meaningful_words[:4])
        return "generic_item"

    @staticmethod
    def extract_features(text: str) -> Dict[str, str]:
        """Returns a dictionary of normalized features."""
        if not text:
            return {}
            
        text = text.lower()
        features = {}
        
        for key, pattern in FeatureExtractor.PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                # Берем все захваченные группы и склеиваем
                raw_val = " ".join(g for g in match.groups() if g).replace(" ", "")
                
                # Нормализация
                raw_val = raw_val.replace("гб", "gb").replace("тб", "tb")
                raw_val = raw_val.replace("новый", "new").replace("запеч", "new")
                raw_val = raw_val.replace("идеал", "used_perfect")
                
                features[key] = raw_val
                
        return features

    @staticmethod
    def normalize_for_hash(text: str) -> List[str]:
        if not text:
            return []
        text = re.sub(r'[^\w\s]', '', text.lower())
        return text.split()

class TextMatcher:
    _vectorizer = None
    _tfidf_matrix = None
    _items_cache = None

    @staticmethod
    def precompute_corpus(items: List[Dict]):
        if not TfidfVectorizer or not items:
            return
        
        titles = [i.get('title', '') for i in items]
        try:
            TextMatcher._vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
            TextMatcher._tfidf_matrix = TextMatcher._vectorizer.fit_transform(titles)
            TextMatcher._items_cache = items
        except Exception as e:
            print(f"Error precomputing TF-IDF: {e}")

    @staticmethod
    def clear_cache():
        TextMatcher._vectorizer = None
        TextMatcher._tfidf_matrix = None
        TextMatcher._items_cache = None

    @staticmethod
    def filter_similar_items(target_title: str, all_items: List[Dict], threshold: float = 0.35) -> List[Dict]:
        if not target_title or not all_items:
            return []

        if TextMatcher._vectorizer and TextMatcher._tfidf_matrix is not None and all_items is TextMatcher._items_cache:
            try:
                target_vec = TextMatcher._vectorizer.transform([target_title])
                cosine_sim = cosine_similarity(target_vec, TextMatcher._tfidf_matrix).flatten()
                
                indices = cosine_sim.argsort()[::-1]
                result = []
                
                for idx in indices[:15]:
                    score = cosine_sim[idx]
                    if score >= threshold:
                        result.append(all_items[idx])
                    elif len(result) < 3:
                         result.append(all_items[idx])
                    else:
                        break
                
                return result
            except Exception:
                pass

        candidates = [i.get('title', '') for i in all_items]
        scores = TextMatcher.calculate_similarity(target_title, candidates)
        
        zipped = sorted(zip(all_items, scores), key=lambda x: x[1], reverse=True)
        result = [x[0] for x in zipped if x[1] >= threshold]
        
        if len(result) < 3:
             return [x[0] for x in zipped[:5]]
             
        return result

    @staticmethod
    def calculate_similarity(target_text: str, candidates: List[str]) -> List[float]:
        if not TfidfVectorizer or not target_text or not candidates:
            return [0.0] * len(candidates)
        
        corpus = [target_text] + candidates
        try:
            vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
            tfidf_matrix = vectorizer.fit_transform(corpus)
            cosine_sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])
            return cosine_sim[0].tolist()
        except Exception:
            return [0.0] * len(candidates)