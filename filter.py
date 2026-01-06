import json

def filter_misc_items(input_file, output_file):
    """
    Фильтрует JSON файл, оставляя только элементы с category='MISC'
    
    Args:
        input_file: путь к исходному JSON файлу
        output_file: путь для сохранения отфильтрованного JSON
    """
    # Загрузка JSON
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Фильтрация items - оставляем только MISC
    original_count = len(data['items'])
    data['items'] = [
        item for item in data['items']
        if item.get('semantic_analysis', {}).get('category') == 'MISC'
    ]
    
    # Обновление счетчика
    data['total_items'] = len(data['items'])
    
    # Сохранение результата
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Исходных элементов: {original_count}")
    print(f"Отфильтровано (MISC): {data['total_items']}")
    print(f"Удалено: {original_count - data['total_items']}")

# Использование
if __name__ == "__main__":
    input_file = "diagnostic_20260106_130732.json"  # ваш входной файл
    output_file = "diagnostic_misc_only.json"  # результат
    
    filter_misc_items(input_file, output_file)