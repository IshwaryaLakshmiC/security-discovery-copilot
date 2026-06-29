"""
Shared utility for extracting JSON from LLM responses that may be wrapped
in markdown fences or leading/trailing prose. Different providers in the
Bedrock -> Groq -> Gemini -> OpenRouter fallback chain format this
differently -- Claude tends to return clean JSON, Llama 3.3 via Groq and
Gemini sometimes wrap it in explanatory text like:
  "Here's the extracted information:\n\nLet me know if you need..."

Used by: discovery.py (entity extraction), recommendations.py (vendor
recommendations), executive.py (executive summary) -- any engine that
asks an LLM to return structured JSON.

Also provides json_default() -- a json.dumps() handler for types it
doesn't know natively (datetime, date, UUID), used when persisting
result objects to RDS via advanced.py and executive.py.
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


def json_default(obj):
    """Handler for json.dumps() covering types it doesn't know natively --
    datetime, date, UUID. Pydantic's model_dump() (without mode="json")
    returns raw datetime objects, not ISO strings, which crashes a plain
    json.dumps() call with no default handler. Use as: json.dumps(payload,
    default=json_default) anywhere a model with a datetime field (almost
    every result object here has generated_at) gets persisted to RDS."""
    from datetime import datetime, date
    from uuid import UUID
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1]
    if "```" in cleaned:
        cleaned = cleaned.replace("```", "")
    return cleaned
