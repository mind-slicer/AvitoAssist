import sys
sys.path.insert(0, '/wip2')

from app.core.memory import MemoryManager

# Создаём экземпляр (инициализирует БД)
mm = MemoryManager()

# Тест добавления элемента
test_item = {
    'ad_id': 'test_123',
    'title': 'iPhone 15 Pro 128GB',
    'price': 75000,
    'description': 'Тестовый iPhone',
    'city': 'Москва',
    'condition': 'Как новый'
}
result = mm.add_raw_item(test_item, categories=['Смартфоны'], product_keys=['iphone_15_pro'])
print(f'Добавлен элемент с ID: {result}')

# Тест получения элементов
items = mm.get_raw_items(search_query='iPhone', limit=10)
print(f'Найдено элементов: {len(items)}')

# Тест статистики
stats = mm.get_raw_data_statistics()
print(f'Статистика: {stats}')

# Тест поиска
results = mm.search_all('iPhone')
print(f'Поиск: {len(results["raw_items"])} items, {len(results["knowledge"])} chunks')

print('\\n✓ Базовое тестирование пройдено!')