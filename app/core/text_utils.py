import re
import hashlib
from typing import Dict, List

class FeatureExtractor:
    """Extracts technical specifications from item titles and descriptions."""
    
    # Регулярки для выделения ключевых характеристик
    PATTERNS = {
        'storage': r'\b(\d+)\s*(gb|гб|tb|тб)\b',       # 128gb, 1tb
        'ram': r'\b(\d+)\s*(gb|гб)\s*(ram|озу)\b',     # 16gb ram
        'model_suffix': r'\b(pro|max|plus|ultra|mini|air|slim|lite|se)\b', # iphone 13 PRO
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
                # Нормализация: убираем пробелы (128 gb -> 128gb)
                raw_val = match.group(0).replace(" ", "")
                # Унификация (гб -> gb)
                raw_val = raw_val.replace("гб", "gb").replace("тб", "tb")
                raw_val = raw_val.replace("озу", "ram")
                raw_val = raw_val.replace("новый", "new").replace("запеч", "new")
                raw_val = raw_val.replace("идеал", "used") # Идеал все равно б/у
                features[key] = raw_val
                
        return features

    @staticmethod
    def normalize_for_hash(text: str) -> List[str]:
        """Cleans text for hashing: removes punctuation, lowers case."""
        if not text:
            return []
        # Оставляем только буквы и цифры
        text = re.sub(r'[^\w\s]', '', text.lower())
        return text.split()

class SimHash:
    """Locality Sensitive Hashing for finding near-duplicate text."""
    
    @staticmethod
    def get_hash(text: str) -> int:
        features = FeatureExtractor.normalize_for_hash(text)
        if not features:
            return 0
            
        hash_bits = [0] * 64
        
        for feature in features:
            # MD5 hash of the word
            h = int(hashlib.md5(feature.encode('utf-8')).hexdigest(), 16)
            for i in range(64):
                bit = (h >> i) & 1
                if bit:
                    hash_bits[i] += 1
                else:
                    hash_bits[i] -= 1
        
        fingerprint = 0
        for i in range(64):
            if hash_bits[i] > 0:
                fingerprint |= (1 << i)
        
        return fingerprint

    @staticmethod
    def distance(hash1: int, hash2: int) -> int:
        """Calculates Hamming distance between two 64-bit integers."""
        # XOR gives bits that are different
        x = (hash1 ^ hash2) & ((1 << 64) - 1)
        ans = 0
        while x:
            ans += 1
            x &= x - 1
        return ans