import os
import json
import statistics
from datetime import datetime
from typing import List, Dict, Optional
from app.config import BASE_APP_DIR
from app.core.log_manager import logger

class PromptManager:
    PROMPTS_FILE = os.path.join(BASE_APP_DIR, "prompts_config.json")

    # --- 1. ANALYSIS PROMPT (ANALYSIS) ---
    DEFAULT_ANALYSIS_BEHAVIOR = """Ты — профессиональный скупщик компьютерной техники на Авито.
Твоя цель — найти выгодные предложения для перепродажи (маржа 20–50%).

[ТВОИ ИНТЕРЕСЫ И НИША]
{interests_block}

ТВОЯ СТРАТЕГИЯ:
1. Ищи цены в нижнем квартиле рынка (q25) или ниже. Медиана — это потолок продажи, а не покупки.
2. Оценивай ликвидность, поскольку товар должен уйти быстро.
3. Фильтруй риски: майнинг, нет коробки, продавец-однодневка, мутные описания.
4. Игнорируй маркетинговый шум ("тянет все игры", "летает"). Смотри на факты.

КАК ПРИНИМАТЬ РЕШЕНИЯ:
- Если цена экстремально низкая -> Ищи подвох (дефекты, скам). Если чисто — это GREAT_DEAL.
- Если данных мало или описание противоречивое -> Не выдумывай. Ставь статус HARD_TO_SAY.
- Если цена выше рынка или товар неликвид -> BAD.
- Если явный обман, мошенничество или цена в 2-3 раза ниже рынка без причины -> VERY_BAD.
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

    def __init__(self):
        self.prompts = {
            "analysis_behavior": self.DEFAULT_ANALYSIS_BEHAVIOR,
            "filter_behavior": self.DEFAULT_FILTER_BEHAVIOR,
            "chat_behavior": self.DEFAULT_CHAT_BEHAVIOR
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
            "chat_behavior": self.DEFAULT_CHAT_BEHAVIOR
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
    COMMON_FORMAT = """
    ВАЖНО: Твой ответ должен быть СТРОГО валидным JSON. Без Markdown блоков.
    
    СТРУКТУРА JSON:
    {
        "display_status": "Краткий статус (2-4 слова, например: 'Рынок перегрет' или 'Отличная точка входа'). Используй CapsLock для важных статусов",
        "main_description": "Суть анализа. Факты, цены, ликвидность. Для человека.",
        "hidden_thought_process": "Твои скрытые мысли. Анализ аномалий, почему сформировался именно такой статус, связь с другими чанками.",
        "formation_reason": "Почему этот кластер вообще существует?",
        "data_sufficiency": "LOW" | "MEDIUM" | "HIGH",
        "influence_weights": {
            "system_prompt": 10,    // % влияния твоей базовой роли
            "user_instructions": 0, // % влияния инструкций пользователя (если были)
            "user_interests": 0,    // % влияния интересов пользователя
            "linked_chunks": 0,     // % влияния прошлых знаний
            "raw_data": 0          // % влияния самих данных
        },
        "price_analysis": {
            "avg": 0, "med": 0, "q25": 0,
            "trend": "up" | "down" | "stable"
        }
    }
    """

    @staticmethod
    def _format_linked_block(text: str) -> str:
        if not text: return ""
        return f"""[СВЯЗАННЫЕ ЗНАНИЯ (КОНТЕКСТ)]
        {text}
        (Используй это для сравнения. Если текущие данные противоречат контексту — это аномалия)."""

    @staticmethod
    def build_product_cultivation_prompt(product_key: str, items: list, 
                                         previous_context: str = "", 
                                         user_interests: str = "",
                                         user_instructions: str = "",
                                         linked_context: str = "") -> str:
        current_date = datetime.now().strftime("%d.%m.%Y")
        
        prices = [i.get('price', 0) for i in items if i.get('price', 0) > 100]
        stats_hint = ""
        if prices:
            med = int(statistics.median(prices))
            q25 = int(sorted(prices)[int(len(prices)*0.25)])
            stats_hint = f"РАСЧЕТНАЯ СТАТИСТИКА: Median={med}, Q25={q25} (Твоя цель <= {q25})"

        items_text = ""
        for item in items[:40]:
            items_text += f"- {item.get('title')} | {item.get('price')} руб. | {item.get('date_text')}\n"

        return f"""
        СЕГОДНЯ: {current_date}. РОЛЬ: Профессиональный скупщик техники. Цель — маржа 20-50%.
        ОБЪЕКТ: "{product_key}"
        {stats_hint}

        [ВХОДНЫЕ ДАННЫЕ]
        1. ИНТЕРЕСЫ: "{user_interests}"
        2. ИНСТРУКЦИИ: "{user_instructions}"
        3. ЛОТЫ (raw_data):
        {items_text}

        {ChunkCultivationPrompts._format_linked_block(linked_context)}
        {f'[ИСТОРИЯ] {previous_context}' if previous_context else ''}

        ЗАДАЧА: Оцени ликвидность и цену (Q25).
        ВЕСА: raw_data (база), linked_chunks (влияние категории), system_prompt (экспертиза).
        {ChunkCultivationPrompts.COMMON_FORMAT}
        """
    
    @staticmethod
    def build_category_cultivation_prompt(category_key: str, sub_products: List[Dict], 
                                          previous_context: str = "",
                                          user_interests: str = "",
                                          linked_context: str = "") -> str: # <-- NEW ARG
        current_date = datetime.now().strftime("%d.%m.%Y")

        products_text = ""
        for p in sub_products:
            content = p.get('content') or {}
            if isinstance(content, str):
                try: content = json.loads(content)
                except: content = {}
            status = content.get('display_status', 'N/A')
            desc = content.get('main_description', '')[:60]
            products_text += f"- {p.get('chunk_key')}: {status} ({desc}...)\n"

        return f"""
        СЕГОДНЯ: {current_date}. РОЛЬ: Аналитик категорий.
        КАТЕГОРИЯ: "{category_key}"

        [ИНТЕРЕСЫ] "{user_interests}"
        [СОСТАВ (raw_data)]
        {products_text}

        {ChunkCultivationPrompts._format_linked_block(linked_context)}
        {f'[ИСТОРИЯ] {previous_context}' if previous_context else ''}

        ЗАДАЧА: Дай обзор категории.
        ВЕСА: raw_data (продукты внутри), linked_chunks (глобальный контекст рынка из Базы).
        {ChunkCultivationPrompts.COMMON_FORMAT}
        """
    
    @staticmethod
    def build_database_cultivation_prompt(db_stats: dict, vocabulary: list, 
                                          linked_context: str = "") -> str:
        vocab_str = ", ".join(vocabulary[:60])

        return f"""
        ГЛОБАЛЬНЫЙ АНАЛИЗ БАЗЫ.
        Записей: {db_stats.get('total_items')}.
        Топ слов (raw_data): {vocab_str}

        {ChunkCultivationPrompts._format_linked_block(linked_context)}
        
        ЗАДАЧА: Опиши наполнение базы. 
        СВЯЗЬ: В linked_chunks передан портрет пользователя. Ответь: база соответствует интересам этого пользователя?
        {ChunkCultivationPrompts.COMMON_FORMAT}
        """
        
    @staticmethod
    def build_ai_behavior_cultivation_prompt(actions_log: list, user_interests: str = "", 
                                             previous_context: str = "",
                                             linked_context: str = "") -> str: # <-- NEW ARG
        log_text = "\n".join([f"- {a.get('action_type')}: {a.get('details')}" for a in actions_log[-40:]])
        
        return f"""
        РОЛЬ: Аналитик поведения пользователя.
        ИНТЕРЕСЫ: "{user_interests}"
        ДЕЙСТВИЯ (raw_data):
        {log_text}
        
        {ChunkCultivationPrompts._format_linked_block(linked_context)}
        {f'[ИСТОРИЯ] {previous_context}' if previous_context else ''}

        ЗАДАЧА: Сравни слова и действия.
        СВЯЗЬ: В linked_chunks передан обзор Базы Данных. Понимает ли пользователь рынок?
        {ChunkCultivationPrompts.COMMON_FORMAT}
        """