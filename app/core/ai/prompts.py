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
    def build_analysis_prompt(cls, items: List[Dict], priority: AnalysisPriority, current_item: Dict, user_instructions: str = "", rag_context: Optional[Dict] = None, search_mode: str = 'full') -> str:
        stats = cls._build_market_stats(items, current_item.get('title'))
        
        current_market_str = "Мало данных для статистики."
        if stats['sample_size'] > 2:
            current_market_str = (
                f"В ТЕКУЩЕЙ ВЫДАЧЕ (похожих лотов: {stats['cnt']}):\n"
                f"- Диапазон: {stats['min']} - {max(stats['max'], 1)} руб.\n"
                f"- Медиана: {stats['med']} руб. | Средняя: {stats['avg']} руб."
            )

        rag_block = ""
        rag_avg_price = 0
        if rag_context:
            med = rag_context.get('median_price', 0)
            avg = rag_context.get('avg_price', 0)
            rag_avg_price = avg
            knowledge = rag_context.get('knowledge', '')
            rag_block = (
                f"ИЗ ПАМЯТИ (Исторический опыт):\n"
                f"- Ист. Медиана: {med} руб.\n"
                f"- Ист. Средняя: {avg} руб.\n"
                f"- Знания: {knowledge}\n"
            )
        else:
            rag_block = "В памяти нет данных по этому товару."

        item_price = current_item.get('price', 0)
        item_views = current_item.get('views', 0)
        item_cond = str(current_item.get('condition', '')).lower()
        item_date = str(current_item.get('date_text', '')).lower()
        
        # --- Логика ЦЕНЫ ---
        price_analysis = []
        if item_price > 0 and stats['med'] > 0:
            diff_table = ((item_price - stats['med']) / stats['med']) * 100
            
            # Градации оценки цены
            if diff_table < -30:
                price_analysis.append(f"ЭКСТРЕМАЛЬНО НИЗКАЯ ЦЕНА (на {abs(int(diff_table))}% ниже рынка). Внимание: высокий риск скама или дефекта!")
            elif diff_table < -15:
                price_analysis.append(f"Отличная цена (на {abs(int(diff_table))}% ниже рынка). Potentially GREAT_DEAL.")
            elif diff_table < -5:
                price_analysis.append(f"Цена немного ниже рынка (на {abs(int(diff_table))}%). Выгодно.")
            elif diff_table > 30:
                price_analysis.append(f"Оверпрайс (+{int(diff_table)}%). Игнорировать.")
            elif diff_table > 10:
                price_analysis.append(f"Дороже рынка (+{int(diff_table)}%). Торг обязателен.")
            else:
                price_analysis.append("Справедливая рыночная цена (Fair Price).")
            
            # Доп. сравнение с памятью
            if rag_avg_price > 0:
                diff_rag = ((item_price - rag_avg_price) / rag_avg_price) * 100
                if diff_rag < -20: 
                    price_analysis.append(f"(Также дешевле исторических данных на {abs(int(diff_rag))}%).")

        price_str = " ".join(price_analysis) if price_analysis else "Цена не определена или мало данных."

        # --- Логика ПРОСМОТРОВ ---
        views_analysis = "Просмотры в норме."
        if search_mode == 'primary':
            # В Primary режиме просмотры не парсятся (обычно 0)
            views_analysis = "Просмотры: Нет данных (быстрый поиск). Не используй это как фактор."
        else:
            # В Full/Neuro режиме просмотры есть
            if item_views == 0:
                views_analysis = "0 просмотров: Только что выложено. Шанс забрать первым!"
            elif item_views < 50:
                 views_analysis = "Мало просмотров: объявление свежее или не популярное."
            elif item_views > 750 and item_price < stats['med'] * 0.8:
                views_analysis = f"ТРЕВОГА: {item_views} просмотров при низкой цене. Почему еще не купили? Проверь на скам/дефекты."
        
        # --- Логика СОСТОЯНИЯ ---
        cond_bonus = ""
        if any(x in item_cond for x in ['нов', 'new', 'идеал', 'запеч']):
            cond_bonus = "БОНУС: Состояние указано как НОВОЕ/ИДЕАЛ."
        elif any(x in item_cond for x in ['запчаст', 'сломан', 'дефект', 'не рабоч', 'разбит']):
            cond_bonus = "МИНУС: Товар сломан или на запчасти. Понижай оценку (если не ищем лом)."

        # --- Логика ДАТЫ ---
        date_analysis = ""
        if any(x in item_date for x in ['сегодня', 'час', 'мин', 'сек']):
            date_analysis = "ДАТА: Только что (Очень актуально)."
        elif any(x in item_date for x in ['вчера']):
            date_analysis = "ДАТА: Свежее (Вчера)."
        elif any(x in item_date for x in ['недел', 'месяц']):
            # Простая эвристика: если "3 недели" или "месяц" - это старо
            if '3 недел' in item_date or '4 недел' in item_date or 'месяц' in item_date:
                date_analysis = "ДАТА: СТАРОЕ (>20 дней). Вероятно, неликвид или продано."
        else:
            # Для абсолютных дат (20 октября) оставляем на откуп LLM
            pass

        # СБОРКА ПРОМПТА
        return f"""
{cls.SYSTEM_BASE}

[ОБЪЕКТ АНАЛИЗА]
Товар: "{current_item.get('title')}"
Цена: {item_price} руб.
Город: {current_item.get('city', 'N/A')}
Состояние: {current_item.get('condition', 'N/A')}
Дата: {item_date} | Просмотры: {item_views}
Описание:
\"\"\"
{current_item.get('description', '')[:2000]}
\"\"\"

[РЫНОЧНЫЙ КОНТЕКСТ]
1. {current_market_str}
2. {rag_block}

[ПОДСКАЗКИ АВТО-АНАЛИЗАТОРА]
- ЦЕНА: {price_str}
- АКТИВНОСТЬ: {views_analysis}
- КАЧЕСТВО: {cond_bonus}
- АКТУАЛЬНОСТЬ: {date_analysis}

[ИНСТРУКЦИИ ДЛЯ LLM]
1. ЦЕНА: Опирайся на подсказки анализатора, среднее по Таблице и Памяти. Если цена "Экстремально низкая" — ищи подвох. Если "Отличная" — GREAT_DEAL.
2. ОПИСАНИЕ: Внимательно читай описание! Ищи скрытые дефекты ("после майнинга", "без проверки"), которые отменяют низкую цену.
3. ДАТА: Если объявление старое (>30 дней) и цена хорошая — это подозрительно (почему не купили?). Снижай оценку.
4. СОСТОЯНИЕ: "Новое" лучше "Б/У". "На запчасти" — это BAD (если не просили иное).
5. РЕЖИМ ПОИСКА: Если указано "Нет данных по просмотрам", не выдумывай их влияние.

[ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ (ПРИОРИТЕТ ВЫШЕ ВСЕГО!)]
{user_instructions}

[ФОРМАТ ОТВЕТА (JSON)]
{{
  "verdict": "GREAT_DEAL" | "GOOD" | "BAD" | "SCAM",
  "reason": "Человеческий вывод (1-2 предложения). Упомяни цену, состояние и риски.",
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