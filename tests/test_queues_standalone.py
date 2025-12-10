import sys
import os
import json
import shutil
import unittest
from pathlib import Path

# Добавляем корень проекта в путь, чтобы видеть модули app
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))

from app.ui.windows.queue_state_manager import QueueStateManager
from app.config import BASE_APP_DIR

class TestQueueStateManager(unittest.TestCase):
    def setUp(self):
        """Подготовка: создаем временную директорию для конфигов"""
        self.test_dir = project_root / "tests" / "temp_config"
        os.makedirs(self.test_dir, exist_ok=True)
        
        # Переопределяем путь сохранения в классе (магия monkey-patching)
        # Мы подменяем метод _queues_file_path у экземпляра класса
        self.original_path_method = QueueStateManager._queues_file_path
        
        def mock_path(instance):
            return os.path.join(self.test_dir, "queues_state_test.json")
            
        QueueStateManager._queues_file_path = mock_path
        
        self.manager = QueueStateManager()
        # Очищаем все перед тестом
        self.manager.queues_data = {}
        self.manager._ensure_queue_exists(0)

    def tearDown(self):
        """Уборка: удаляем временные файлы и возвращаем метод"""
        QueueStateManager._queues_file_path = self.original_path_method
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_initial_state(self):
        """Тест 1: Проверка начального состояния"""
        self.assertEqual(len(self.manager.queues_data), 1)
        self.assertIn(0, self.manager.queues_data)
        self.assertEqual(self.manager.get_current_index(), 0)

    def test_add_and_update_queue(self):
        """Тест 2: Добавление данных и обновление"""
        # Создаем данные для очереди 0
        state_0 = {"search_tags": ["iphone"], "min_price": 100}
        self.manager.set_state(state_0, 0)
        
        saved = self.manager.get_state(0)
        self.assertEqual(saved["search_tags"], ["iphone"])
        self.assertEqual(saved["min_price"], 100)
        
        # Создаем очередь 1
        state_1 = {"search_tags": ["samsung"], "min_price": 200}
        self.manager.set_state(state_1, 1)
        
        self.assertEqual(len(self.manager.queues_data), 2)
        self.assertEqual(self.manager.get_state(1)["search_tags"], ["samsung"])

    def test_delete_queue_logic(self):
        """Тест 3: Логика удаления и сдвига индексов"""
        # Создаем 3 очереди: 0 (A), 1 (B), 2 (C)
        self.manager.set_state({"search_tags": ["A"]}, 0)
        self.manager.set_state({"search_tags": ["B"]}, 1)
        self.manager.set_state({"search_tags": ["C"]}, 2)
        
        # Удаляем среднюю (index 1 / B)
        self.manager.delete_queue(1)
        
        # Ожидаем: 
        # Index 0 -> A
        # Index 1 -> C (сдвинулся с 2)
        # Всего 2 очереди
        
        self.assertEqual(len(self.manager.queues_data), 2)
        self.assertEqual(self.manager.get_state(0)["search_tags"], ["A"])
        self.assertEqual(self.manager.get_state(1)["search_tags"], ["C"])
        
        # Проверяем, что 2 исчезла
        self.assertNotIn(2, self.manager.queues_data)

    def test_persistence(self):
        """Тест 4: Сохранение и загрузка с диска"""
        self.manager.set_state({"search_tags": ["SAVE_TEST"]}, 0)
        self.manager.save_current_state()
        
        # Создаем новый инстанс менеджера, он должен подгрузить файл
        new_manager = QueueStateManager()
        # Важно: monkey-patch для него тоже нужен, если он создается заново
        # (в данном тесте setUp патчит класс, так что ок)
        
        loaded_state = new_manager.get_state(0)
        self.assertEqual(loaded_state["search_tags"], ["SAVE_TEST"])

if __name__ == '__main__':
    unittest.main()