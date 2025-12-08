import re
import hashlib
from typing import Dict, List

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    TfidfVectorizer = None
    cosine_similarity = None

class FeatureExtractor:
    PATTERNS = {
        'storage': r'\b(\d+)\s*(gb|гб|tb|тб)\b',
        'ram': r'\b(\d+)\s*(gb|гб)\s*(ram|озу)\b',
        'model_suffix': r'\b(pro|max|plus|ultra|mini|air|slim|lite|se)\b',
        'condition': r'\b(new|новый|sealed|запеч|б/?у|used|ideal|идеал)\b',
        'authenticity': r'\b(orig|ориг|replica|репл|copy|копия)\b'
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
                raw_val = match.group(0).replace(" ", "")
                raw_val = raw_val.replace("гб", "gb").replace("тб", "tb")
                raw_val = raw_val.replace("озу", "ram")
                raw_val = raw_val.replace("новый", "new").replace("запеч", "new")
                raw_val = raw_val.replace("идеал", "used")
                features[key] = raw_val
                
        return features

    @staticmethod
    def normalize_for_hash(text: str) -> List[str]:
        if not text:
            return []
        text = re.sub(r'[^\w\s]', '', text.lower())
        return text.split()

class TextMatcher:
    @staticmethod
    def calculate_similarity(target_text: str, candidates: List[str]) -> List[float]:
        if not TfidfVectorizer or not target_text or not candidates:
            return [0.0] * len(candidates)
            
        corpus = [target_text] + candidates
        
        try:
            vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4))
            tfidf_matrix = vectorizer.fit_transform(corpus)
            
            # Считаем сходство первого вектора (target) со всеми остальными
            cosine_sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])
            
            # Возвращаем плоский список
            return cosine_sim[0].tolist()
        except Exception:
            return [0.0] * len(candidates)