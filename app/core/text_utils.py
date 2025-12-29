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
            'trigger': r'\b(rtx|gtx|rx|arc|geforce|radeon|nvidia|gt|titan|quadro|video\s*card|видеокарт[а-я]*)\b',
            'vendor': {
                'nvidia': r'\b(rtx|gtx|nvidia|geforce|gt|titan|quadro)\b',
                'amd': r'\b(rx|radeon|amd)\b',
                'intel': r'\b(arc|intel)\b'
            },
            'model_pattern': r'\b((?:rtx|gtx|rx|arc|gt)\s*\d{3,4}(?:\s*(?:ti|super|xt|xtx|oc|se))?|titan\s*\w*|quadro\s*\w+)\b'
        },
        'CPU': {
            'trigger': r'\b(ryzen|core|xeon|threadripper|epyc|pentium|celeron|athlon|fx)\b',
            'vendor': {
                'intel': r'\b(core|xeon|intel|pentium|celeron)\b',
                'amd': r'\b(ryzen|threadripper|epyc|amd|athlon|fx)\b'
            },
            'model_pattern': r'\b((?:i\d|ryzen\s*\d|fx|a\d)\s*-?\s*\d{3,5}[a-z]*)\b'
        },
        'MOBO': {
            'trigger': r'\b([bzxhq]\d{2,3}[a-z]?|lga|am4|am5|socket|соке[тd])\b',
            'vendor': {},
            'model_pattern': r'\b([bzxhq]\d{2,3}[a-z]?)\b'
        },
        'RAM': {
            'trigger': r'\b(ddr\d|dimm|sodimm)\b',
            'vendor': {},
            'model_pattern': r'\b(ddr\d)\b',
            'anti_trigger': r'\b(video|gpu|graphic|видео|карт[а-я]*|geforce|radeon|rtx|gtx|rx|arc|gt|lga|am4|am5|socket)\b'
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
            'cluster_key': '',
            'entity_type': 'CATEGORY',
            'clean_name': title,
            'is_system': False
        }

        # 1. System check
        for pattern in FeatureExtractor.SYSTEM_TRIGGERS:
            if re.search(pattern, t_lower):
                result['is_system'] = True
                break

        # 2. Category & Model extraction
        matched_rule = False
        for cat_name, rules in FeatureExtractor.SEMANTIC_RULES.items():
            if 'anti_trigger' in rules and re.search(rules['anti_trigger'], t_lower):
                continue

            if re.search(rules['trigger'], t_lower):
                matched_rule = True
                result['category'] = cat_name

                # Vendor extraction
                for sub_name, sub_pattern in rules['vendor'].items():
                    if re.search(sub_pattern, t_lower):
                        result['sub_category'] = sub_name
                        break

                # Model extraction
                match = re.search(rules['model_pattern'], t_lower)
                if match:
                    model_raw = match.group(1)
                    clean_model = re.sub(r'\s+', ' ', model_raw).strip()
                    result['clean_name'] = clean_model
                    key_parts = [result['sub_category'] if result['sub_category'] != 'general' else '', clean_model]
                    result['product_key'] = "_".join(filter(None, key_parts)).replace(' ', '_')
                    result['cluster_key'] = FeatureExtractor._derive_cluster_key(cat_name, clean_model)
                    result['entity_type'] = 'PRODUCT'
                else:
                    if result['sub_category'] != 'general':
                        result['entity_type'] = 'LINEUP'
                        result['product_key'] = f"{cat_name}_{result['sub_category']}"
                        result['cluster_key'] = f"{cat_name}_{result['sub_category']}"
                    else:
                        result['entity_type'] = 'CATEGORY'
                        result['product_key'] = cat_name
                        result['cluster_key'] = cat_name
                break
        
        if not matched_rule and not result['is_system']:
            # Пытаемся понять, что это, через эвристику первых слов
            universal_keys = FeatureExtractor._generate_universal_keys(t_lower)
            result['category'] = 'UNIVERSAL' # Маркер универсальной категории
            result['cluster_key'] = universal_keys['cluster']
            result['product_key'] = universal_keys['product']
            result['entity_type'] = 'PRODUCT'
            result['clean_name'] = title # Оставляем оригинал для читаемости

        # 3. Handle Systems
        if result['is_system']:
            result['category'] = 'SYSTEM'
            if result['product_key'] and matched_rule:
                result['cluster_key'] = f"pc_with_{result['cluster_key']}" 
                result['product_key'] = f"pc_{result['product_key']}"
                result['entity_type'] = 'PRODUCT'
            else:
                # Универсальная обработка для системников без явной видеокарты в названии
                legacy_key = FeatureExtractor.generate_legacy_key(t_lower)
                result['product_key'] = f"pc_{legacy_key}"
                result['cluster_key'] = 'pc_general'
                result['entity_type'] = 'CATEGORY'

        return result

    @staticmethod
    def _generate_universal_keys(text: str) -> Dict[str, str]:
        """
        Универсальный генератор ключей для ЛЮБОЙ ниши (Авто, Недвижка, Мебель).
        Берет первые значимые слова.
        """
        # Убираем спецсимволы
        cleaned = re.sub(r'[^\w\s]', ' ', text)
        words = cleaned.split()
        
        meaningful = []
        for w in words:
            # Фильтр стоп-слов и мусора
            if len(w) < 2: continue
            if w.isdigit() and len(w) < 3: continue # Пропускаем 1, 20, но оставляем 3060, 2020
            if w in FeatureExtractor.STOP_WORDS: continue
            meaningful.append(w)
        
        if not meaningful:
            return {'cluster': 'misc_unknown', 'product': 'misc_item'}
            
        # Эвристика: Кластер = Первые 2 слова (Например: "BMW X5", "Диван Угловой")
        # Продукт = Первые 4 слова ("BMW X5 2020 Черный")
        
        cluster_words = meaningful[:2]
        product_words = meaningful[:4]
        
        return {
            'cluster': "_".join(cluster_words),
            'product': "_".join(product_words)
        }

    @staticmethod
    def _derive_cluster_key(category: str, clean_model: str) -> str:
        """
        Groups specific models into families.
        RTX 3060 Ti -> rtx_30
        Core i5 12400F -> core_i5_12
        """
        m = clean_model.lower().replace(' ', '')
        
        if category == 'GPU':
            # Nvidia RTX/GTX
            if 'rtx30' in m: return 'gpu_nvidia_rtx30_series'
            if 'rtx40' in m: return 'gpu_nvidia_rtx40_series'
            if 'rtx50' in m: return 'gpu_nvidia_rtx50_series'
            if 'rtx20' in m: return 'gpu_nvidia_rtx20_series'
            if 'gtx16' in m: return 'gpu_nvidia_gtx16_series'
            if 'gtx10' in m: return 'gpu_nvidia_gtx10_series'
            # AMD RX
            if 'rx7' in m: return 'gpu_amd_rx7000_series'
            if 'rx6' in m: return 'gpu_amd_rx6000_series'
            if 'rx5' in m and len(m) > 3: return 'gpu_amd_rx5000_or_500' # rx580, rx5700
            
        if category == 'CPU':
            # Intel Core
            match_intel = re.search(r'(corei\d)(\d{2,5})', m)
            if match_intel:
                family = match_intel.group(1) # corei5
                gen = match_intel.group(2)
                # Take first 1 or 2 digits as gen (12xxx -> 12, 9xxx -> 9)
                gen_ver = gen[:2] if len(gen) >= 4 else gen[:1]
                return f"cpu_intel_{family}_gen{gen_ver}"
            
            # AMD Ryzen
            match_amd = re.search(r'(ryzen\d)(\d{4})', m)
            if match_amd:
                family = match_amd.group(1)
                gen = match_amd.group(2)[0] # 5600 -> 5
                return f"cpu_amd_{family}_{gen}000_series"

        # Default: use first word + length logic or just raw model
        return f"{category.lower()}_{clean_model.split()[0]}"

    @staticmethod
    def generate_product_key(title: str) -> str:
        data = FeatureExtractor.extract_semantic_data(title)
        return data['product_key']

    @staticmethod
    def generate_legacy_key(t_lower: str) -> str:
        cleaned = re.sub(r'[^\w\s]', ' ', t_lower)
        
        words = cleaned.split()
        
        garbage_filters = {
            'b', 'y', 'bu', 'by', 'бу', 'бy', 'v', 'c', 's', 'x', 'box', 'edition',
            'ver', 'version', 'rev', 'revision', 'gb', 'tb', 'гб', 'тб',
            'ddr3', 'ddr4', 'ddr5', 'gddr5', 'gddr6'
        }
        
        meaningful_words = []
        for w in words:
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