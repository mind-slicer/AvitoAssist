import re
from typing import Dict, List

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    TfidfVectorizer = None
    cosine_similarity = None

class FeatureExtractor:
    # Обновленные паттерны под ПК железо
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
        # Оставляем цифры и буквы, убираем пунктуацию
        text = re.sub(r'[^\w\s]', '', text.lower())
        return text.split()

class TextMatcher:
    @staticmethod
    def calculate_similarity(target_text: str, candidates: List[str]) -> List[float]:
        if not TfidfVectorizer or not target_text or not candidates:
            return [0.0] * len(candidates)
            
        corpus = [target_text] + candidates
        
        try:
            # analyzer='char_wb' хорошо работает с опечатками и моделями железа
            vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
            tfidf_matrix = vectorizer.fit_transform(corpus)
            
            cosine_sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])
            
            return cosine_sim[0].tolist()
        except Exception:
            return [0.0] * len(candidates)
        
    @staticmethod
    def filter_similar_items(target_title: str, all_items: List[Dict], threshold: float = 0.35) -> List[Dict]:
        if not target_title or not all_items:
            return []
            
        candidates = [i.get('title', '') for i in all_items]
        
        scores = TextMatcher.calculate_similarity(target_title, candidates)
        
        result = []
        for i, score in enumerate(scores):
            if score >= threshold:
                result.append(all_items[i])
                
        if len(result) < 3 and len(all_items) > 0:
             # Сортируем по убыванию скора
             zipped = sorted(zip(all_items, scores), key=lambda x: x[1], reverse=True)
             return [x[0] for x in zipped[:10]]

        return result