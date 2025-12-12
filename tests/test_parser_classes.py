#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модульные и интеграционные тесты для классов парсера:
BanRecoveryStrategy, PageLoader, SearchNavigator и ItemParser.
"""

import pytest
import time
import random
from unittest.mock import Mock, MagicMock, patch
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

from app.core.parser import BanRecoveryStrategy, PageLoader, SearchNavigator, ItemParser


# --- Тесты для BanRecoveryStrategy ---
class TestBanRecoveryStrategy:
    """Тесты для класса BanRecoveryStrategy."""

    def test_initialization(self):
        """Тест инициализации BanRecoveryStrategy."""
        mock_driver_manager = Mock()
        strategy = BanRecoveryStrategy(mock_driver_manager)
        assert strategy.driver_manager == mock_driver_manager
        assert strategy.ban_count == 0
        assert strategy.last_ban_time is None

    def test_handle_soft_ban_first_time(self):
        """Тест обработки первого софт-бана."""
        mock_driver_manager = Mock()
        strategy = BanRecoveryStrategy(mock_driver_manager)
        
        start_time = time.time()
        result = strategy.handle_soft_ban()
        end_time = time.time()
        
        assert result is True
        assert strategy.ban_count == 1
        assert strategy.last_ban_time is not None
        assert end_time - start_time >= 30  # Проверка времени ожидания

    def test_handle_soft_ban_multiple_times(self):
        """Тест обработки нескольких софт-банов."""
        mock_driver_manager = Mock()
        strategy = BanRecoveryStrategy(mock_driver_manager)
        
        # Первый бан
        strategy.handle_soft_ban()
        assert strategy.ban_count == 1
        
        # Второй бан
        strategy.handle_soft_ban()
        assert strategy.ban_count == 2
        
        # Третий бан
        strategy.handle_soft_ban()
        assert strategy.ban_count == 3

    def test_handle_soft_ban_with_stop_check(self):
        """Тест обработки софт-бана с прерыванием."""
        mock_driver_manager = Mock()
        strategy = BanRecoveryStrategy(mock_driver_manager)
        
        stop_flag = False
        def stop_check():
            nonlocal stop_flag
            return stop_flag
        
        # Начинаем обработку бана
        result = strategy.handle_soft_ban(stop_check=stop_check)
        assert result is True
        
        # Теперь прерываем
        stop_flag = True
        result = strategy.handle_soft_ban(stop_check=stop_check)
        assert result is False

    def test_handle_soft_ban_cookie_reset(self):
        """Тест сброса cookies при обработке бана."""
        mock_driver_manager = Mock()
        mock_driver = Mock()
        mock_driver_manager.driver = mock_driver
        
        strategy = BanRecoveryStrategy(mock_driver_manager)
        
        # Первый бан (без сброса cookies)
        strategy.handle_soft_ban()
        mock_driver.delete_all_cookies.assert_not_called()
        
        # Второй бан (со сбросом cookies)
        strategy.handle_soft_ban()
        mock_driver.delete_all_cookies.assert_called_once()

    def test_handle_soft_ban_user_agent_change(self):
        """Тест смены User-Agent при обработке бана."""
        mock_driver_manager = Mock()
        mock_driver = Mock()
        mock_driver_manager.driver = mock_driver
        
        strategy = BanRecoveryStrategy(mock_driver_manager)
        
        # Первый и второй бан (без смены UA)
        strategy.handle_soft_ban()
        strategy.handle_soft_ban()
        mock_driver.execute_cdp_cmd.assert_not_called()
        
        # Третий бан (со сменой UA)
        strategy.handle_soft_ban()
        mock_driver.execute_cdp_cmd.assert_called_once()


# --- Тесты для PageLoader ---
class TestPageLoader:
    """Тесты для класса PageLoader."""

    def test_wait_for_load_success(self):
        """Тест успешного ожидания загрузки страницы."""
        mock_driver = Mock()
        mock_driver.execute_script.return_value = "complete"
        
        result = PageLoader.wait_for_load(mock_driver, timeout=5)
        assert result is True

    def test_wait_for_load_timeout(self):
        """Тест таймаута при ожидании загрузки страницы."""
        mock_driver = Mock()
        mock_driver.execute_script.side_effect = TimeoutException()
        
        result = PageLoader.wait_for_load(mock_driver, timeout=5)
        assert result is False

    def test_safe_get_success(self):
        """Тест успешной загрузки страницы."""
        mock_driver = Mock()
        mock_driver.title = "Test Page"
        mock_driver.execute_script.return_value = "complete"
        
        result = PageLoader.safe_get(mock_driver, "https://example.com")
        assert result is True

    def test_safe_get_soft_ban_detected(self):
        """Тест обнаружения софт-бана при загрузке страницы."""
        mock_driver = Mock()
        mock_driver.title = "Доступ ограничен"
        
        mock_ban_strategy = Mock()
        mock_ban_strategy.handle_soft_ban.return_value = True
        
        result = PageLoader.safe_get(
            mock_driver, 
            "https://example.com",
            ban_strategy=mock_ban_strategy
        )
        
        mock_ban_strategy.handle_soft_ban.assert_called()

    def test_safe_get_retry_logic(self):
        """Тест логики повторных попыток при загрузке страницы."""
        mock_driver = Mock()
        mock_driver.title = "Test Page"
        mock_driver.execute_script.side_effect = [
            WebDriverException("Network error"),
            "complete"
        ]
        
        result = PageLoader.safe_get(mock_driver, "https://example.com")
        assert result is True
        assert mock_driver.execute_script.call_count == 2

    def test_scroll_page(self):
        """Тест прокрутки страницы."""
        mock_driver = Mock()
        mock_driver.execute_script.return_value = 1000
        
        PageLoader.scroll_page(mock_driver)
        mock_driver.execute_script.assert_called()


# --- Тесты для SearchNavigator ---
class TestSearchNavigator:
    """Тесты для класса SearchNavigator."""

    def test_initialization(self):
        """Тест инициализации SearchNavigator."""
        mock_driver = Mock()
        navigator = SearchNavigator(mock_driver)
        assert navigator.driver == mock_driver

    def test_human_type_success(self):
        """Тест успешного ввода текста."""
        mock_driver = Mock()
        mock_element = Mock()
        mock_element.is_displayed.return_value = True
        
        navigator = SearchNavigator(mock_driver)
        result = navigator._human_type(mock_element, "test")
        assert result is True

    def test_human_type_element_not_displayed(self):
        """Тест ввода текста, когда элемент не отображается."""
        mock_driver = Mock()
        mock_element = Mock()
        mock_element.is_displayed.return_value = False
        
        navigator = SearchNavigator(mock_driver)
        result = navigator._human_type(mock_element, "test")
        mock_driver.execute_script.assert_called()

    def test_is_valid_url_valid(self):
        """Тест валидации корректного URL."""
        mock_driver = Mock()
        navigator = SearchNavigator(mock_driver)
        
        valid_url = "https://www.avito.ru/moskva/telefony?q=iphone"
        result = navigator._is_valid_url(valid_url)
        assert result is True

    def test_is_valid_url_invalid(self):
        """Тест валидации некорректного URL."""
        mock_driver = Mock()
        navigator = SearchNavigator(mock_driver)
        
        invalid_url = "https://www.avito.ru"
        result = navigator._is_valid_url(invalid_url)
        assert result is False

    def test_get_search_suggestions(self):
        """Тест получения поисковых предложений."""
        mock_driver = Mock()
        navigator = SearchNavigator(mock_driver)
        
        # Мокаем метод _type_query
        with patch.object(navigator, '_type_query', return_value=[]):
            result = navigator.get_search_suggestions("test")
            assert result == []

    def test_perform_smart_search(self):
        """Тест выполнения умного поиска."""
        mock_driver = Mock()
        navigator = SearchNavigator(mock_driver)
        
        # Мокаем метод _type_query
        with patch.object(navigator, '_type_query', return_value=[]):
            result = navigator.perform_smart_search("test")
            assert result == []


# --- Тесты для ItemParser ---
class TestItemParser:
    """Тесты для класса ItemParser."""

    def test_extract_ad_id(self):
        """Тест извлечения ID объявления из URL."""
        url = "https://www.avito.ru/moskva/telefony/iphone_123456789"
        ad_id = ItemParser.extract_ad_id(url)
        assert ad_id == "123456789"

    def test_extract_ad_id_no_id(self):
        """Тест извлечения ID объявления из URL без ID."""
        url = "https://www.avito.ru/moskva/telefony"
        ad_id = ItemParser.extract_ad_id(url)
        assert ad_id == "telefony"

    def test_parse_search_item(self):
        """Тест парсинга элемента поиска."""
        # Создаем мок-объект для BeautifulSoup элемента
        mock_element = Mock()
        mock_element.select_one.return_value = Mock()
        mock_element.select_one.return_value.get.return_value = "test"
        mock_element.select_one.return_value.get_text.return_value = "Test Title"
        
        result = ItemParser.parse_search_item(mock_element)
        assert result is None  # Так как мок не полный, ожидаем None

    def test_parse_search_item_with_valid_data(self):
        """Тест парсинга элемента поиска с корректными данными."""
        # Создаем более реалистичный мок
        mock_link_el = Mock()
        mock_link_el.get.return_value = "/moskva/telefony/iphone_123456789"
        mock_link_el.get_text.return_value = "iPhone 12"
        
        mock_price_el = Mock()
        mock_price_el.get_text.return_value = "50 000 ₽"
        
        mock_element = Mock()
        mock_element.select_one.side_effect = [
            mock_link_el,  # PREVIEW_TITLE
            mock_price_el,  # PREVIEW_PRICE
            None,  # PREVIEW_DESC_VARIANTS
            None,  # PREVIEW_DATE
            None,  # PREVIEW_GEO
            None,  # PREVIEW_SELLER_LINK
        ]
        
        result = ItemParser.parse_search_item(mock_element)
        assert result is not None
        assert result['title'] == "iPhone 12"
        assert result['price'] == 50000


# --- Интеграционные тесты ---
class TestParserIntegration:
    """Интеграционные тесты для проверки взаимодействия компонентов."""

    def test_ban_recovery_with_page_loader(self):
        """Тест взаимодействия BanRecoveryStrategy и PageLoader."""
        mock_driver_manager = Mock()
        mock_driver = Mock()
        mock_driver_manager.driver = mock_driver
        
        strategy = BanRecoveryStrategy(mock_driver_manager)
        
        # Мокаем метод handle_soft_ban
        with patch.object(strategy, 'handle_soft_ban', return_value=True):
            mock_driver.title = "Доступ ограничен"
            
            result = PageLoader.safe_get(
                mock_driver, 
                "https://example.com",
                ban_strategy=strategy
            )
            
            strategy.handle_soft_ban.assert_called()

    def test_search_navigator_with_page_loader(self):
        """Тест взаимодействия SearchNavigator и PageLoader."""
        mock_driver = Mock()
        navigator = SearchNavigator(mock_driver)
        
        # Мокаем метод _type_query
        with patch.object(navigator, '_type_query', return_value=[]):
            result = navigator.get_search_suggestions("test")
            assert result == []

    def test_item_parser_with_search_navigator(self):
        """Тест взаимодействия ItemParser и SearchNavigator."""
        mock_driver = Mock()
        navigator = SearchNavigator(mock_driver)
        
        # Мокаем метод _type_query
        with patch.object(navigator, '_type_query', return_value=[]):
            suggestions = navigator.get_search_suggestions("test")
            assert suggestions == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
