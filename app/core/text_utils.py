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
        self.safe_regex = [re.compile(p, re.IGNORECASE) for p in self.SAFE_CONTEXT_PATTERNS]
        self.defect_regex = {}
        for cat, patterns in self.DEFAULT_PATTERNS.items():
            self.defect_regex[cat] = re.compile("|".join(patterns), re.IGNORECASE)

    def update_user_keywords(self, keywords_text: str):
        if not keywords_text:
            self.user_keywords = set()
            self.user_regex = None
            return

        raw_list = [w.strip() for w in keywords_text.split(',') if w.strip()]
        self.user_keywords = set(raw_list)

        if self.user_keywords:
            patterns = []
            for w in self.user_keywords:
                esc = re.escape(w)
                if w and w[0].isalnum():
                    patterns.append(rf"\b{esc}")
                else:
                    patterns.append(esc)
            self.user_regex = re.compile("|".join(patterns), re.IGNORECASE)
        else:
            self.user_regex = None

    def check(self, title: str, description: str) -> tuple[bool, str]:
        text = (f"{title} . {description}").lower()

        is_declared_safe = False
        for pattern in self.safe_regex:
            if pattern.search(text):
                is_declared_safe = True
                break

        found_defects = []

        if self.user_regex:
            matches = self.user_regex.findall(text)
            for m in matches:
                if self._check_negative_context(text, m): continue
                found_defects.append(f"[User] {m}")

        for category, regex in self.defect_regex.items():
            matches = regex.findall(text)
            for match in matches:
                if is_declared_safe and category == 'general_bad':
                    continue
                if self._check_negative_context(text, match):
                    continue
                found_defects.append(match)

        if found_defects:
            return True, ", ".join(set(found_defects))

        return False, ""

    def _check_negative_context(self, text: str, match_word: str) -> bool:
        start_idx = text.find(match_word)
        if start_idx > 0:
            context = text[max(0, start_idx - 15):start_idx]
            if any(neg in context for neg in ["без ", "нет ", "не ", "кроме ", "no "]):
                return True
        return False

# Singleton instance
defect_filter = SmartDefectFilter()


class FeatureExtractor:
    SYSTEM_TRIGGERS = [
        r'\bпк\b', r'\bpc\b', r'\bсистемник\b', r'\bсборка\b', 
        r'\bкомпьютер\b', r'\bсистемный\s+блок\b', r'\bdesktop\b',
        r'\bstation\b', r'\bworkstation\b', r'\bмоноблок\b', r'\bmonoblock\b'
    ]

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
        'цена', 'руб', 'рублей', 'договорная', 'системный', 'блок',
        'сборка', 'station', 'desktop'
    }

    @staticmethod
    def extract_semantic_data(title: str) -> Dict[str, str]:
        t_lower = title.lower()
        result = {
            'category': 'MISC',
            'sub_category': 'general',
            'product_key': '',
            'clean_name': title,
            'is_system': False
        }

        for pattern in FeatureExtractor.SYSTEM_TRIGGERS:
            if re.search(pattern, t_lower):
                result['is_system'] = True
                break

        for cat_name, rules in FeatureExtractor.SEMANTIC_RULES.items():
            if re.search(rules['trigger'], t_lower):
                result['category'] = cat_name

                for sub_name, sub_pattern in rules['vendor'].items():
                    if re.search(sub_pattern, t_lower):
                        result['sub_category'] = sub_name
                        break

                match = re.search(rules['model_pattern'], t_lower)
                if match:
                    model_raw = match.group(1)
                    clean_model = re.sub(r'\s+', ' ', model_raw).strip()
                    result['clean_name'] = clean_model

                    key_parts = [
                        result['sub_category'] if result['sub_category'] != 'general' else '',
                        clean_model
                    ]
                    result['product_key'] = "_".join(filter(None, key_parts)).replace(' ', '_')
                break
        
        if result['is_system']:
            result['category'] = 'SYSTEM'
            
            if result['product_key']:
                result['product_key'] = f"pc_{result['product_key']}"
                if result['clean_name'] == title:
                     result['clean_name'] = f"PC System"
                elif not result['clean_name'].lower().startswith("pc"):
                     result['clean_name'] = f"PC {result['clean_name']}"
            else:
                legacy_key = FeatureExtractor.generate_legacy_key(t_lower)
                result['product_key'] = f"pc_{legacy_key}"
                result['clean_name'] = 'Generic System'

        if result['category'] == 'MISC' and not result['product_key']:
            result['product_key'] = FeatureExtractor.generate_legacy_key(t_lower)

        return result

    @staticmethod
    def generate_product_key(title: str) -> str:
        data = FeatureExtractor.extract_semantic_data(title)
        return data['product_key']

    @staticmethod
    def generate_legacy_key(t_lower: str) -> str:
        # 1. Заменяем любые не-буквенные символы на пробелы
        cleaned = re.sub(r'[^\w\s]', ' ', t_lower)
        
        words = cleaned.split()
        
        # Расширенный список мусорных префиксов
        garbage_filters = {
            'b', 'y', 'bu', 'by', 'бу', 'бy', 'v', 'c', 's', 'x', 'box', 'edition',
            'ver', 'version', 'rev', 'revision', 'gb', 'tb', 'гб', 'тб'
        }
        
        meaningful_words = []
        for w in words:
            # FIX: Если слово начинается с 'b' и дальше идет русский текст (bвидеокарта), обрезаем 'b'
            # Это частый артефакт парсинга bold тегов <b>Видеокарта
            if w.startswith('b') and len(w) > 3 and re.search(r'[а-я]', w[1:]):
                w = w[1:]
                
            if w not in FeatureExtractor.STOP_WORDS and w not in garbage_filters and len(w) > 1 and not w.isdigit():
                meaningful_words.append(w)
        
        if meaningful_words:
            return "_".join(meaningful_words[:4])
        return "generic_item"

    @staticmethod
    def extract_features(text: str) -> Dict[str, str]:
        if not text:
            return {}

        text = text.lower()
        features = {}

        for key, pattern in FeatureExtractor.PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                raw_val = " ".join(g for g in match.groups() if g).replace(" ", "")
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