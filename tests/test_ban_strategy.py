import pytest
from unittest.mock import Mock, patch, ANY
from app.core.parser import BanRecoveryStrategy

@pytest.fixture
def mock_driver_manager():
    """Создает фиктивный менеджер драйвера"""
    mock_dm = Mock()
    mock_dm.driver = Mock()
    return mock_dm

@patch('time.sleep')  # Подменяем сон, чтобы тесты летали
def test_soft_ban_first_occurrence(mock_sleep, mock_driver_manager):
    """Тест: первый бан — только ожидание"""
    strategy = BanRecoveryStrategy(mock_driver_manager)
    
    # Эмулируем бан
    result = strategy.handle_soft_ban()
    
    assert result is True
    assert strategy.ban_count == 1
    # Проверяем, что куки НЕ чистили
    mock_driver_manager.driver.delete_all_cookies.assert_not_called()
    # Проверяем, что UA НЕ меняли
    mock_driver_manager.driver.execute_cdp_cmd.assert_not_called()
    # Проверяем, что спали (30 сек по умолчанию для 1-го раза)
    assert mock_sleep.call_count > 0

@patch('time.sleep')
def test_soft_ban_second_occurrence(mock_sleep, mock_driver_manager):
    """Тест: второй бан — очистка cookies"""
    strategy = BanRecoveryStrategy(mock_driver_manager)
    strategy.ban_count = 1  # Уже был один бан
    
    strategy.handle_soft_ban()
    
    assert strategy.ban_count == 2
    # Должен был вызвать удаление кук
    mock_driver_manager.driver.delete_all_cookies.assert_called_once()
    # UA все еще не меняем
    mock_driver_manager.driver.execute_cdp_cmd.assert_not_called()

@patch('time.sleep')
def test_soft_ban_third_occurrence(mock_sleep, mock_driver_manager):
    """Тест: третий бан — смена User-Agent"""
    strategy = BanRecoveryStrategy(mock_driver_manager)
    strategy.ban_count = 2
    
    strategy.handle_soft_ban()
    
    assert strategy.ban_count == 3
    # Должен сменить UA через CDP команду
    mock_driver_manager.driver.execute_cdp_cmd.assert_called_with(
        'Network.setUserAgentOverride', 
        {"userAgent": ANY} # Нам неважно, какой именно UA, главное что какой-то
    )

@patch('time.sleep')
def test_stop_check_interruption(mock_sleep, mock_driver_manager):
    """Тест: прерывание восстановления пользователем"""
    strategy = BanRecoveryStrategy(mock_driver_manager)
    
    # Функция stop_check возвращает True (пользователь нажал Стоп)
    result = strategy.handle_soft_ban(stop_check=lambda: True)
    
    assert result is False  # Операция прервана