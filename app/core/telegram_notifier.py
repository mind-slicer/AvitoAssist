import requests
from app.core.log_manager import logger

class TelegramNotifier:
    def __init__(self, token: str, chat_ids_str: str):
        self.token = token
        self.chat_ids = self._parse_chat_ids(chat_ids_str)
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.enabled = bool(self.token and self.chat_ids)

    def _parse_chat_ids(self, raw_str: str) -> list:
        """Разбивает строку '123, 456' на список ID"""
        if not raw_str: return []
        return [x.strip() for x in raw_str.replace(';', ',').split(',') if x.strip()]

    def update_config(self, token: str, chat_ids_str: str):
        self.token = token
        self.chat_ids = self._parse_chat_ids(chat_ids_str)
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.enabled = bool(self.token and self.chat_ids)

    def _send(self, text: str):
        if not self.enabled: return
        
        # Рассылка по всем ID
        for chat_id in self.chat_ids:
            try:
                url = f"{self.base_url}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
                # Короткий таймаут, чтобы не вешать программу
                requests.post(url, json=payload, timeout=5)
            except Exception as e:
                logger.error(f"Telegram fail (ID {chat_id}): {e}")

    def send_new_favorite(self, item: dict):
        if not self.enabled: return
        try:
            title = item.get('title', 'Без названия')
            price = item.get('price', 0)
            link = item.get('link', '')
            city = item.get('city', 'Неизвестно')
            
            msg = (
                f"📌 <b>Добавлено в отслеживание</b>\n\n"
                f"📦 <b>{title}</b>\n"
                f"💰 {price:,} ₽\n"
                #f"📍 {city}\n\n"
                f"🔗 <a href='{link}'>Открыть объявление</a>"
            ).replace(",", " ")
            self._send(msg)
            logger.info(f"TG: Уведомление о новом избранном отправлено ({len(self.chat_ids)} получателей).")
        except Exception as e:
            logger.error(f"Ошибка отправки TG: {e}")

    def send_update(self, item: dict, changes: list):
        if not self.enabled: return
        title = item.get('title', 'Без названия')
        link = item.get('link', '')
        change_text = "\n".join([f"• {c}" for c in changes])
        
        msg = (
            f"🔔 <b>Изменение объявления</b>\n\n"
            f"📦 <b>{title}</b>\n"
            f"{change_text}\n\n"
            f"🔗 <a href='{link}'>Проверить</a>"
        )
        self._send(msg)

    def send_closed(self, item: dict):
        if not self.enabled: return
        title = item.get('title', 'Без названия')
        link = item.get('link', '')
        msg = (
            f"❌ <b>Объявление закрыто</b>\n\n"
            f"📦 {title}\n"
            f"Снято с мониторинга.\n\n"
            f"🔗 <a href='{link}'>Посмотреть</a>"
        )
        self._send(msg)