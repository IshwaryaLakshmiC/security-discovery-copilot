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
            print(f"Bedrock failed ({e}), trying Groq")
            try:
                return await self._groq_complete(system, messages, max_tokens)
            except Exception as e2:
                print(f"Groq failed ({e2}), trying Gemini")
                try:
                    return await self._gemini_complete(system, messages, max_tokens)
                except Exception as e3:
                    print(f"Gemini failed ({e3}), falling back to OpenRouter")
                    return await self._openrouter_complete(system, messages, max_tokens)

    async def stream(self, system: str, messages: list[dict], max_tokens: int = 2000) -> AsyncGenerator[str, None]:
        """Streaming completion for discovery chat"""
        try:
            got_any = False
            async for chunk in self._bedrock_stream(system, messages, max_tokens):
                got_any = True
                yield chunk
            if got_any:
                return
            raise Exception("Bedrock stream produced no content")
        except Exception as e:
            print(f"Bedrock stream failed ({e}), trying Groq")
        try:
            got_any = False
            async for chunk in self._groq_stream(system, messages, max_tokens):
                got_any = True
                yield chunk
            if got_any:
                return
            raise Exception("Groq stream produced no content")
        except Exception as e2:
            print(f"Groq stream failed ({e2}), trying Gemini")
        try:
            got_any = False
            async for chunk in self._gemini_stream(system, messages, max_tokens):
                got_any = True
                yield chunk
            if got_any:
                return
            raise Exception("Gemini stream produced no content")
        except Exception as e3:
            print(f"Gemini stream failed ({e3}), falling back to OpenRouter")
        async for chunk in self._openrouter_stream(system, messages, max_tokens):
            yield chunk

    async def _groq_complete(self, system: str, messages: list[dict], max_tokens: int) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={"model": settings.groq_model, "max_tokens": max_tokens,
                      "messages": [{"role": "system", "content": system}] + messages},
                timeout=60.0
            )
            if resp.status_code != 200:
                raise Exception(f"Groq HTTP {resp.status_code}: {resp.text[:300]}")
            return resp.json()["choices"][0]["message"]["content"]

    async def _groq_stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={"model": settings.groq_model, "max_tokens": max_tokens, "stream": True,
                      "messages": [{"role": "system", "content": system}] + messages},
                timeout=60.0
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    raise Exception(f"Groq HTTP {resp.status_code}: {error_body.decode(errors='ignore')[:300]}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            data = json.loads(line[6:])
                            content = data["choices"][0].get("delta", {}).get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass

    async def _gemini_complete(self, system: str, messages: list[dict], max_tokens: int) -> str:
        gemini_contents = self._to_gemini_format(messages)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={
                "contents": gemini_contents,
                "systemInstruction": {"parts": [{"text": system}]},
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
            }, timeout=60.0)
            if resp.status_code != 200:
                raise Exception(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _gemini_stream(self, system: str, messages: list[dict], max_tokens: int) -> AsyncGenerator[str, None]:
        gemini_contents = self._to_gemini_format(messages)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:streamGenerateContent?key={settings.gemini_api_key}&alt=sse"
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, json={
                "contents": gemini_contents,
                "systemInstruction": {"parts": [{"text": system}]},
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
            }, timeout=60.0) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    raise Exception(f"Gemini HTTP {resp.status_code}: {error_body.decode(errors='ignore')[:300]}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            text = data["candidates"][0]["content"]["parts"][0].get("text", "")
                            if text:
                                yield text
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass

    def _to_gemini_format(self, messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            out.append({"role": role, "parts": [{"text": m["content"]}]})
        return out

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
                if response.status_code != 200:
                    error_body = await response.aread()
                    error_text = error_body.decode("utf-8", errors="ignore")
                    print(f"OpenRouter error {response.status_code}: {error_text}")
                    yield f"[Error: OpenRouter returned {response.status_code}. {error_text[:200]}]"
                    return

                got_any_content = False
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            data = json.loads(line[6:])
                            if "error" in data:
                                print(f"OpenRouter inline error: {data['error']}")
                                yield f"[Error: {data['error'].get('message', 'unknown error')}]"
                                return
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                got_any_content = True
                                yield delta["content"]
                        except json.JSONDecodeError as e:
                            print(f"OpenRouter SSE parse error: {e} | line: {line[:200]}")
                        except Exception as e:
                            print(f"OpenRouter unexpected error: {e} | line: {line[:200]}")

                if not got_any_content:
                    print("OpenRouter stream completed with zero content chunks")
                    yield "[No response generated — the model may have returned empty content. Try again.]"


def get_llm_client() -> LLMClient:
    return LLMClient()
