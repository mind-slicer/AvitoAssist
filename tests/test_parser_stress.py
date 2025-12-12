#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Упрощенное стресс-тестирование парсера Avito.
Фокус на основных сценариях без сложных моков.
"""

import pytest
import time
import threading
import random
from unittest.mock import Mock, MagicMock, patch
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium.common.exceptions import TimeoutException, WebDriverException

from app.core.parser import (
    BanRecoveryStrategy, 
    PageLoader, 
    SearchNavigator, 
    ItemParser,
    AvitoParser
)


# --- Стресс-тесты для BanRecoveryStrategy ---
class TestBanRecoveryStrategyStress:
    """Стресс-тесты для механизма восстановления после банов."""

    def test_concurrent_ban_handling(self):
        """Тест одновременной обработки банов в нескольких потоках."""
        mock_driver_manager = Mock()
        strategy = BanRecoveryStrategy(mock_driver_manager)
        
        def simulate_ban(strategy, thread_id):
            """Симуляция обработки бана в потоке."""
            start_time = time.time()
            result = strategy.handle_soft_ban()
            end_time = time.time()
            return {
                'thread_id': thread_id,
                'success': result,
                'duration': end_time - start_time,
                'ban_count': strategy.ban_count
            }
        
        # Запускаем 2 потока для симуляции одновременных банов
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(simulate_ban, strategy, i) for i in range(2)]
            results = [future.result() for future in as_completed(futures)]
        
        # Проверяем, что все потоки завершились успешно
        assert all(result['success'] for result in results)
        assert strategy.ban_count == 2
        
        # Проверяем, что время обработки увеличивалось с каждым баном
        durations = [r['duration'] for r in sorted(results, key=lambda x: x['thread_id'])]
        assert durations[0] >= 30  # Первый бан - 30 секунд
        assert durations[1] >= 60  # Второй бан - 60 секунд

    def test_ban_handling_under_heavy_load(self):
        """Тест обработки банов при высокой нагрузке."""
        mock_driver_manager = Mock()
        strategy = BanRecoveryStrategy(mock_driver_manager)
        
        # Симулируем 3 последовательных бана
        for i in range(3):
            start_time = time.time()
            result = strategy.handle_soft_ban()
            duration = time.time() - start_time
            
            assert result is True
            assert strategy.ban_count == i + 1
            
            # Проверяем, что время ожидания соответствует стратегии
            if i == 0:
                assert duration >= 30
            elif i == 1:
                assert duration >= 60
            else:
                assert duration >= 120


# --- Стресс-тесты для PageLoader ---
class TestPageLoaderStress:
    """Стресс-тесты для загрузчика страниц."""

    def test_concurrent_page_loading(self):
        """Тест одновременной загрузки нескольких страниц."""
        
        def create_mock_driver(success_rate=0.9):
            """Создает мок-драйвер с заданной вероятностью успеха."""
            mock_driver = Mock()
            mock_driver.title = "Test Page"
            
            def execute_script(cmd):
                if random.random() < success_rate:
                    return "complete"
                else:
                    raise TimeoutException("Page load timeout")
            
            mock_driver.execute_script = execute_script
            return mock_driver
        
        # Создаем 5 мок-драйверов
        drivers = [create_mock_driver(0.8) for _ in range(5)]
        
        # Запускаем параллельную загрузку
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(
                    PageLoader.safe_get, 
                    driver, 
                    f"https://example.com/page_{i}"
                )
                for i, driver in enumerate(drivers)
            ]
            results = [future.result() for future in as_completed(futures)]
        
        # Проверяем, что большинство запросов завершились успешно
        success_count = sum(results)
        assert success_count >= 3

    def test_page_loading_with_retry_logic(self):
        """Тест логики повторных попыток при загрузке страниц."""
        mock_driver = Mock()
        mock_driver.title = "Test Page"
        
        # Симулируем ошибки с последующим успехом
        call_count = 0
        def unreliable_execute_script(cmd):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Первые 2 попытки завершаются ошибкой
                raise WebDriverException("Network error")
            return "complete"
        
        mock_driver.execute_script = unreliable_execute_script
        
        result = PageLoader.safe_get(mock_driver, "https://example.com")
        assert result is True
        assert call_count == 3  # 2 ошибки + 1 успех


# --- Стресс-тесты для ItemParser ---
class TestItemParserStress:
    """Стресс-тесты для парсера элементов."""

    def test_parse_large_number_of_items(self):
        """Тест парсинга большого количества элементов."""
        
        # Создаем HTML с большим количеством элементов
        html = """
        <div class="items-container">
        """
        
        for i in range(50):
            html += f"""
            <div data-marker="item">
                <a href="/moskva/tovary/item_{i}" data-marker="item-title">
                    Item {i}
                </a>
                <span data-marker="item-price">{random.randint(1000, 100000)}&nbsp;₽</span>
                <div class="iva-item-bottomBlock">
                    <p class="styles-module-root">Description for item {i}</p>
                </div>
                <div data-marker="item-date">Today</div>
            </div>
            """
        
        html += "</div>"
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        elements = soup.select('[data-marker="item"]')
        
        # Парсим все элементы
        start_time = time.time()
        parsed_items = []
        
        for element in elements:
            item = ItemParser.parse_search_item(element)
            if item:
                parsed_items.append(item)
        
        duration = time.time() - start_time
        
        # Проверяем, что все элементы были успешно спарсены
        assert len(parsed_items) == 50
        assert duration < 2.0  # Ожидаем, что парсинг 50 элементов займет менее 2 секунд

    def test_parse_items_with_varying_quality(self):
        """Тест парсинга элементов с разным качеством данных."""
        
        html = """
        <div class="items-container">
        """
        
        # Создаем элементы с разным качеством данных
        for i in range(30):
            price = random.randint(1000, 100000) if random.random() > 0.2 else None
            description = f"Description {i}" if random.random() > 0.3 else None
            
            html += f"""
            <div data-marker="item">
                <a href="/moskva/tovary/item_{i}" data-marker="item-title">
                    Item {i}
                </a>
                {'<span data-marker="item-price">' + str(price) + '&nbsp;₽</span>' if price else ''}
                {'<div class="iva-item-bottomBlock"><p class="styles-module-root">' + description + '</p></div>' if description else ''}
                <div data-marker="item-date">Today</div>
            </div>
            """
        
        html += "</div>"
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        elements = soup.select('[data-marker="item"]')
        
        # Парсим все элементы
        parsed_items = []
        for element in elements:
            item = ItemParser.parse_search_item(element)
            if item:
                parsed_items.append(item)
        
        # Проверяем, что большинство элементов были успешно спарсены
        assert len(parsed_items) >= 20


# --- Интеграционные стресс-тесты ---
class TestParserIntegrationStress:
    """Интеграционные стресс-тесты для проверки взаимодействия компонентов."""

    def test_concurrent_parser_instances(self):
        """Тест одновременной работы нескольких экземпляров парсера."""
        
        def create_parser_instance():
            """Создает экземпляр парсера с замоканным драйвером."""
            parser = AvitoParser(debug_mode=True)
            
            # Мокаем драйвер и его методы
            mock_driver = Mock()
            mock_driver.title = "Test Page"
            mock_driver.execute_script.return_value = "complete"
            mock_driver.page_source = "<html></html>"
            mock_driver.find_elements.return_value = []
            
            # Используем патчинг для свойства driver
            with patch.object(type(parser.driver_manager), 'driver', new_callable=lambda: mock_driver):
                parser.driver_manager._initialize_driver = Mock()
                parser.driver_manager.cleanup = Mock()
                return parser
        
        # Создаем 2 экземпляра парсера
        parsers = [create_parser_instance() for _ in range(2)]
        
        # Запускаем параллельные поисковые запросы
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    parser.search_items, 
                    f"query_{i}",
                    max_total_items=2
                )
                for i, parser in enumerate(parsers)
            ]
            results = [future.result() for future in as_completed(futures)]
        
        # Проверяем, что все запросы завершились
        assert len(results) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])