import boto3
import json
import httpx
from typing import AsyncGenerator
from app.core.config import get_settings

settings = get_settings()


class LLMClient:
    """
    Bedrock (Claude Sonnet) primary.
    OpenRouter (Mistral free) fallback when Bedrock unavailable.
    """

    def __init__(self):
        self.bedrock = boto3.client(
            service_name="bedrock-runtime",
            region_name=settings.aws_region
        )

    async def complete(self, system: str, messages: list[dict], max_tokens: int = 2000) -> str:
        """Non-streaming completion"""
        try:
            return await self._bedrock_complete(system, messages, max_tokens)
        except Exception as e:
            print(f"Bedrock failed ({e}), falling back to OpenRouter")
            return await self._openrouter_complete(system, messages, max_tokens)

    async def stream(self, system: str, messages: list[dict], max_tokens: int = 2000) -> AsyncGenerator[str, None]:
        """Streaming completion for discovery chat"""
        try:
            async for chunk in self._bedrock_stream(system, messages, max_tokens):
                yield chunk
        except Exception as e:
            print(f"Bedrock stream failed ({e}), falling back to OpenRouter")
            async for chunk in self._openrouter_stream(system, messages, max_tokens):
                yield chunk

    async def _bedrock_complete(self, system: str, messages: list[dict], max_tokens: int) -> str:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "temperature": 0.3,
        })
        response = self.bedrock.invoke_model(
            modelId=settings.bedrock_model_id,
            body=body,
            contentType="application/json",
            accept="application/json"
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]

    async def _bedrock_stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncGenerator[str, None]:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "temperature": 0.3,
        })
        response = self.bedrock.invoke_model_with_response_stream(
            modelId=settings.bedrock_model_id,
            body=body,
            contentType="application/json",
            accept="application/json"
        )
        stream = response.get("body")
        for event in stream:
            chunk = event.get("chunk")
            if chunk:
                data = json.loads(chunk["bytes"])
                if data.get("type") == "content_block_delta":
                    delta = data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield delta.get("text", "")

    async def _openrouter_complete(self, system: str, messages: list[dict], max_tokens: int) -> str:
        all_messages = [{"role": "system", "content": system}] + messages
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "HTTP-Referer": "https://ishwaryaaunfiltered.live",
                    "X-Title": "Security Discovery Copilot"
                },
                json={
                    "model": settings.openrouter_model,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                    "messages": all_messages
                },
                timeout=60.0
            )
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def _openrouter_stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncGenerator[str, None]:
        all_messages = [{"role": "system", "content": system}] + messages
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "HTTP-Referer": "https://ishwaryaaunfiltered.live",
                    "X-Title": "Security Discovery Copilot"
                },
                json={
                    "model": settings.openrouter_model,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                    "messages": all_messages,
                    "stream": True
                },
                timeout=60.0
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            data = json.loads(line[6:])
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except Exception:
                            pass


def get_llm_client() -> LLMClient:
    return LLMClient()
