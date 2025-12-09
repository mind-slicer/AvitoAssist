class AvitoSelectors:
    # --- Поиск и навигация ---
    #SEARCH_INPUTS = [
    #    'input[data-marker*="search"]',
    #    'input[placeholder*="Поиск"]',
    #    'input[name="q"]',
    #]
    SEARCH_INPUTS = [
        'input[data-marker*="search"]',
        'input[placeholder*="Поиск"]',
        'input[name="q"]',
        'input[data-marker="search-form/suggest"]',
        'input[data-marker="top-rubricator/search/input"]',
        'input[class*="input-input"]',
        'input[placeholder="Поиск по объявлениям"]',
        'input[type="text"]'
    ]
    SEARCH_BUTTON = 'button[data-marker="search-form/submit-button"]'
    DROPDOWN = 'div[data-marker*="suggest"], [role="listbox"]'
    DROPDOWN_ITEMS = '[data-marker*="suggest/list/item"], [role="option"]'
    
    # --- Список выдачи (Grid) ---
    ITEM_CONTAINER = '[data-marker="item"]'
    PAGINATION_NEXT = '[data-marker="pagination-button/nextPage"]'
    
    # --- Карточка товара (Превью в списке) ---
    PREVIEW_TITLE = '[data-marker="item-title"]'
    PREVIEW_PRICE = '[data-marker="item-price"]'
    PREVIEW_DATE = '[data-marker="item-date"]'
    PREVIEW_GEO = "div[class*='geo-root']"
    
    # Описание может быть в разных блоках в зависимости от версии верстки
    PREVIEW_DESC_VARIANTS = [
        "div[class*='iva-item-bottomBlock'] p[class*='styles-module-root']",
        "div[class*='bottomBlock'] p[class*='styles-module']",
        "p[itemprop='description']"
    ]
    
    PREVIEW_SELLER_LINK = "a[data-marker='seller-link/link'], a[href*='/profile/']"

    # --- Детальная страница (Deep Dive) ---
    DETAIL_DESC = "[data-marker='item-view/item-description']"
    DETAIL_ADDR_CONTAINER = "[itemprop='address']"
    DETAIL_ADDR_ALT = "[data-marker='delivery-item-address-text'], [class*='item-address-georeferences']"
    DETAIL_PARAMS = "[data-marker='item-view/item-params']"
    DETAIL_DATE = "[data-marker='item-view/item-date']"
    DETAIL_SELLER_INFO = "a[data-marker='seller-info/label'], a[href*='/profile/']"
    
    # --- Технические ---
    DISABLED_CLASS = "styles-module-root_disabled"