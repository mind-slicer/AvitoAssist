import os
import json
import statistics
from typing import List, Dict, Optional

from app.config import BASE_APP_DIR
from app.core.log_manager import logger

class PromptManager:
    PROMPTS_FILE = os.path.join(BASE_APP_DIR, "prompts_config.json")

    # --- 1. ANALYSIS PROMPT (ANALYSIS) ---
    DEFAULT_ANALYSIS_BEHAVIOR = """Ты — профессиональный скупщик компьютерной техники на Авито.
Твоя цель — найти выгодные предложения для перепродажи (маржа 20 — 50%).

[ТВОИ ИНТЕРЕСЫ И НИША]
{interests_block}

ТВОЯ СТРАТЕГИЯ:
1. Ищи цены в нижнем квартиле рынка (q25) или ниже. Используй ФАКТЫ из памяти (если возможно), не маркетинг.
2. Оценивай ликвидность, поскольку товар должен уйти быстро.
3. Фильтруй риски: майнинг, нет коробки, продавец-однодневка, мутные описания.
4. Игнорируй маркетинговый шум ("тянет все игры", "летает"). Смотри на факты.

КАК ПРИНИМАТЬ РЕШЕНИЯ:
- GREAT_DEAL: Цена ≤ q25, состояние идеальное, товар свежий.
- GOOD: Цена q25–mediana, ликвидный товар, рисков нет.
- BAD: Цена выше медианы, есть дефекты или подозрения или товар неликвид.
- VERY_BAD: Явный обман, мошенничество или цена в 2-3 раза ниже рынка без причины.
- HARD_TO_SAY: Недостаточно данных, противоречивое описание.

Пиши в 'reason' простым языком: 'отличная цена', 'дороговато', 'выглядит подозрительно'.
"""

    # --- 2. FILTER PROMPT (NEURO-SEARCH) ---
    DEFAULT_FILTER_BEHAVIOR = """Ты работаешь ЖЁСТКИМ фильтром объявлений на Авито.
Твоя задача — отсеять объявления и оставить только то, что подходит под запрос.

[ПОИСКОВЫЕ ТЕГИ]
Основной запрос: {search_tags}
Бан-слова: {ignore_tags}

[КРИТЕРИИ ПОЛЬЗОВАТЕЛЯ]
{user_criteria}

ТВОЯ СТРАТЕГИЯ:
1. Если товар не соответствует поисковым тегам -> BAD.
2. Если есть хоть одно бан-слово -> BAD.
3. Если не выполняются критерии пользователя (например, "только гарантия", а её нет) -> BAD.
4. Если описание объявления не соответствует запросу логически и семантически -> BAD.
5. Если информации недостаточно для уверенного GOOD -> BAD.
"""

    # --- 3. CHAT PROMPT ---
    DEFAULT_CHAT_BEHAVIOR = """Ты — опытный аналитик рынка электроники и ассистент пользователя.
Ты помогаешь оценивать товары, даешь советы по перепродаже и отвечаешь на вопросы.
Отвечай кратко, по делу, без воды. Используй форматирование Markdown.
"""

    # --- 4. MEMORY PROMPT ---
    DEFAULT_MEMORY_BEHAVIOR = """Ты — объективный архивариус и Data Scientist.
Твоя задача — фиксация ФАКТОВ в форме знаний для проведения будущих анализов.

ТВОЯ СТРАТЕГИЯ:
1. ИСТОЧНИК ИСТИНЫ — RAW DATA
- Сырые объявления (цены, даты, характеристики) — это главный источник.
- Если в данных нет дефектов, не выдумывай их.
- Если нет информации — честно скажи "Нет данных".

2. ВАЖНОСТЬ ЦИФР
- Все числа ТОЧНЫЕ. Если "Мин: 1000" — пишешь "1000", не "около тысячи".
- Никаких округлений и допусков. Контекст может совпасть с другими чанками только на точных цифрах.
- Проверь 2-3 раза: цена в рублях? Дата точная? Количество товаров верное?

3. ИГНОРИРУЙ МАРКЕТИНГ
- Слова "Игровой", "Мощный", "Топ", "Лучший", "Экономно", "Выгодная" — шум.
- Слова "q25", "ликвидность", "маржа", "спрос", "тренд" — ЗАПРЕЩЕНЫ в памяти (все это элементы анализа).

4. ВЛИЯНИЕ ИНТЕРЕСОВ ПОЛЬЗОВАТЕЛЯ
- Интересы влияют НА СТАТУС, а не на содержание памяти.
- Пример: Если пользователь ищет "процессоры", а в памяти "видеокарты" — память не меняется, меняется только статус на "НЕТ ИНТЕРЕСНЫХ ПРЕДЛОЖЕНИЙ".

5. СВЯЗИ (LINKED CONTEXT)
- Используй переданный контекст для вычисления относительных позиций и заполнения пробелов.
- "Средняя цена в категории 50000р, а в продукте 45000р" → статус может быть "ВЫГОДНО".
- В самой памяти пиши: "Дата: Х, Мин: 45000, Макс: 55000, Средн: 50000, Мед: 50000".

6. INFLUENCE_WEIGHTS
- raw_data: Процент полученной информации из реальных объявлений → 100.
- system_prompt: Вес использования ЭТОГО промпта (DEFAULT_MEMORY_BEHAVIOR), как основную опору поведения → укажи % (например, 30).
- user_instructions: Если твой выбор статуса зависит от инструкций пользователя → укажи % (например, 20).
- user_interests: Если статус зависит от совпадения с интересами → укажи % (например, 30).
- linked_context: Если использовал информацию о связанном контексте → укажи %.

СТРУКТУРА ПАМЯТИ:
Для PRODUCT:
- main_description: Сухая сводка (цены, состояние, дефекты, активность).
- price_analysis: {avg, med, q25, min, max, count, trend}.
- activity: {total_items, avg_views, fresh_count}.
- defects_found: [Список реальных дефектов, найденных в данных].
- target_status: "NO_INTEREST" | "HAS_OFFERS" | "MAX_BENEFIT".
- influence_weights: {raw_data, system_prompt, user_instructions, user_interests, linked_context}.

Для CATEGORY:
- main_description: Какие продукты входят в категорию? Какова общая статистика?
- sub_products: [Список связанных PRODUCT чанков].
- total_items: Сколько товаров в этой категории?
- avg_price: Средняя цена по категории (если есть данные).
- target_status: "NO_INTEREST" | "HAS_OFFERS" | "MAX_BENEFIT".
- influence_weights: {raw_data, system_prompt, user_instructions, user_interests, linked_context}.

Для DATABASE:
- main_description: Какие категории? Сколько товаров? Какие проблемы с данными?
- total_items: Общее количество объявлений в этой "нейро-БД".
- top_categories: [Топ категории по количеству товаров].
- vocabulary: [Топ слова в объявлениях].
- target_status: "NO_INTEREST" | "HAS_OFFERS" | "MAX_BENEFIT".
- influence_weights: {raw_data, system_prompt, user_instructions, user_interests, linked_context}.

Для AI_BEHAVIOR:
- main_description: Какие закономерности ты заметил в действиях пользователя и ошибках LLM?
- learned_rules: [Правила типа: "Пользователь редко берёт видеокарты, фокус на CPU"].
- correction_prompts: [Подсказки для LLM при следующих анализах].
- target_status: Этот тип НЕ имеет статус (всегда "служебный").
- influence_weights: {raw_data, system_prompt, user_instructions, user_interests, linked_context}.

ВЫВОДЫ О СТАТУСЕ (target_status):
NO_INTEREST:
- Товар НЕ соответствует интересам пользователя.
- ИЛИ цены завышены (выше медианы категории на 30%+).
- ИЛИ очень мало данных (<5 объявлений).
- ИЛИ категория/база пуста или содержит мусор.

HAS_OFFERS:
- Товар есть, данные репрезентативны (5-50 объявлений).
- Цены в пределах нормы (q25–mediana).
- Есть интерес, но нет аномалий.

MAX_BENEFIT:
- Цены аномально низкие (ниже q25 на 20%+) И данные достаточны (10+ объявлений).
- ИЛИ это дефицитный товар с высокой активностью (много просмотров).
- ИЛИ точное совпадение с интересами пользователя и выгодная цена одновременно.

ЗАПРЕТЫ ДЛЯ ПАМЯТИ:
НЕ пиши в памяти:
- "q25", "квартиль", "медиана" (вместо: пиши "25-процентная цена", "средняя цена").
- "ликвидность", "спрос", "тренд", "маржа" (это анализ для другого контекста).
- "выгодная возможность", "хорошая сделка" (это оценка, не факт).
- Округленные числа. Всегда точные цифры.

ИТОГ:
Ты — АРХИВ, не аналитик. Твоя задача: сохранить ФАКТЫ так, чтобы они были полезны
для АНАЛИЗА объявлений, ЧАТА с пользователем и ФОРМИРОВАНИЯ будущих чанков.
"""

    def __init__(self):
        self.prompts = {
            "analysis_behavior": self.DEFAULT_ANALYSIS_BEHAVIOR,
            "filter_behavior": self.DEFAULT_FILTER_BEHAVIOR,
            "chat_behavior": self.DEFAULT_CHAT_BEHAVIOR,
            "memory_generation_behavior": self.DEFAULT_MEMORY_BEHAVIOR
        }
        self.load()

    def load(self):
        if os.path.exists(self.PROMPTS_FILE):
            try:
                with open(self.PROMPTS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if k in self.prompts:
                            self.prompts[k] = v
            except Exception as e:
                logger.error(f"Ошибка загрузки промптов: {e}...")

    def save(self):
        try:
            with open(self.PROMPTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.prompts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения промптов: {e}...")

    def get(self, key: str) -> str:
        return self.prompts.get(key, "")

    def set(self, key: str, value: str):
        if key in self.prompts:
            self.prompts[key] = value
            self.save()

    def reset_to_defaults(self):
        self.prompts = {
            "analysis_behavior": self.DEFAULT_ANALYSIS_BEHAVIOR,
            "filter_behavior": self.DEFAULT_FILTER_BEHAVIOR,
            "chat_behavior": self.DEFAULT_CHAT_BEHAVIOR,
            "memory_generation_behavior": self.DEFAULT_MEMORY_BEHAVIOR
        }
        self.save()

# Global instance
prompt_manager = PromptManager()


class PromptBuilder:
    # --- FIXED FORMATS (NOT EDITABLE BY USER) ---

    ANALYSIS_FORMAT_INSTRUCTIONS = """
ВАЖНО: Твой ответ должен быть СТРОГО в формате JSON.
Сначала заполни поле "thinking", где подробно опиши свой ход мыслей, анализ цены и рисков.

ФОРМАТ ОТВЕТА JSON:
{{
    "thinking": "Твой подробный анализ ситуации...",
    "verdict": "GREAT_DEAL" | "GOOD" | "BAD" | "VERY_BAD" | "HARD_TO_SAY",
    "reason": Краткое объяснение на РУССКОМ языке для обычного пользователя. НЕ ИСПОЛЬЗУЙ слова 'квартиль', 'q25', 'медиана'. Пиши: 'отличная цена', 'низ рынка', 'дороговато', 'средняя цена'.",
    "market_position": "great_deal" | "good_zone" | "overpriced" | "unknown",
    "risks": ["риск1", "риск2"] (если рисков нет — пустой список),
    "defects": true (если есть явные дефекты) | false
}}

ЗНАЧЕНИЯ VERDICT:
- GREAT_DEAL: Цена ≤ q25, состояние отличное, высокая ликвидность.
- GOOD: Цена между q25 и median, товар ликвидный, рисков нет.
- BAD: Дорого (выше медианы), неликвид, или есть дефекты.
- VERY_BAD: Скам, цена подозрительно низкая (в разы), продавец-мошенник, или "труп" (хлам).
- HARD_TO_SAY: Слишком мало данных, нет цены, противоречивое описание, или невозможно определить модель.
"""

    FILTER_FORMAT_INSTRUCTIONS = """
ФОРМАТ ОТВЕТА (СТРОГО JSON):
{{
  "verdict": "GOOD" | "BAD",
  "reason": "Краткая причина (1 предложение на русском)"
}}
"""

    @staticmethod
    def _build_market_stats(items: List[Dict]) -> Dict:
        default_stats = {
            "sample_size": 0, "avg": 0, "med": 0, "min": 0, "max": 0, "cnt": 0,
        }
        if not items: return default_stats

        prices = [
            i.get("price", 0) for i in items
            if isinstance(i.get("price"), (int, float)) and i.get("price") > 50
        ]
        if not prices: return default_stats

        return {
            "sample_size": len(prices),
            "avg": int(statistics.mean(prices)),
            "med": int(statistics.median(prices)),
            "min": min(prices),
            "max": max(prices),
            "cnt": len(prices),
        }

    @classmethod
    def build_analysis_prompt(cls, items: List[Dict], current_item: Dict,
                              user_instructions: str = "", interests: str = "",
                              rag_context: Optional[Dict] = None, search_mode: str = 'full') -> str:

        stats = cls._build_market_stats(items)

        if stats['sample_size'] < 3:
            market_ctx = (
                "ВНИМАНИЕ: Мало данных для статистики. "
                "Опирайся на свои внутренние знания цен (актуальность 2025). "
                "В поле 'reason' обязательно укажи: 'Мало данных, оценка примерная'."
            )
        else:
            market_ctx = (
                f"ТВОЯ ВЫДАЧА (похожих: {stats['cnt']}):\n"
                f"- Диапазон: {stats['min']} - {stats['max']} руб.\n"
                f"- Медиана: {stats['med']} руб. | Средняя: {stats['avg']} руб."
            )

        rag_ctx = "В памяти нет данных по этому товару."
        if rag_context:
            rag_ctx = (
                f"ИЗ ПАМЯТИ:\n"
                f"- Ист. Медиана: {rag_context.get('median_price', 0)} руб.\n"
                f"- Знания: {rag_context.get('knowledge', '')}\n"
            )

        item_price = current_item.get('price', 0)
        item_views = current_item.get('views', 0)
        item_cond = str(current_item.get('condition', '')).lower()
        item_date = str(current_item.get('date_text', '')).lower()
        
        views_analysis = "Просмотры в норме."
        display_views = str(item_views)
        
        if search_mode == 'primary':
            display_views = "N/A (Данные недоступны в быстром поиске)"
            views_analysis = "Просмотры: Нет данных. ИГНОРИРУЙ этот фактор, это не значит что их 0."
        else:
            if item_views == 0:
                views_analysis = "0 просмотров: Только что выложено. Шанс забрать первым!"
            elif item_views < 50:
                 views_analysis = "Мало просмотров: объявление свежее или не популярное."
            elif item_views > 750 and item_price < stats['med'] * 0.8:
                views_analysis = f"ТРЕВОГА: {item_views} просмотров при низкой цене."

        price_analysis = []
        if item_price > 0 and stats['med'] > 0:
            diff_table = ((item_price - stats['med']) / stats['med']) * 100

            if diff_table < -30: price_analysis.append("Экстремально низкая цена.")
            elif diff_table < -15: price_analysis.append("Отличная цена (низ рынка).")
            elif diff_table < -5: price_analysis.append("Цена немного ниже рынка.")
            elif diff_table > 30: price_analysis.append("Оверпрайс.")
            elif diff_table > 10: price_analysis.append("Дороже рынка.")
            else: price_analysis.append("Справедливая цена.")

        price_str = " ".join(price_analysis) if price_analysis else "Цена не определена или мало данных."

        cond_bonus = ""
        if any(x in item_cond for x in ['нов', 'new', 'идеал', 'запеч']):
            cond_bonus = "БОНУС: Состояние указано как НОВОЕ/ИДЕАЛ."
        elif any(x in item_cond for x in ['запчаст', 'сломан', 'дефект', 'не рабоч', 'разбит']):
            cond_bonus = "МИНУС: Товар сломан или на запчасти. Понижай оценку (если не ищем лом)."

        date_analysis = ""
        if any(x in item_date for x in ['сегодня', 'час', 'мин', 'сек']):
            date_analysis = "ДАТА: Только что."
        elif any(x in item_date for x in ['вчера']):
            date_analysis = "ДАТА: Свежее."
        elif any(x in item_date for x in ['недел', 'месяц']):
            if '3 недел' in item_date or '4 недел' in item_date or 'месяц' in item_date:
                date_analysis = "ДАТА: Старое (>20 дней). Вероятно, неликвид или продано."
        else:
            pass

        # Сборка частей
        base_behavior = prompt_manager.get("analysis_behavior").format(
            interests_block=interests if interests else "Любая ликвидная электроника."
        )

        mode_instruction = ""
        if search_mode == 'primary':
            mode_instruction = "- Режим поиска 'Первичный': у тебя нет точных данных о просмотрах, поэтому НЕ ОПИРАЙСЯ на этот фактор."

        full_prompt = f"""
{base_behavior}

[ОБЪЕКТ АНАЛИЗА]
Товар: "{current_item.get('title')}"
Цена: {item_price} руб.
Город: {current_item.get('city', 'N/A')}
Состояние: {current_item.get('condition', 'N/A')}
Дата: {item_date} | Просмотры: {display_views}
Описание:
\"\"\"
{current_item.get('description', '')[:2500]}
\"\"\"

[РЫНОЧНЫЙ КОНТЕКСТ]
1. {market_ctx}
2. {rag_ctx}

[ПОДСКАЗКИ АВТОМАТИКИ]
- ЦЕНА: {price_str}
- АКТИВНОСТЬ: {views_analysis}
- КАЧЕСТВО: {cond_bonus}
- АКТУАЛЬНОСТЬ: {date_analysis}

[ПРИОРИТЕТНЫЕ ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ]
{user_instructions}
{mode_instruction}

{cls.ANALYSIS_FORMAT_INSTRUCTIONS}
"""
        return full_prompt

    @classmethod
    def build_neuro_filter_prompt(cls, search_tags: List[str], ignore_tags: List[str], user_criteria: str = "") -> str:
        s_tags = ", ".join(search_tags) if search_tags else "Любые"
        i_tags = ", ".join(ignore_tags) if ignore_tags else "Нет"
        u_crit = user_criteria if user_criteria else "Нет дополнительных критериев."

        base_behavior = prompt_manager.get("filter_behavior").format(
            search_tags=s_tags,
            ignore_tags=i_tags,
            user_criteria=u_crit
        )

        return f"{base_behavior}\n{cls.FILTER_FORMAT_INSTRUCTIONS}"

    @classmethod
    def get_chat_system_prompt(cls) -> str:
        return prompt_manager.get("chat_behavior")


class ChunkCultivationPrompts:
    @staticmethod
    def _format_linked_block(text: str) -> str:
        if not text: return ""
        return f"""[СВЯЗАННЫЕ ЗНАНИЯ (КОНТЕКСТ)]
        {text}
        (Используй это для сравнения. Если текущие данные противоречат контексту — это аномалия)."""

    @staticmethod
    def _get_system_behavior():
        return prompt_manager.get("memory_generation_behavior")

    @staticmethod
    def build_product_cultivation_prompt(
        chunk_key: str,
        items: List[Dict],
        math_block: Dict,
        history_block: str,
        previous_context: str,
        user_interests: str,
        user_instructions: str,
        linked_context: str
    ) -> str:
        """
        Промпт для культивации PRODUCT чанка.
        """
        total_raw_count = len(items) if items else 0

        items_preview = []
        for item in items[:15]:
            items_preview.append({
                'title': item.get('title', '')[:100],
                'price': item.get('price', 0),
                'date': item.get('date', '')[:10]
            })
        
        items_json = json.dumps(items_preview, ensure_ascii=False, indent=2)
        math_json = json.dumps(math_block, ensure_ascii=False, indent=2)
        
        prompt = f"""ТЫ — АНАЛИТИК ТОВАРОВ. КУЛЬТИВАЦИЯ ПРОДУКТА.
    
        ИСХОДНЫЕ ДАННЫЕ:
        Товар: {chunk_key}

        СТАТИСТИКА (Точные факты):
        Всего найдено объявлений: {total_raw_count}
        Ценовая выборка (валидные цены): {math_block.get('count', 0)}
        Статистика цен: {math_json}
        
        ПРИМЕРЫ ОБЪЯВЛЕНИЙ (первые 15):
        {items_json}

        ИСТОРИЯ ЦЕН:
        {history_block if history_block else 'История недоступна'}

        КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
        Интересы: {user_interests if user_interests else 'Не заданы'}
        Инструкции: {user_instructions if user_instructions else 'Нет'}

        {linked_context if linked_context else ''}
        
        ПРЕДЫДУЩЕЕ ОПИСАНИЕ (если было):
        {previous_context[:300] if previous_context else 'Нет'}

        ЗАДАЧА:
        1. Опиши товар, опираясь на заголовок и примеры.
        2. Дай точную сводку цен (min/max/avg из статистики).
        3. Если {total_raw_count} > 5, статус = HAS_OFFERS. Если цена супер-низкая = MAX_BENEFIT.

        ВАЖНО:
        - Все числа в price_analysis ДОЛЖНЫ быть из math_block!
        - Если данных мало (<10 объявлений), установи "confidence" < 0.8 в ответе.
        - "confidence" — это твоя оценка надёжности (0-1)

        ОТВЕТ (ТОЛЬКО в формате JSON, без лишнего текста):
        {{
            "main_description": "Краткое описание товара (1-2 предложения)",
            "hidden_thought_process": "Твои мысли: почему такой статус? Какие факторы повлияли (цена, интересы)?",
            "target_status": "NO_INTEREST | HAS_OFFERS | MAX_BENEFIT",
            "market_phase": "растущий | стабильный | падающий",
            "influence_weights": {{
                "raw_data": <0-100>,
                "system_prompt": <0-100>,
                "user_instructions": <0-100>,
                "user_interests": <0-100>,
                "linked_context": <0-100>
            }},
            "price_analysis": {{
                "min": {math_block.get('min', 0)},
                "max": {math_block.get('max', 0)},
                "avg": {math_block.get('avg', 0)},
                "med": {math_block.get('med', 0)},
                "count": {math_block.get('count', 0)},
                "interpretation": "Описание диапазона цен в прозе"
            }},
            "recommendations": ["Рекомендация 1", "Рекомендация 2", "Рекомендация 3"],
            "confidence": <число>,
            "summary": "Краткий итог"
        }}
        """
        
        return prompt
    
    @staticmethod
    def build_category_cultivation_prompt(
        category_key: str,
        sub_products: List[Dict],
        previous_context: str,
        user_interests: str,
        linked_context: str,
        raw_fallback_preview: str,
        raw_count: int
    ) -> str:
        """
        Промпт для культивации CATEGORY чанка.
        """
        products_info = []
        for p in sub_products:
            p_cont = p.get('content')
            if isinstance(p_cont, str):
                try: p_cont = json.loads(p_cont)
                except: p_cont = {}
                
                if p_cont:
                    products_info.append({
                        "name": p.get('title'),
                        "status": p_cont.get('target_status', 'UNKNOWN'),
                        "price_avg": p_cont.get('price_analysis', {}).get('avg', '?'),
                        "count": p_cont.get('price_analysis', {}).get('count', 0)
                    })

        products_json = json.dumps(products_info, ensure_ascii=False, indent=2)
        
        # Формируем блок сырых данных, если чанков нет
        raw_data_block = ""
        if not products_info:
            raw_data_block = f"""
            ВНИМАНИЕ: Подкатегории (кластеры товаров) еще не сформированы или находятся в очереди обработки.
            ОПИРАЙСЯ НА СЫРЫЕ ДАННЫЕ НИЖЕ ДЛЯ ОБЩЕГО АНАЛИЗА.
            
            ВСЕГО В БАЗЕ (RAW ITEMS): {raw_count} объявлений.
            ПРИМЕРЫ (Сырые данные):
            {raw_fallback_preview}

            ИНСТРУКЦИЯ:
            1. Твой анализ сейчас предварительный.
            2. Не пиши "категория пуста", если {raw_count} > 0.
            3. Если {raw_count} > 10, статус должен быть HAS_OFFERS.
            """
        else:
            raw_data_block = f"""
            ВСЕГО В БАЗЕ (RAW ITEMS): {raw_count} объявлений.
            СФОРМИРОВАННЫЕ КЛАСТЕРЫ (Подтовары):
            {products_json}
            
            Используй кластеры как основной источник истины о сегментах рынка.
            """

        prompt = f"""ТЫ — АНАЛИТИК НОМЕНКЛАТУРЫ. КУЛЬТИВАЦИЯ КАТЕГОРИИ [{category_key}].

        ИСХОДНЫЕ ДАННЫЕ:
        Категория: {category_key}
        
        {raw_data_block}

        КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
        Интересы: {user_interests if user_interests else 'Не заданы'}
        
        {linked_context if linked_context else ''}
        
        ПРЕДЫДУЩЕЕ ОПИСАНИЕ (если было):
        {previous_context[:300] if previous_context else 'Нет'}

        ЗАДАЧА:
        1. ОПРЕДЕЛИ РЫНОЧНУЮ СИТУАЦИЮ:
            - Сколько всего сырых объявлений? ({raw_count})
            - Какие модели/серии доминируют (исходя из примеров или кластеров)?
            - Какой общий ценовой диапазон?

        2. СТРУКТУРА:
            - Если есть кластеры: опиши ситуацию по ним (какие дорогие, какие дешевые).
            - Если кластеров нет: предположи структуру на основе сырых примеров.

        3. СТАТУС (target_status):
            - NO_INTEREST: Только если база пуста или цены x2-x3 от рынка.
            - HAS_OFFERS: Есть товары, есть выбор.
            - MAX_BENEFIT: Есть явные выгодные предложения (низ рынка).

        4. РЕКОМЕНДАЦИИ:
            - Как ориентироваться в категории?
            - Какие подтовары стоит отслеживать?
            - Какие ниши недозаполнены?

        ВАЖНО:
        - "Товарные позиции" в твоем ответе — это виды товаров (модели), а не количество объявлений.
        - Количество объявлений бери из {raw_count}.
        - Если 'User Instructions' пусты, influence_weights.user_instructions ДОЛЖЕН БЫТЬ 0.
        - "confidence" ниже отражает уверенность (0.0-1.0) в ответе.

        ОТВЕТ (ТОЛЬКО в формате JSON, без лишнего текста):
        {{
            "main_description": "Краткое описание категории",
            "hidden_thought_process": "Анализ структуры категории и её точек интереса.",
            "target_status": "NO_INTEREST | HAS_OFFERS | MAX_BENEFIT",
            "market_overview": "Обзор рынка в категории (2-3 предложения)",
            "influence_weights": {{
                "raw_data": <0-100>,
                "system_prompt": <0-100>,
                "user_instructions": <0-100>,
                "user_interests": <0-100>,
                "linked_context": <0-100>
            }},
            "subcategories": [
               {{"name": "Пример подкатегории", "count": "примерно X", "price_range": "X-Y"}}
            ],
            "trends": ["Тренд 1", "Тренд 2"],
            "recommendations": ["Рекомендация 1", "Рекомендация 2"],
            "confidence": <0.0-1.0>,
            "summary": "Однострочный итог для карточки"
        }}
        """

        return prompt
    
    @staticmethod
    def build_database_cultivation_prompt(
        db_stats: Dict,
        vocabulary: List[str],
        linked_context: str,
        topic: str
    ) -> str:
        """
        Промпт для культивации DATABASE чанка.
        """
        vocab_text = ", ".join(vocabulary[:40]) if vocabulary else "Нет данных"
        
        # Явное указание на область видимости
        scope_note = f"Это виртуальная база данных по теме '{topic}'." 
        if db_stats.get('total_items', 0) == 0:
            scope_note += " ВНИМАНИЕ: База выглядит пустой. Проверь фильтры."

        prompt = f"""ТЫ — АНАЛИТИК ДАННЫХ. КУЛЬТИВАЦИЯ БД [{topic}].

        {scope_note}

        СТАТИСТИКА:
        Всего объявлений: {db_stats.get('total_items', 0)}
        Средняя цена: {db_stats.get('avg_price', 0)}₽
        Брендов/Групп: {db_stats.get('total_brands', 0)}

        ТОП СЛОВА (КОНТЕКСТ):
        {vocab_text}

        {linked_context if linked_context else ''}

        ЗАДАЧА:
        1. ОЦЕНИ СОСТОЯНИЕ БД:
            - Объём данных достаточный?
            - Какие категории доминируют?
            - Какие категории недозаполнены?

        2. АНАЛИЗИРУЙ СЛОВАРЬ:
            - Какие ключевые темы?
            - Есть ли дубликаты/синонимы?
            - Какие слова встречаются часто?

        3. ВЫЯВИ ПРОБЛЕМЫ:
            - Есть ли дыры в данных?
            - Есть ли странные/неправильные данные?
            - Нужны ли уточнения?

        4. РЕКОМЕНДАЦИИ:
            - Что нужно добавить в БД?
            - На какие категории ориентироваться?
            - Как улучшить качество?

        ВАЖНО:
        - data_quality_score (0.0 - 1.0): Твоя оценка качества базы.
            * 1.0: Данных много, категории разнообразны, словарь чистый, цены реалистичные.
            * 0.5: Данные есть, но их мало, либо много мусора/дубликатов.
            * 0.1: База почти пуста или содержит только мусор.

        ОТВЕТ (ТОЛЬКО в формате JSON, без лишнего текста):
        {{
            "main_description": "Состояние и характер БД",
            "data_volume_assessment": "Оценка объёма данных",
            "target_status": "NO_INTEREST | HAS_OFFERS | MAX_BENEFIT",
            "hidden_thought_process": "Оценка полноты данных и необходимости расширения.",
            "influence_weights": {{
                "raw_data": <0-100>,
                "system_prompt": <0-100>,
                "user_instructions": <0-100>,
                "user_interests": <0-100>,
                "linked_context": <0-100>
            }},
            "key_topics": ["Тема 1", "Тема 2", "Тема 3"],
            "quality_issues": ["Проблема 1", "Проблема 2"],
            "recommendations": ["Рекомендация 1", "Рекомендация 2"],
            "data_quality_score": <0.0-1.0>,
            "summary": "Однострочный summary"
        }}
        """

        return prompt
        
    @staticmethod
    def build_ai_behavior_cultivation_prompt(
        actions_log: List[Dict],
        user_interests: str,
        previous_context: str,
        linked_context: str
    ) -> str:
        """
        Промпт для культивации AI_BEHAVIOR чанка.
        """
        # Подготавливаем лог действий
        actions_text = ""
        if actions_log:
            for action in actions_log[:30]:  # Первые 30 действий
                actions_text += f"• {action.get('action', 'unknown')} - "
                actions_text += f"результат: {action.get('result', 'unknown')[:50]}\n"
        else:
            actions_text = "Логов действий нет"

        prompt = f"""ТЫ — САМОКОРРЕКТИРУЮЩИЙСЯ ИИ. АНАЛИЗ СОБСТВЕННОГО ПОВЕДЕНИЯ.
        
        ЛОГ ДЕЙСТВИЙ:
        {actions_text}
        
        КОНТЕКСТ:
        Интересы пользователя: {user_interests if user_interests else 'Не заданы'}
        
        {linked_context if linked_context else ''}
        
        ПРЕДЫДУЩИЕ ВЫВОДЫ (если были):
        {previous_context[:300] if previous_context else 'Нет'}
        
        ЗАДАЧА:
        1. АНАЛИЗИРУЙ СОБСТВЕННОЕ ПОВЕДЕНИЕ:
            - Какие ошибки я допускал?
            - Какие решения оказались верными?
            - Какие шаблоны повторяются?
        
        2. ВЫЯВИ ПРАВИЛА SELF-CORRECTION:
            - Когда я ошибаюсь?
            - Как я могу исправиться?
            - Какие проверки нужны?
        
        3. ОЦЕНИ ЭФФЕКТИВНОСТЬ:
            - Насколько точны мои анализы?
            - Где я теряю точность?
            - Какие данные помогают, какие путают?
        
        4. ДАЙ ПОДСКАЗКИ ДЛЯ УЛУЧШЕНИЯ:
            - Что я должен делать лучше?
            - Какие вопросы задавать?
            - Какие проверки добавить?
        
        ВАЖНО:
        - effectiveness_score (0.0 - 1.0): Твоя эффективность.
            * 1.0: Все действия успешны, ошибок нет, логи чистые.
            * 0.5: Есть ошибки, но работа идет. Были повторные попытки (retries).
            * 0.1: Сплошные ошибки, таймауты или пустые результаты.
        - Будь честен в оценке своих ошибок.
        - Предлагай конкретные, применимые правила.   
        
        ОТВЕТ (ТОЛЬКО в формате JSON, без лишнего текста):
        {{
            "main_description": "Общая оценка собственного поведения",
            "hidden_thought_process": "Поведенческий шаблон, рефлексия ошибок и успехов.",
            "influence_weights": {{
                "raw_data": <0-100>,
                "system_prompt": <0-100>,
                "user_instructions": <0-100>,
                "user_interests": <0-100>,
                "linked_context": <0-100>
            }},
            "learned_rules": [
            "Правило 1 (например: 'Проверяй цены на выбросы при анализе')",
            "Правило 2",
            "Правило 3"],
            "error_patterns": ["Ошибка 1 (когда и почему)", "Ошибка 2"],
            "correction_prompts": [
            "Подсказка 1 для будущих анализов",
            "Подсказка 2",
            "Подсказка 3"],
            "effectiveness_score": <число>,
            "improvement_areas": ["Область улучшения 1", "Область улучшения 2"],
            "summary": "Краткий итог self-correction анализа"
        }}
        """
            
        return prompt