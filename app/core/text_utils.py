import re
from typing import Any, Dict, List, Set, Tuple

from app.core.extraction.spacy_extractor import SpacyFeatureExtractor

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
    @staticmethod
    def extract_semantic_data(title: str, description: str = "", price: int = 0) -> Dict[str, Any]:
        """
        Извлекает семантические данные.
        Теперь принимает description и price для полной совместимости с логикой экстрактора.
        """
        # Используем метод с дебагом и отбрасываем дебаг-инфо, чтобы гарантировать 100% идентичность логики
        result, _ = SpacyFeatureExtractor().extract_semantic_data_with_debug(title, description, price)
        return result

    @staticmethod
    def extract_semantic_data_with_debug(title: str, description: str = "", price: int = 0) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Прокси для метода с отладочной информацией."""
        return SpacyFeatureExtractor().extract_semantic_data_with_debug(title, description, price)

    @staticmethod
    def normalize_for_hash(text: str) -> List[str]:
        if not text: return []
        text = re.sub(r'[^\w\s]', '', text.lower())
        return text.split()
    
    @staticmethod
    def get_string_vector(text: str):
        """Возвращает numpy-вектор для строки."""
        if not text: return None
        
        extractor = SpacyFeatureExtractor()
        if not hasattr(extractor, 'nlp'):
            return None
            
        doc = extractor.nlp(text)
        if doc and doc.has_vector:
            return doc.vector
        return None

    @staticmethod
    def is_model_ready() -> bool:
        return hasattr(SpacyFeatureExtractor(), 'nlp')


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