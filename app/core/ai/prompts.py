"""
Система промптов для AI анализа
"""
import statistics
import re
from collections import defaultdict
from typing import List, Dict, Optional
from enum import IntEnum


class AnalysisPriority(IntEnum):
    """Приоритеты анализа"""
    PRICE = 1      # Фокус на цене
    DEFICIT = 2    # Фокус на дефиците и соотношении ЦКК
    QUALITY = 3    # Фокус на состоянии товара


class PromptBuilder:
    """Строитель промптов для AI"""
    
    # Базовый системный промпт
    SYSTEM_BASE = """Ты - AI-аналитик для бизнеса скупки-перепродажи товаров с Avito.

ТВОЯ ЗАДАЧА:
Оценивать каждое объявление с точки зрения выгоды для ПОКУПАТЕЛЯ (перекупщика).

Формат ответа:
{
  "verdict": "GREAT_DEAL" | "GOOD" | "BAD" | "SCAM",
  "reason": "краткое объяснение (до 80 символов)",
  "market_position": "below_market" | "fair" | "overpriced",
  "defects": true/false
}

КРИТЕРИИ:
- GREAT_DEAL: Цена значительно ниже рынка (на 15-30%), продавец живой, описание адекватное.
- GOOD: Честная цена, нормальный товар.
- BAD: Оверпрайс, мутное описание, перекуп.
- SCAM: Цена подозрительно низкая (в 2-3 раза), новый аккаунт, просьба писать в ватсап, доставка отключена.
"""
    
    # Промпт для нейро-фильтра
    NEURO_FILTER_TEMPLATE = """Ты - СТРОГИЙ ФИЛЬТР для парсера Avito.

ЗАДАЧА: Пропускать ТОЛЬКО релевантные объявления.

ИЩЕМ: {search_tags}
ИСКЛЮЧАЕМ: {ignore_tags}
ДОП. КРИТЕРИИ ПОЛЬЗОВАТЕЛЯ: {user_criteria}

ПРОВЕРЬ:
1. Соответствует ли товар тегам ИЩЕМ?
2. НЕ содержит ли игнор-теги?
3. Выполняются ли доп. критерии пользователя (КРИТИЧНО)?
4. Нет ли признаков скама/развода?

ОТВЕТ (JSON):
{{
  "verdict": "GOOD" | "BAD",
  "reason": "почему пропустил или отклонил"
}}

ПРАВИЛО: При МАЛЕЙШЕМ сомнении ставь BAD."""
    
    @staticmethod
    def select_priority(
        table_size: int,
        user_instructions: str,
        has_rag: bool,
        search_tags: List[str]
    ) -> AnalysisPriority:
        """
        Эвристика выбора приоритета анализа
        
        Args:
            table_size: Размер таблицы результатов
            user_instructions: Инструкции пользователя
            has_rag: Есть ли накопленные данные в RAG
            search_tags: Теги поиска
            
        Returns:
            Выбранный приоритет (1, 2 или 3)
        """
        instructions_lower = user_instructions.lower()
        
        # 1. Явное указание в инструкциях
        if any(word in instructions_lower for word in ["состояние", "новый", "качество", "отличный"]):
            return AnalysisPriority.QUALITY
        
        if any(word in instructions_lower for word in ["дефицит", "редкий", "уникальный"]):
            return AnalysisPriority.DEFICIT
        
        if any(word in instructions_lower for word in ["цена", "дешев", "выгод"]):
            return AnalysisPriority.PRICE
        
        # 2. Большая таблица + RAG = анализ дефицита
        if table_size > 50 and has_rag:
            return AnalysisPriority.DEFICIT
        
        # 3. Поиск дорогих товаров (электроника, техника) = фокус на качестве
        expensive_keywords = ["rtx", "gpu", "видеокарта", "процессор", "iphone", "macbook", "ноутбук"]
        if any(kw in " ".join(search_tags).lower() for kw in expensive_keywords):
            return AnalysisPriority.QUALITY
        
        # 4. Дефолт: цена (самый универсальный)
        return AnalysisPriority.PRICE
    
    @staticmethod
    def group_similar_items(items: List[Dict]) -> Dict[str, List[Dict]]:
        groups = defaultdict(list)

        for item in items:
            title = str(item.get('title', '')).lower()

            # Извлекаем ключевые слова (модель товара)
            # Убираем шум: "новый", "б/у", "срочно", "обмен" и т.д.
            noise_words = r'\b(новый|б/у|срочно|обмен|торг|продам|куплю|цена|руб|рублей)\b'
            clean_title = re.sub(noise_words, '', title)

            # Извлекаем модель/ключевые слова (первые 3-5 значимых слов)
            words = clean_title.split()
            significant_words = [w for w in words if len(w) > 2][:5]

            if significant_words:
                # Ключ группы = первые 3 значимых слова
                group_key = ' '.join(significant_words[:3])
                groups[group_key].append(item)
            else:
                # Если не смогли извлечь - отдельная группа
                groups[title[:30]].append(item)

        return dict(groups)

    @staticmethod
    def _build_market_stats(items: List[Dict], current_title: str) -> Dict:
        """Вспомогательный метод для статистики текущего батча"""
        if not items or not current_title:
            return {'sample_size': 0}
            
        # Упрощенная логика группировки
        prices = []
        current_words = set(current_title.lower().split())
        
        for item in items:
            item_price = item.get('price', 0)
            if not isinstance(item_price, (int, float)) or item_price < 100: continue
            
            # Грубая проверка похожести: пересечение слов > 30%
            item_words = set(str(item.get('title', '')).lower().split())
            intersection = current_words.intersection(item_words)
            if len(intersection) >= 2: # Хотя бы 2 общих слова
                 prices.append(item_price)

        if not prices:
            return {'sample_size': 0}
            
        return {
            "avg_price": int(statistics.mean(prices)),
            "median_price": int(statistics.median(prices)),
            "min_price": min(prices),
            "max_price": max(prices),
            "sample_size": len(prices)
        }
    
    @classmethod
    def build_analysis_prompt(cls, 
                            items: List[Dict], 
                            priority: AnalysisPriority, 
                            current_item: Dict, 
                            user_instructions: str = "",
                            rag_context: Optional[Dict] = None) -> str:
        
        # 1. Анализ текущего батча (Batch Context) - оставляем как было, это полезно
        stats = cls._build_market_stats(items, current_item.get('title'))
        
        batch_stats_block = ""
        if stats['sample_size'] > 2:
            batch_stats_block = (
                f"\n[СТАТИСТИКА ТЕКУЩЕЙ ВЫДАЧИ]\n"
                f"Мы спарсили {stats['sample_size']} похожих объявлений прямо сейчас.\n"
                f"Средняя цена: {stats['avg_price']}. Медиана: {stats['median_price']}.\n"
                f"Разброс цен: {stats['min_price']} - {stats['max_price']}.\n"
                f"Сравнивай товар с ЭТИМИ данными в первую очередь."
            )
        
        # 2. RAG Context (Историческая память) - НОВОЕ!
        rag_block = ""
        if rag_context:
            rag_block = (
                f"\n[ИСТОРИЧЕСКАЯ БАЗА (RAG)]\n"
                f"В нашей базе знаний найдено {rag_context['sample_count']} записей по запросу '{rag_context['keyword']}'.\n"
                f"Историческая средняя цена: {rag_context['avg_price']}.\n"
                f"Историческая медиана: {rag_context['median_price']}.\n"
                f"Нормальный диапазон цен: {rag_context['min_price']} - {rag_context['max_price']}.\n"
                f"ВАЖНО: Если цена текущего товара ({current_item.get('price')}) сильно отличается от исторической медианы ({rag_context['median_price']}), это повод для тревоги (SCAM) или радости (GREAT_DEAL)."
            )

        # 3. Инструкции пользователя
        instructions_block = ""
        if user_instructions.strip():
            instructions_block = f"\n[ОСОБЫЕ ИНСТРУКЦИИ]\n{user_instructions}"

        # 4. Фокус внимания (на основе приоритета)
        focus = ""
        if priority == AnalysisPriority.PRICE:
            focus = "ФОКУС: Ищем максимальную выгоду. Любое отклонение цены вниз проверяй на СКАМ. Если чисто - GREAT_DEAL."
        elif priority == AnalysisPriority.DEFICIT:
            focus = "ФОКУС: Редкость. Цена не важна. Главное - наличие товара."
        else:
            focus = "ФОКУС: Качество. Ищем идеальное состояние. Игнорируй слишком дешевые убитые варианты."

        # Сборка промпта
        full_prompt = (
            f"{cls.SYSTEM_BASE}\n"
            f"ТОВАР: {current_item.get('title')}\n"
            f"ЦЕНА: {current_item.get('price')}\n"
            f"ОПИСАНИЕ: {current_item.get('description')}\n"
            f"{batch_stats_block}\n"
            f"{rag_block}\n"
            f"{instructions_block}\n"
            f"{focus}\n"
            f"JSON:"
        )
        
        return full_prompt
    
    @classmethod
    def build_neuro_filter_prompt(
        cls,
        search_tags: List[str],
        ignore_tags: List[str],
        user_criteria: str = ""
    ) -> str:
        """Строит промпт для нейро-фильтрации"""
        return cls.NEURO_FILTER_TEMPLATE.format(
            search_tags=", ".join(search_tags) if search_tags else "Нет",
            ignore_tags=", ".join(ignore_tags) if ignore_tags else "Нет",
            user_criteria=user_criteria if user_criteria.strip() else "Нет"
        )