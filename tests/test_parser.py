import pytest
from bs4 import BeautifulSoup
from app.core.parser import ItemParser

# Простейший мок HTML карточки товара
HTML_ITEM = """
<div data-marker="item">
    <div class="geo-root">Москва, м. Арбатская</div>
    <a href="/moskva/tovary/noutbuk_apple_macbook_pro_14_m1_max_32gb_1tb_3682914567" 
       data-marker="item-title">
       Ноутбук Apple MacBook Pro 14 M1 Max 32Gb 1Tb
    </a>
    <span data-marker="item-price">185 000&nbsp;₽</span>
    <div class="iva-item-bottomBlock">
        <p class="styles-module-root">Идеальное состояние, полный комплект.</p>
    </div>
    <div data-marker="item-date">Сегодня, 14:30</div>
</div>
"""

def test_extract_ad_id():
    url = "https://avito.ru/item_name_123456789"
    assert ItemParser.extract_ad_id(url) == "123456789"
    
    url_with_params = "https://avito.ru/item_name_987654321?query=test"
    assert ItemParser.extract_ad_id(url_with_params) == "987654321"

def test_parse_item_valid():
    soup = BeautifulSoup(HTML_ITEM, 'lxml')
    # Находим корневой элемент, как это делает реальный парсер
    item_element = soup.find('div', {'data-marker': 'item'})
    
    result = ItemParser.parse_search_item(item_element)
    
    assert result is not None
    assert result['title'] == "Ноутбук Apple MacBook Pro 14 M1 Max 32Gb 1Tb"
    assert result['price'] == 185000
    assert result['city'] == "Москва"
    assert result['id'] == "3682914567"
    assert "Идеальное состояние" in result['description']
    assert "https://www.avito.ru/moskva" in result['link']

def test_parse_item_no_price():
    # Тест на товар без цены (например, "Договорная")
    html = HTML_ITEM.replace('<span data-marker="item-price">185 000&nbsp;₽</span>', '')
    soup = BeautifulSoup(html, 'lxml')
    item_element = soup.find('div', {'data-marker': 'item'})
    
    result = ItemParser.parse_search_item(item_element)
    assert result['price'] == 0