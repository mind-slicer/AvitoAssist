import aiohttp
from typing import Optional, Dict, List, Any
from app.core.log_manager import logger

class LlamaClient:
    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.base_url = f"http://{host}:{port}"
        self.session: Optional[aiohttp.ClientSession] = None

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

    async def chat_completion(self, 
                            model: str, 
                            messages: List[Dict[str, str]], 
                            params: Dict[str, Any] = None) -> Optional[str]:
        await self.ensure_session()
        
        default_params = {
            "temperature": 0.3,
            "max_tokens": 1024,
            "stop": ["<|im_end|>", "<|endoftext|>", "user:", "system:"],
        }
        if params:
            default_params.update(params)

        payload = {
            "model": model,
            "messages": messages,
            **default_params
        }

        try:
            async with self.session.post(f"{self.base_url}/v1/chat/completions", json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Ошибка API: {resp.status}: {text}")
                    return None
                
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
                
        except Exception as e:
            logger.error(f"Запрос провален: {e}")
            return None