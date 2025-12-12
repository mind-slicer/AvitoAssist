"""
Система промптов для AI анализа (Специализация: Вторичный рынок ПК и комплектующих)
"""
import statistics
import re
from collections import defaultdict
from typing import List, Dict, Optional
from enum import IntEnum

class AnalysisPriority(IntEnum):
    PRICE = 1
    DEFICIT = 2
    QUALITY = 3

class PromptBuilder:
    # Список целевого железа для контекста
    HARDWARE_INTERESTS = """
=== СПИСОК ИНТЕРЕСУЮЩЕГО ЖЕЛЕЗА ===
1. ВИДЕОКАРТЫ:
   - Nvidia: RTX 50/40/30/20 series, GTX 16xx/10xx.
   - AMD: RX 9000/7000/6000/5000/500/400 series.
2. ПРОЦЕССОРЫ:
   - Intel: LGA 1851/1700/1200/1151(v1/v2)/1150/1155. Поколения: с 2-го по 15-е.
   - AMD: AM5, AM4. Ryzen 1000-9000 series.
3. МАТЕРИНСКИЕ ПЛАТЫ: Z/B/H чипсеты под указанные выше сокеты.
4. ОПЕРАТИВНАЯ ПАМЯТЬ:
   - DDR5.
   - DDR4 (частоты 2133-4000+).
5. НАКОПИТЕЛИ: NVMe M.2, SATA SSD (от 60gb до 1tb+), HDD (от 1tb).
6. БЛОКИ ПИТАНИЯ: От 500W до 1000W+.
7. ОХЛАЖДЕНИЕ: Башенные кулеры, СВО (водянка).
8. ГОТОВЫЕ СБОРКИ, НОУТБУКИ, МОНИТОРЫ, КОРПУСА.
===================================
"""

    # Базовый системный промпт
    SYSTEM_BASE = f"""Ты — циничный и профессиональный скупщик компьютерной техники на вторичном рынке (Avito). 
Твоя цель — найти ликвидный товар для перепродажи с прибылью.

{HARDWARE_INTERESTS}

ПРАВИЛА АНАЛИЗА:
1. ИГНОРИРУЙ воду в описании ("тянет все игры", "летает"). Смотри только на сухие факты: модель, состояние, комплект, цена.
2. ЦЕНА: Опирайся ТОЛЬКО на предоставленную статистику цен (текущую выдачу и RAG). Не выдумывай цены из головы.
3. СКАМ-ТРИГГЕРЫ: 
   - Цена в 2 раза ниже рынка без причины.
   - "Только Авито доставка" на новый аккаунт.
   - "Пишите в ватсап".
   - Видеокарты после майнинга по цене новых.
4. ВЕРДИКТЫ:
   - GREAT_DEAL: Жирный вариант. Цена ниже рынка на 20%+, либо редкое железо по низу рынка. Продавец похож на частника.
   - GOOD: Честная рыночная цена, можно брать для себя или быстрой перепродажи с небольшой маржой.
   - BAD: Оверпрайс (дорого), хлам, древнее железо (775 сокет и т.д.), либо восстановленное после майнинга "как новое".
   - SCAM: Явный развод, мутные схемы, отказ от проверок.

Формат ответа (JSON):
{{
  "verdict": "GREAT_DEAL" | "GOOD" | "BAD" | "SCAM",
  "reason": "Жесткий и краткий комментарий скупщика (макс 10 слов).",
  "market_position": "below_market" | "fair" | "overpriced",
  "defects": true/false
}}
"""
    
    # Промпт для нейро-фильтра
    NEURO_FILTER_TEMPLATE = """
Ты работаешь ЖЁСТКИМ фильтром объявлений Авито для скупщика компьютерной техники.
Твоя задача — решить, стоит ли вообще рассматривать объявление.

[ПОИСКОВЫЕ ТЕГИ]
Основной запрос: {search_tags}
Игнорируем (бан-слова): {ignore_tags}

[ДОП. КРИТЕРИИ ОТ ПОЛЬЗОВАТЕЛЯ]
{user_criteria}

ПРАВИЛА ФИЛЬТРА:

1. Вердикт может быть ТОЛЬКО:
   - GOOD  — объявление подходит под запрос и критерии.
   - BAD   — объявление не подходит или есть сомнения.

2. Всегда учитывай:
   - Заголовок и описание объявления.
   - Поисковые теги (search_tags) — товар должен им соответствовать.
   - Бан-слова (ignore_tags) — если что-то из этого явно присутствует, вердикт ОБЯЗАТЕЛЬНО BAD.

3. Доп. критерии (user_criteria) ВАЖНЕЕ нейросети:
   - Если пользователь просит "только по гарантии" — объявление считается подходящим ТОЛЬКО если гарантия
     явно указана в тексте (слова типа "гарантия", "чек", "оставшаяся гарантия" и т.п.).
   - Если критерий не выполнен ЯВНО — ставь BAD, даже если остальное выглядит неплохо.
   - Если критериев нет, используй пункты 1 и 2 фильтрации.

4. Если информации недостаточно, чтобы уверенно сказать GOOD — ставь BAD.

ФОРМАТ ОТВЕТА:
Отвечай СТРОГО одним JSON-объектом без пояснений вокруг:

{{
  "verdict": "GOOD" или "BAD",
  "reason": "Краткое объяснение на русском, 1–2 предложения"
}}

НЕ добавляй никакой другой текст.
"""
    
    @staticmethod
    def select_priority(table_size: int, user_instructions: str, has_rag: bool, search_tags: List[str]) -> AnalysisPriority:
        txt = user_instructions.lower()
        if any(x in txt for x in ["состояние", "гарант", "чек", "комплект"]): return AnalysisPriority.QUALITY
        if any(x in txt for x in ["редк", "дефиц"]): return AnalysisPriority.DEFICIT
        return AnalysisPriority.PRICE
    
    @staticmethod
    def _build_market_stats(items: List[Dict], current_title: str) -> Dict:
        default_stats = {
            "sample_size": 0,
            "avg": 0,
            "med": 0,
            "min": 0,
            "max": 0,
            "cnt": 0,
        }

        if not items or not current_title:
            return default_stats

        prices = [
            i.get("price", 0)
            for i in items
            if isinstance(i.get("price"), int) and i.get("price") > 500
        ]

        if not prices:
            return default_stats

        return {
            "sample_size": len(prices),
            "avg": int(statistics.mean(prices)),
            "med": int(statistics.median(prices)),
            "min": min(prices),
            "max": max(prices),
            "cnt": len(prices),
        }
    
    @classmethod
    def build_analysis_prompt(cls, items: List[Dict], priority: AnalysisPriority, current_item: Dict, user_instructions: str = "", rag_context: Optional[Dict] = None) -> str:
        # 1. Сбор данных статистики (ТЕКУЩАЯ СИТУАЦИЯ)
        stats = cls._build_market_stats(items, current_item.get('title'))
        
        # Формируем строку текущей статистики
        current_market_str = "Нет данных."
        if stats['sample_size'] > 0:
            current_market_str = (
                f"Найдено {stats['cnt']} похожих лотов прямо сейчас.\n"
                f"- Диапазон цен: от {stats['min']} до {stats['max']} руб.\n"
                f"- Медиана текущей выдачи: {stats['med']} руб.\n"
                f"- Средняя цена: {stats['avg']} руб."
            )

        # 2. Формирование блока RAG (ИСТОРИЧЕСКАЯ ПАМЯТЬ)
        rag_block = ""
        if rag_context:
            med = rag_context.get('median_price', 0)
            avg = rag_context.get('avg_price', 0)
            cnt = rag_context.get('sample_count', 0)
            knowledge = rag_context.get('knowledge', '')
            
            # Если это "заглушка" или чанка нет -> включаем режим Live-статистики
            if not knowledge or "Нет детального" in knowledge:
                rag_block = (
                    f"СТАТУС ПАМЯТИ: Чанк не сформирован (Live-режим).\n"
                    f"Историческая статистика (база {cnt} товаров):\n"
                    f"- Историческая Медиана: {med} руб.\n"
                    f"- Историческая Средняя: {avg} руб.\n"
                    f"ИНСТРУКЦИЯ: Сравнивай цену товара ({current_item.get('price')} руб) с исторической медианой ({med}). "
                    f"Если цена сильно ниже — ищи подвох."
                )
            else:
                # Если есть полноценный чанк
                rag_block = (
                    f"СТАТУС ПАМЯТИ: Активен чанк знаний.\n"
                    f"{knowledge}\n"
                    f"Базовые метрики категории: Медиана {med} руб, Средняя {avg} руб.\n"
                    f"ИНСТРУКЦИЯ: Используй этот контекст для глубокой оценки ликвидности."
                )
        else:
            rag_block = "Данных в памяти нет. Опирайся только на текущую выдачу."

        # 3. Блок правил
        strat = "Максимальная маржа. Ищи ошибки в цене."
        if priority == AnalysisPriority.QUALITY: strat = "Идеальное состояние, гарантия, комплект."
        elif priority == AnalysisPriority.DEFICIT: strat = "Редкое/Топовое железо."
        user_rules = f"{strat}\n{user_instructions}" if user_instructions else strat

        # 4. Детали товара
        item_details = (
            f"Товар: {current_item.get('title')}\n"
            f"Цена: {current_item.get('price')} ₽\n"
            f"Город: {current_item.get('city', 'N/A')}\n"
            f"Дата: {current_item.get('date_text', 'N/A')} | Просмотры: {current_item.get('views', 0)}\n"
            f"Продавец ID: {current_item.get('seller_id', 'N/A')}\n"
            f"Описание:\n{current_item.get('description', '')[:1200]}" # Чуть увеличили лимит
        )

        return f"""
{cls.SYSTEM_BASE}

=============================================================
РАЗДЕЛ 1: ЖЁСТКИЕ ПРАВИЛА (ПРИОРИТЕТ 100%)
=============================================================
1. Стратегия: {user_rules}
2. Не выдумывай цены.
3. Игнорируй маркетинговый шум.

=============================================================
РАЗДЕЛ 2: КОНТЕКСТ АНАЛИЗА (ПРИОРИТЕТ 40%)
=============================================================
[А] ТЕКУЩАЯ СИТУАЦИЯ (Прямо сейчас в поиске):
{current_market_str}

[Б] ПАМЯТЬ ИИ (Исторический опыт):
{rag_block}

ИНСТРУКЦИЯ ПО КОНТЕКСТУ:
Если "Текущая медиана" и "Историческая медиана" сильно отличаются, 
значит рынок изменился (тренд). Учитывай это.

=============================================================
РАЗДЕЛ 3: ОБЪЕКТ АНАЛИЗА
=============================================================
{item_details}

=============================================================
ЗАДАЧА
=============================================================
Дай вердикт в JSON:
{{
  "verdict": "GREAT_DEAL" | "GOOD" | "BAD" | "SCAM",
  "reason": "Жесткий комментарий (макс 10 слов)",
  "market_position": "below_market" | "fair" | "overpriced",
  "defects": true/false
}}
"""
    
    @classmethod
    def build_knowledge_prompt(cls, product_key: str, items: List[Dict]) -> str:
        """
        Промпт для генерации знаний (сводки) по категории (Этап Культивации).
        """
        sample_items = items[:40] # Берем сэмпл для анализа
        
        items_text = ""
        prices = []
        for i in sample_items:
            p = i.get('price', 0)
            if isinstance(p, int) and p > 0: prices.append(p)
            desc = i.get('description', '')[:100].replace('\n', ' ')
            items_text += f"- {i.get('title')} | {p} руб | {desc}\n"

        if not prices: return ""

        avg = int(sum(prices) / len(prices))
        med = int(statistics.median(prices))

        return f"""
{cls.SYSTEM_BASE}

Твоя задача — проанализировать выборку товаров из категории: "{product_key}".
Создай "Заметку для базы знаний", которая поможет оценивать такие товары в будущем.

СТАТИСТИКА:
- Лотов: {len(sample_items)}
- Средняя: {avg} | Медиана: {med}
- Мин: {min(prices)} | Макс: {max(prices)}

СПИСОК (Сэмпл):
{items_text}

ЗАДАНИЕ:
Напиши JSON-отчет с анализом рынка.
1. summary: Краткая выжимка (1-2 предл). Что это, норма цены?
2. risk_factors: На что смотреть? (майнинг, подделки, дефекты).
3. price_range_notes: Текстовое описание диапазонов цен.

JSON ФОРМАТ:
{{
  "summary": "...",
  "risk_factors": "...",
  "price_range_notes": "..."
}}
"""

    @classmethod
    def build_neuro_filter_prompt(
    cls,
    search_tags: List[str],
    ignore_tags: List[str],
    user_criteria: str = ""
    ) -> str:
        """
        Строит промпт для нейро-фильтра:
        - при пустых user_criteria работает как "чистый" фильтр по search_tags/ignore_tags;
        - при непустых user_criteria явно делает их жёсткими правилами.
        """
    
        # 1. Форматируем теги для чтения моделью
        if isinstance(search_tags, str):
            # на случай, если где-то передали строку
            search_list = [t.strip() for t in search_tags.split(",") if t.strip()]
        else:
            search_list = [t.strip() for t in search_tags or [] if t.strip()]
    
        if isinstance(ignore_tags, str):
            ignore_list = [t.strip() for t in ignore_tags.split(",") if t.strip()]
        else:
            ignore_list = [t.strip() for t in ignore_tags or [] if t.strip()]
    
        search_str = ", ".join(search_list) if search_list else "Любые комплектующие из списка интересов"
        ignore_str = ", ".join(ignore_list) if ignore_list else "Нет (бан-слов нет)"
    
        # 2. Блок доп. критериев
        user_criteria = (user_criteria or "").strip()
        if not user_criteria:
            # Чистый нейро-поиск: явно говорим, что доп. критериев нет
            criteria_block = (
                "НЕТ дополнительных критериев. Оцени объявление ТОЛЬКО по поисковым тегам "
                "и бан-словам, строго следуя правилам фильтра выше."
            )
        else:
            # Явно подчёркиваем, что это жёсткие правила от пользователя
            criteria_block = (
                "Пользователь задал СЛЕДУЮЩИЕ ЖЁСТКИЕ критерии отбора "
                "(они важнее любых эвристик нейросети):\n"
                f"{user_criteria}"
            )
    
        return cls.NEURO_FILTER_TEMPLATE.format(
            search_tags=search_str,
            ignore_tags=ignore_str,
            user_criteria=criteria_block,
        )

class ChunkCultivationPrompts:
    """Специализированные промпты для создания структур знаний (чанков)"""
    
    @staticmethod
    def build_product_cultivation_prompt(product_key: str, items: list) -> str:
        """Промпт для анализа конкретного товара/серии"""
        
        # Формируем компактный список примеров
        items_text = ""
        for item in items[:40]: # Лимит 40, чтобы не забить контекст
            p = item.get('price', 0)
            t = item.get('title', 'N/A')
            v = item.get('verdict', 'N/A')
            items_text += f"- {t} | {p} руб. | {v}\n"
        
        return f"""
        ТЫ — ПРОФЕССИОНАЛЬНЫЙ РЫНОЧНЫЙ АНАЛИТИК. ТВОЯ ЗАДАЧА — СОЗДАТЬ СТРУКТУРИРОВАННОЕ ЗНАНИЕ О ТОВАРЕ.
        
        ТОВАР: "{product_key}"
        ИСХОДНЫЕ ДАННЫЕ (список объявлений):
        {items_text}
        
        ТРЕБОВАНИЕ:
        Проанализируй эти данные и верни JSON (без markdown, только JSON) следующей структуры:
        {{
            "summary": "Краткий аналитический обзор рынка этого товара (2-3 предложения). Цены, спрос, доступность.",
            "price_analysis": {{
                "avg": (число, средняя цена),
                "median": (число, медиана),
                "trend": "up" или "down" или "stable",
                "trend_percent": (число, примерный процент изменения, если есть данные, иначе 0)
            }},
            "risk_factors": ["список", "конкретных", "рисков", "покупки"],
            "market_position": "fair" (справедливая) или "overpriced" (перегрет) или "undervalued" (недооценен),
            "seller_quality": "mixed" или "high" или "low"
        }}
        
        ВАЖНО: Опирайся ТОЛЬКО на предоставленные данные. Если данных мало, пиши честно.
        """
    
    @staticmethod
    def build_category_cultivation_prompt(category_key: str, stats: dict) -> str:
        """Промпт для анализа целой категории"""
        
        return f"""
        АНАЛИЗ КАТЕГОРИИ ТОВАРОВ: "{category_key}"
        
        СТАТИСТИКА:
        - Средняя цена: {stats.get('avg_price')}
        - Медианная цена: {stats.get('median_price')}
        - Минимум: {stats.get('min_price')}
        - Максимум: {stats.get('max_price')}
        - Количество лотов: {stats.get('sample_count')}
        - Тренд: {stats.get('trend')} ({stats.get('trend_percent')}%)
        
        ЗАДАЧА: Вернуть JSON-структуру знаний о категории.
        
        FORMAT JSON:
        {{
            "summary": "Общее описание состояния рынка в этой категории.",
            "subcategories": {{
                "main": {{ "trend": "{stats.get('trend')}", "avg_price": {stats.get('avg_price')} }}
            }},
            "market_insights": "Ключевые инсайты (например: много перекупов, или цены падают).",
            "seasonal_patterns": "Есть ли сезонность (предположение на основе типа товара)."
        }}
        """
    
    @staticmethod
    def build_database_cultivation_prompt(db_stats: dict) -> str:
        """Промпт для анализа всей базы"""
        
        return f"""
        ГЛОБАЛЬНЫЙ АНАЛИЗ БАЗЫ ДАННЫХ.
        
        ВСЕГО ТОВАРОВ: {db_stats.get('total_items')}
        ВСЕГО КАТЕГОРИЙ: {db_stats.get('total_categories')}
        
        ЗАДАЧА: Сформировать отчет о составе базы.
        
        FORMAT JSON:
        {{
            "summary": "Обзор того, какие данные преобладают в базе.",
            "top_categories": ["название_категории_1", "название_категории_2"],
            "key_trends": ["общий тренд 1", "общий тренд 2"],
            "insights": "Выводы о том, что ищет пользователь."
        }}
        """
        
    @staticmethod
    def build_ai_behavior_cultivation_prompt(actions_log: list) -> str:
        return """
        { "summary": "Log analysis not implemented yet." }
        """