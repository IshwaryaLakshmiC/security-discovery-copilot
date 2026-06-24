"""
Shared utility for extracting JSON from LLM responses that may be wrapped
in markdown fences or leading/trailing prose. Different providers in the
Bedrock -> Groq -> Gemini -> OpenRouter fallback chain format this
differently -- Claude tends to return clean JSON, Llama 3.3 via Groq and
Gemini sometimes wrap it in explanatory text like:
  "Here's the extracted information:\n\n{...}\n\nLet me know if you need..."

Used by: discovery.py (entity extraction), recommendations.py (vendor
recommendations), executive.py (executive summary) -- any engine that
asks an LLM to return structured JSON.
"""
import json


def extract_json_object(text: str) -> dict:
    """Extract a JSON object ({...}) from a possibly prose-wrapped response."""
    cleaned = _strip_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in response")
    return json.loads(cleaned[start:end + 1])


def extract_json_array(text: str) -> list:
    """Extract a JSON array ([...]) from a possibly prose-wrapped response."""
    cleaned = _strip_fences(text)
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON array found in response")
    return json.loads(cleaned[start:end + 1])


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1]
    if "```" in cleaned:
        cleaned = cleaned.replace("```", "")
    return cleaned
