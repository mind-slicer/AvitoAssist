import json
import os

# ==========================================
# 1. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def make_tag(value):
    return {"type": "tag", "value": value}

def make_folder(name, children=None):
    return {"type": "folder", "name": name, "children": children or []}

def make_root(children=None):
    return {"type": "folder", "name": "ROOT", "children": children or []}

def convert_dict_to_structure(data_dict):
    """Превращает словарь { 'Имя папки': ['тег1', 'тег2'] } в список объектов папок"""
    folders = []
    for folder_name, items in data_dict.items():
        tags = [make_tag(item) for item in items]
        folders.append(make_folder(folder_name.upper(), tags))
    return folders

# ==========================================
# 2. ДАННЫЕ: ПРОЦЕССОРЫ (CPU)
# ==========================================
intel_cpus = {
    "2 поколение (Sandy Bridge)": [
        "Core i7 2600K", "Core i7 2600", "Core i7 2700K",
        "Core i5 2500K", "Core i5 2500", "Core i5 2400", "Core i3 2120"
    ],
    "3 поколение (Ivy Bridge)": [
        "Core i7 3770K", "Core i7 3770", 
        "Core i5 3570K", "Core i5 3570", "Core i5 3470", "Core i3 3220"
    ],
    "4 поколение (Haswell)": [
        "Core i7 4790K", "Core i7 4770K", 
        "Core i5 4690K", "Core i5 4670K", "Core i5 4590", "Core i5 4460", "Core i3 4170"
    ],
    "6 поколение (Skylake)": [
        "Core i7 6700K", "Core i7 6700", "Core i5 6600K", "Core i5 6500", "Core i5 6400", "Core i3 6100"
    ],
    "7 поколение (Kaby Lake)": [
        "Core i7 7700K", "Core i7 7700", "Core i5 7600K", "Core i5 7500", "Core i5 7400", "Core i3 7100"
    ],
    "8 поколение (Coffee Lake)": [
        "Core i7 8700K", "Core i7 8700", "Core i5 8600K", "Core i5 8400", "Core i3 8100"
    ],
    "9 поколение (Coffee Lake R)": [
        "Core i9 9900K", "Core i7 9700K", "Core i7 9700", "Core i5 9600K", "Core i5 9400F", "Core i3 9100F"
    ],
    "10 поколение (Comet Lake)": [
        "Core i9 10900K", "Core i7 10700K", "Core i7 10700F", "Core i5 10600K", "Core i5 10400F", "Core i3 10100F"
    ],
    "11 поколение (Rocket Lake)": [
        "Core i9 11900K", "Core i7 11700K", "Core i5 11600K", "Core i5 11400F"
    ],
    "12 поколение (Alder Lake)": [
        "Core i9 12900K", "Core i7 12700K", "Core i7 12700KF", "Core i5 12600K", "Core i5 12400F", "Core i3 12100F"
    ],
    "13 поколение (Raptor Lake)": [
        "Core i9 13900K", "Core i7 13700K", "Core i5 13600K", "Core i5 13400F"
    ],
    "14 поколение (Raptor Lake R)": [
        "Core i9 14900K", "Core i7 14700K", "Core i5 14600K", "Core i5 14400F"
    ],
    "15 поколение (Core Ultra 200S)": [
        "Core Ultra 9 285K", "Core Ultra 7 265K", "Core Ultra 5 245K"
    ]
}

amd_cpus = {
    "1 поколение (Zen 1000)": [
        "Ryzen 7 1800X", "Ryzen 7 1700", "Ryzen 5 1600", "Ryzen 5 1400", "Ryzen 3 1200"
    ],
    "2 поколение (Zen+ 2000)": [
        "Ryzen 7 2700X", "Ryzen 7 2700", "Ryzen 5 2600", "Ryzen 5 2400G", "Ryzen 3 2200G"
    ],
    "3 поколение (Zen2 3000)": [
        "Ryzen 9 3950X", "Ryzen 9 3900X", "Ryzen 7 3700X", "Ryzen 5 3600", "Ryzen 3 3300X"
    ],
    "4 поколение (Zen2 Renoir 4000)": [
        "Ryzen 7 4700G", "Ryzen 5 4650G", "Ryzen 5 4500", "Ryzen 3 4100"
    ],
    "5 поколение (Zen3 5000)": [
        "Ryzen 9 5950X", "Ryzen 9 5900X", "Ryzen 7 5800X3D", "Ryzen 7 5700X", "Ryzen 5 5600X", "Ryzen 5 5600"
    ],
    "7 поколение (Zen4 7000)": [
        "Ryzen 9 7950X", "Ryzen 7 7800X3D", "Ryzen 7 7700X", "Ryzen 5 7600X", "Ryzen 5 7500F"
    ],
    "8 поколение (Zen4 APU 8000)": [
        "Ryzen 7 8700G", "Ryzen 5 8600G", "Ryzen 5 8400F"
    ],
    "9 поколение (Zen5 9000)": [
        "Ryzen 9 9950X", "Ryzen 9 9900X", "Ryzen 7 9700X", "Ryzen 5 9600X"
    ]
}

# ==========================================
# 3. ДАННЫЕ: ВИДЕОКАРТЫ (GPU)
# ==========================================
nvidia_gpus = {
    "RTX 50 Series (Blackwell)": [
        "RTX 5090", "RTX 5080", "RTX 5070 Ti", "RTX 5070", "RTX 5060 Ti", "RTX 5060", "RTX 5050"
    ],
    "RTX 40 Series (Lovelace)": [
        "RTX 4090", "RTX 4080 Super", "RTX 4080", 
        "RTX 4070 Ti Super", "RTX 4070 Ti", "RTX 4070 Super", "RTX 4070",
        "RTX 4060 Ti", "RTX 4060"
    ],
    "RTX 30 Series (Ampere)": [
        "RTX 3090 Ti", "RTX 3090", "RTX 3080 Ti", "RTX 3080", 
        "RTX 3070 Ti", "RTX 3070", "RTX 3060 Ti", "RTX 3060", "RTX 3050"
    ],
    "RTX 20 Series (Turing)": [
        "RTX 2080 Ti", "RTX 2080 Super", "RTX 2080",
        "RTX 2070 Super", "RTX 2070", 
        "RTX 2060 Super", "RTX 2060"
    ],
    "GTX 16 Series (Turing)": [
        "GTX 1660 Ti", "GTX 1660 Super", "GTX 1660", 
        "GTX 1650 Super", "GTX 1650", "GTX 1630"
    ],
    "GTX 10 Series (Pascal)": [
        "GTX 1080 Ti", "GTX 1080", "GTX 1070 Ti", "GTX 1070",
        "GTX 1060 6GB", "GTX 1060 3GB", "GTX 1050 Ti", "GTX 1050"
    ]
}

amd_gpus = {
    "RX 9000 Series (RDNA 4)": [
        "RX 9070 XT", "RX 9070", "RX 9070 GRE", "RX 9060 XT", "RX 9060"
    ],
    "RX 7000 Series (RDNA 3)": [
        "RX 7900 XTX", "RX 7900 XT", "RX 7900 GRE",
        "RX 7800 XT", "RX 7700 XT", "RX 7600 XT", "RX 7600"
    ],
    "RX 6000 Series (RDNA 2)": [
        "RX 6950 XT", "RX 6900 XT", "RX 6800 XT", "RX 6800",
        "RX 6750 XT", "RX 6700 XT", "RX 6650 XT", "RX 6600 XT", "RX 6600",
        "RX 6500 XT", "RX 6400"
    ],
    "RX 5000 Series (RDNA 1)": [
        "RX 5700 XT", "RX 5700", "RX 5600 XT", "RX 5500 XT"
    ],
    "RX 500 Series (Polaris)": [
        "RX 590", "RX 580", "RX 570", "RX 560", "RX 550"
    ],
    "RX 400 Series (Polaris)": [
        "RX 480", "RX 470", "RX 460"
    ]
}

# ==========================================
# 4. ДАННЫЕ: МАТЕРИНСКИЕ ПЛАТЫ
# ==========================================
motherboards_data = {
    "INTEL": [
        "LGA 1851", "LGA 1700", "LGA 1200", 
        "LGA 1151 v2", "LGA 1151 v1", "LGA 1150", "LGA 1155"
    ],
    "AMD": [
        "AM5", "AM4"
    ]
}

# ==========================================
# 5. ДАННЫЕ: ДИСКИ
# ==========================================
disks_data = {
    "SSD": [
        "SSD 1 Тб", "SSD 500 Гб", "SSD 480 Гб", 
        "SSD 256 Гб", "SSD 240 Гб", 
        "SSD 128 Гб", "SSD 120 Гб", "SSD 60 Гб"
    ],
    "HDD": [
        "HDD 2 Тб", "HDD 1 Тб", "HDD 512 Гб"
    ]
}

# ==========================================
# 6. ДАННЫЕ: ОПЕРАТИВНАЯ ПАМЯТЬ
# ==========================================
ram_data = {
    "DDR": [
        "DDR 5", 
        "DDR 4", "DDR 4 4000", "DDR 4 3600", "DDR 4 3200", "DDR 4 3000", 
        "DDR 4 2666", "DDR 4 2400", "DDR 4 2133"
    ]
}

# ==========================================
# 7. ДАННЫЕ: ИГНОР (ОБЩИЙ)
# ==========================================
ignore_data = {
    "Состояние / Ремонт": [
        "Сломан", "Не работает", "На запчасти", "Разбит", 
        "Ремонт", "Дефект", "Отвал", "Гретый", "Восстановленный", "Артефакты"
    ],
    "Коммерция": [
        "Куплю", "Скупка", "Магазин", "Оптом", "Кредит", "Рассрочка", "Trade-in"
    ],
    "Серверное (если ищем десктоп)": [
        "Xeon", "E5-26", "E5-16", "v2", "v3", "v4", "Server", "X99", "X79", "Huanan"
    ],
    "Майнинг (для GPU)": [
        "Майнинг", "После майнинга", "Ферма", "Риг", "P106", "P104", "CMP"
    ]
}

# ==========================================
# 8. ГЕНЕРАЦИЯ
# ==========================================
def generate_files():
    search_structure = {
        "Процессоры": make_root([
            make_folder("INTEL", convert_dict_to_structure(intel_cpus)),
            make_folder("AMD", convert_dict_to_structure(amd_cpus))
        ]),
        "Видеокарты": make_root([
            make_folder("NVIDIA", convert_dict_to_structure(nvidia_gpus)),
            make_folder("AMD", convert_dict_to_structure(amd_gpus))
        ]),
        "Материнские платы": make_root(convert_dict_to_structure(motherboards_data)),
        "Диски": make_root(convert_dict_to_structure(disks_data)),
        "Оперативная память": make_root(convert_dict_to_structure(ram_data))
    }
    
    ignore_root_children = convert_dict_to_structure(ignore_data)
    ignore_structure = {
        "Базовый фильтр": make_root(ignore_root_children)
    }

    print("Генерация tag_presets.json (CPU + GPU + MB + Disks + RAM)...")
    with open("tag_presets.json", "w", encoding="utf-8") as f:
        json.dump(search_structure, f, ensure_ascii=False, indent=2)

    print("Генерация tag_presets_ignore.json...")
    with open("tag_presets_ignore.json", "w", encoding="utf-8") as f:
        json.dump(ignore_structure, f, ensure_ascii=False, indent=2)
        
    print(f"Готово! Обработано CPU, GPU, MB, Диски и Оперативная память.")

if __name__ == "__main__":
    generate_files()