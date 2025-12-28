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
    PATTERNS = {
        # Память (Видеопамять или ОЗУ)
        'capacity': r'\b(\d+)\s*(gb|гб|tb|тб)\b',
        
        # Видеокарты (RTX, GTX, RX, Ti, Super, XT)
        'gpu_model': r'\b(rtx|gtx|rx)\s*(\d{3,4})\s*(ti|super|xt|xtx|oc|gaming)?\b',
        
        # Процессоры (i3-i9, Ryzen, поколения)
        'cpu_model': r'\b(core\s*i\d|ryzen\s*\d)\s*-?\s*(\d{4,5}[kKfFhHxX]?)\b',
        
        # Состояние (включая майнинг сленг)
        'condition': r'\b(new|новый|sealed|запеч|б/?у|used|ideal|идеал|lhr|не майнил|пломб[аы])\b',
        
        # Комплект
        'kit': r'\b(box|коробк[аи]|чек|гарантия|full\s*set|полный\s*комплект)\b'
    }

    STOP_WORDS = {
        'продам', 'куплю', 'новый', 'новая', 'новое', 'бу', 'б/у', 
        'игровой', 'мощный', 'пк', 'компьютер', 'для', 'на', 
        'срочно', 'торг', 'обмен', 'оригинал', 'гарантия', 'чек',
        'состояние', 'идеал', 'полный', 'комплект', 'запечатан',
        'видеокарта', 'процессор', 'ноутбук', 'телефон', 'смартфон'
    }

    @staticmethod
    def generate_product_key(title: str) -> str:
        """
        Генерирует чистый ключ продукта из заголовка.
        Пример: "Продам мощный игровой ПК RTX 3060" -> "rtx_3060"
        Пример: "iPhone 15 Pro Max 256Gb" -> "iphone_15_pro_max"
        """
        if not title:
            return "unknown_item"
            
        t_lower = title.lower()
        
        gpu = re.search(FeatureExtractor.PATTERNS['gpu_model'], t_lower)
        if gpu:
            return re.sub(r'\s+', '_', gpu.group(0).strip())
            
        cpu = re.search(FeatureExtractor.PATTERNS['cpu_model'], t_lower)
        if cpu:
            return re.sub(r'\s+', '_', cpu.group(0).strip())

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