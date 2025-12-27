import statistics
from typing import List, Dict, Optional
from enum import IntEnum

class AnalysisPriority(IntEnum):
    PRICE = 1
    DEFICIT = 2
    QUALITY = 3

class PromptBuilder:
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

    SYSTEM_BASE = f"""Ты — профессиональный скупщик новой и Б/У компьютерной техники на Avito.
Твоя цель — купить максимально дёшево у частника и быстро перепродать с маржей 20–50% .

{HARDWARE_INTERESTS}

КЛЮЧЕВЫЕ ПРИОРИТЕТЫ:
1. Максимизация маржи: ищи цены в нижнем квартиле рынка (q25_price) или ниже — это реальные цены от частников.
2. Медиана (median_price) часто завышена перекупами — используй её только как верхнюю границу "нормальной" цены.
3. Ликвидность: товар должен продаваться быстро.
4. Риски: майнинг, скрытые дефекты, отсутствие коробки/чека, скам-схемы.
5. Игнорируй воду в описании ("тянет все игры", "летает"). Смотри только на сухие факты: модель, состояние, комплект, цена.
6. Опирайся на предоставленную статистику цен (текущую выдачу и память). Не выдумывай цены из головы.

ПРАВИЛА ОЦЕНКИ:
    - GREAT_DEAL — цена ≤ q25_price - 10% (или сильно ниже q25 при хорошем состоянии). Это жирный вариант для быстрой перепродажи.
    - GOOD — цена между q25_price и median_price, минимальные риски, ликвидная модель.
    - BAD — цена выше медианы, низкая ликвидность, подозрительное состояние, оверпрайс.
    - SCAM — цена в 2+ раза ниже q25 без причины, подозрительное описание объявления, много "воды" вне контекста товара, отказ от проверки.

ОБЯЗАТЕЛЬНЫЙ ФОРМАТ ОТВЕТА — ТОЛЬКО ВАЛИДНЫЙ JSON БЕЗ ЛИШНЕГО ТЕКСТА:
{{
  "verdict": "GREAT_DEAL" | "GOOD" | "BAD" | "SCAM",
  "reason": "Краткое жёсткое объяснение на русском (6–12 слов)",
  "market_position": "great_deal" | "good_zone" | "overpriced" | "scam_low",
  "expected_margin_percent": 15–50,
  "risks": ["риск1", "риск2"],
  "recommendation": "Брать срочно" | "Можно взять" | "Пропустить" | "Избегать"
}}
"""
    
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
        
        price_analysis = []
        if item_price > 0 and stats['med'] > 0:
            diff_table = ((item_price - stats['med']) / stats['med']) * 100
            
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
            
            if rag_avg_price > 0:
                diff_rag = ((item_price - rag_avg_price) / rag_avg_price) * 100
                if diff_rag < -20: 
                    price_analysis.append(f"(Также дешевле исторических данных на {abs(int(diff_rag))}%).")

        price_str = " ".join(price_analysis) if price_analysis else "Цена не определена или мало данных."

        # --- Логика ПРОСМОТРОВ ---
        views_analysis = "Просмотры в норме."
        if search_mode == 'primary':
            views_analysis = "Просмотры: Нет данных (быстрый поиск). Не используй это как фактор."
        else:
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
            if '3 недел' in item_date or '4 недел' in item_date or 'месяц' in item_date:
                date_analysis = "ДАТА: СТАРОЕ (>20 дней). Вероятно, неликвид или продано."
        else:
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
    def build_neuro_filter_prompt(
    cls,
    search_tags: List[str],
    ignore_tags: List[str],
    user_criteria: str = ""
    ) -> str:
        if isinstance(search_tags, str):
            search_list = [t.strip() for t in search_tags.split(",") if t.strip()]
        else:
            search_list = [t.strip() for t in search_tags or [] if t.strip()]
    
        if isinstance(ignore_tags, str):
            ignore_list = [t.strip() for t in ignore_tags.split(",") if t.strip()]
        else:
            ignore_list = [t.strip() for t in ignore_tags or [] if t.strip()]
    
        search_str = ", ".join(search_list) if search_list else "Любые комплектующие из списка интересов"
        ignore_str = ", ".join(ignore_list) if ignore_list else "Нет (бан-слов нет)"
    
        user_criteria = (user_criteria or "").strip()
        if not user_criteria:
            criteria_block = (
                "НЕТ дополнительных критериев. Оцени объявление ТОЛЬКО по поисковым тегам "
                "и бан-словам, строго следуя правилам фильтра выше."
            )
        else:
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
    @staticmethod
    def build_product_cultivation_prompt(product_key: str, items: list) -> str:  
        items_text = ""
        for item in items[:40]:
            p = item.get('price', 0)
            t = item.get('title', 'N/A')
            v = item.get('verdict', 'N/A')
            items_text += f"- {t} | {p} руб. | {v}\n"
        
        return f"""
        ТЫ — ПРОФЕССИОНАЛЬНЫЙ РЫНОЧНЫЙ АНАЛИТИК по новому и Б/У компьютерному железу.
        ТОВАР: "{product_key}"

        ИСХОДНЫЕ ДАННЫЕ (объявления):
        {items_text}

        ТРЕБОВАНИЕ: Проанализируй рынок и верни ТОЛЬКО JSON следующей структуры:

        {{
            "summary": "Краткий обзор рынка в 2–3 предложения. Укажи диапазон цен от частников и перекупов.",
            "price_analysis": {{
                "q25_price": (нижний квартиль — цель для покупки),
                "median_price": (медиана рынка),
                "trend": "up" | "down" | "stable",
                "liquidity": "high" | "medium" | "low"
            }},
            "risk_factors": ["риск1", "риск2"],
            "best_buy_zone": "Цены до X руб. — выгодная покупка",
            "seller_insights": "Частники преобладают" | "Много перекупов" | "Смешанно"
        }}
        ВАЖНО: Нижний квартиль (q25) — главная цель для скупщика!
        """
    
    @staticmethod
    def build_category_cultivation_prompt(category_key: str, stats: dict) -> str:    
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