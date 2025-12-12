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
        # 1. Сбор данных статистики
        stats = cls._build_market_stats(items, current_item.get('title'))
        
        # 2. Формирование блока RAG [ВСПОМОГАТЕЛЬНЫЕ ДАННЫЕ]
        aux_data = []
        if stats['sample_size'] > 0:
            aux_data.append(f"- Текущая выдача ({stats['cnt']} шт): Медиана {stats['med']}₽, Мин {stats['min']}₽")
        
        if rag_context:
            # Данные из "Концептуальной памяти" и кэша
            hist_med = rag_context.get('median_price', 'Нет данных')
            hist_trend = rag_context.get('trend', 'N/A')
            aux_data.append(f"- Историческая база (RAG): Медиана {hist_med}₽, Тренд: {hist_trend}")
            
            # Если есть "мысли" ИИ (summary/risks)
            if rag_context.get('knowledge'):
                aux_data.append(f"- ЗАМЕТКИ ИЗ ПАМЯТИ: {rag_context['knowledge']}")
        
        aux_block = "\n".join(aux_data) if aux_data else "Нет статистических данных."

        # 3. Формирование блока [ЖЁСТКИЕ ПРАВИЛА]
        strat = "Максимальная маржа. Ищи ошибки в цене."
        if priority == AnalysisPriority.QUALITY: strat = "Идеальное состояние, гарантия, комплект."
        elif priority == AnalysisPriority.DEFICIT: strat = "Редкое/Топовое железо."
        
        user_rules = f"{strat}\n{user_instructions}" if user_instructions else strat

        # 4. Расширенные поля товара
        item_details = (
            f"Товар: {current_item.get('title')}\n"
            f"Цена: {current_item.get('price')} ₽\n"
            f"Город: {current_item.get('city', 'N/A')}\n"
            f"Дата: {current_item.get('date_text', 'N/A')} | Просмотры: {current_item.get('views', 0)}\n"
            f"Продавец ID: {current_item.get('seller_id', 'N/A')}\n"
            f"Описание:\n{current_item.get('description', '')[:800]}" 
        )

        # Итоговая сборка
        return f"""
{cls.SYSTEM_BASE}

=============================================================
РАЗДЕЛ 1: ЖЁСТКИЕ ПРАВИЛА (ПРИОРИТЕТ 100%)
=============================================================
Следуй этим инструкциям неукоснительно. Они важнее любой статистики.
1. Твоя стратегия: {user_rules}
2. Не выдумывай цены. Если их нет в статистике — пиши "нет данных".
3. Игнорируй маркетинговый шум в описании.

=============================================================
РАЗДЕЛ 2: ВСПОМОГАТЕЛЬНЫЕ ДАННЫЕ (ПРИОРИТЕТ 30%)
=============================================================
Используй это для контекста, но если цена товара противоречит им — верь факту цены товара.
{aux_block}

=============================================================
ОБЪЕКТ АНАЛИЗА
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