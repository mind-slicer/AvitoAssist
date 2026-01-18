import aiohttp
import asyncio

from app.core.log_manager import logger


class LlamaClient:
    def __init__(self, port: int, request_timeout: int = 120):
        self.base_url = f"http://127.0.0.1:{port}"
        self.session = None
        self.request_timeout = request_timeout

    async def ensure_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=120) 
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def is_healthy(self) -> bool:
        try:
            await self.ensure_session()
            async with self.session.get(f"{self.base_url}/health", timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def chat_completion(self, model: str, messages: list, params: dict = None) -> str:
        if not self.session:
            timeout = aiohttp.ClientTimeout(
                total=self.request_timeout,
                connect=10,
                sock_read=self.request_timeout
            )
            self.session = aiohttp.ClientSession(timeout=timeout)

        payload = {
            "model": model,
            "messages": messages,
            **(params or {})
        }

        try:
            async with self.session.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('choices', [{}])[0].get('message', {}).get('content', '')
                else:
                    logger.error(f"LLM server error: {response.status}")
                    return ""
        except asyncio.TimeoutError:
            logger.error(f"LLM request timeout after {self.request_timeout}s")
            return ""
        except Exception as e:
            logger.error(f"LLM request error: {e}")
            return ""