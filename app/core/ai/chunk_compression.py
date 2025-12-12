import json
from typing import Tuple, Dict, Any
from app.core.log_manager import logger

class ChunkCompressor:
    """
    Сжимает чанки без потери критического смысла.
    Использует стратегии сокращения ключей и выборки данных в зависимости от типа.
    """
    
    @staticmethod
    def compress_product_chunk(content: Dict[str, Any]) -> Tuple[str, int]:
        """
        PRODUCT: сокращает до ключевых метрик цены и рисков.
        
        Сжатие:
        - summary: обрезается до 250 символов
        - price_analysis: оставляем avg, trend, trend_percent
        - risk_factors: топ-3
        - market_position: 1 буква (f/g/b/o)
        """
        try:
            analysis = content.get('analysis', {})
            price_analysis = analysis.get('price_analysis', {})
            
            # Безопасное получение первой буквы позиции
            mp = analysis.get('market_position', '?')
            mp_char = mp[0] if mp else '?'

            compressed = {
                "s": analysis.get('summary', '')[:250],
                "p": {
                    "a": price_analysis.get('avg'),
                    "t": price_analysis.get('trend'),
                    "tp": price_analysis.get('trend_percent')
                },
                "r": analysis.get('risk_factors', [])[:3],
                "m": mp_char
            }
            
            compressed_json = json.dumps(compressed, ensure_ascii=False)
            return compressed_json, len(compressed_json.encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error compressing PRODUCT chunk: {e}")
            return "", 0
    
    @staticmethod
    def compress_category_chunk(content: Dict[str, Any]) -> Tuple[str, int]:
        """
        CATEGORY: сокращает анализ подкатегорий.
        Оставляет топ-5 подкатегорий и ключевые инсайты.
        """
        try:
            analysis = content.get('analysis', {})
            subcats = analysis.get('subcategories', {})
            
            # Берем только тренд и цену для первых 5 подкатегорий
            compressed_subcats = {
                k: {'t': v.get('trend'), 'p': v.get('avg_price')}
                for i, (k, v) in enumerate(subcats.items())
                if i < 5 and isinstance(v, dict)
            }
            
            compressed = {
                "s": analysis.get('summary', '')[:200],
                "sc": compressed_subcats,
                "mi": analysis.get('market_insights', '')[:150],
                "sp": analysis.get('seasonal_patterns', '')[:100]
            }
            
            compressed_json = json.dumps(compressed, ensure_ascii=False)
            return compressed_json, len(compressed_json.encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error compressing CATEGORY chunk: {e}")
            return "", 0
    
    @staticmethod
    def compress_database_chunk(content: Dict[str, Any]) -> Tuple[str, int]:
        """
        DATABASE: сокращает до общих трендов.
        """
        try:
            analysis = content.get('analysis', {})
            
            compressed = {
                "sum": analysis.get('summary', '')[:300],
                "top": analysis.get('top_categories', [])[:3],
                "trends": analysis.get('key_trends', [])[:3]
            }
            
            compressed_json = json.dumps(compressed, ensure_ascii=False)
            return compressed_json, len(compressed_json.encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error compressing DATABASE chunk: {e}")
            return "", 0

    @staticmethod
    def compress_generic(content: Dict[str, Any]) -> Tuple[str, int]:
        """
        Fallback для неизвестных типов (AI_BEHAVIOR, CUSTOM).
        Просто сохраняет summary.
        """
        try:
            summary = content.get('summary') or content.get('analysis', {}).get('summary', '')
            compressed = {"s": summary[:500]}
            compressed_json = json.dumps(compressed, ensure_ascii=False)
            return compressed_json, len(compressed_json.encode('utf-8'))
        except Exception as e:
            return "", 0