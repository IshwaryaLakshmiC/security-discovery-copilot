from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.engines.discovery import DiscoveryEngine
from app.models.schemas import DiscoveryMessage, Message
from app.core.database import execute
from datetime import datetime
import json

router = APIRouter()
engine = DiscoveryEngine()

# In-memory cache. RDS (discovery_messages table) is the source of truth.
# On cache miss, _load_messages() rebuilds this from the database, so a
# service restart no longer loses any transcript.
session_messages: dict[str, list[Message]] = {}
session_contexts: dict[str, dict] = {}


def _persist_message(session_id: str, msg: Message):
    execute("""
        INSERT INTO discovery_messages (session_id, role, content, created_at)
        VALUES (%s, %s, %s, %s)
    """, (session_id, msg.role, msg.content, msg.timestamp))


def _load_messages(session_id: str) -> list[Message]:
    """Load transcript from RDS if not already cached in memory.
    This is what makes sessions survive a service restart."""
    if session_id in session_messages:
        return session_messages[session_id]

    rows = execute("""
        SELECT role, content, created_at FROM discovery_messages
        WHERE session_id = %s ORDER BY id ASC
    """, (session_id,), fetch=True)

    messages = [Message(role=r["role"], content=r["content"], timestamp=r["created_at"]) for r in rows]
    session_messages[session_id] = messages
    return messages


@router.post("/{session_id}/message")
async def send_message(session_id: str, body: DiscoveryMessage):
    """Send a message and get a streaming response from the discovery engine"""

    messages = _load_messages(session_id)

    user_msg = Message(role="user", content=body.content, timestamp=datetime.utcnow())
    messages.append(user_msg)
    _persist_message(session_id, user_msg)

    context = session_contexts.get(session_id, {})

    async def generate():
        full_response = ""
        async for chunk in engine.stream_response(messages, context):
            full_response += chunk
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        assistant_msg = Message(role="assistant", content=full_response, timestamp=datetime.utcnow())
        messages.append(assistant_msg)
        _persist_message(session_id, assistant_msg)

        is_complete = engine.is_discovery_complete(messages)
        yield f"data: {json.dumps({'done': True, 'discovery_complete': is_complete})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/{session_id}/start")
async def start_discovery(session_id: str, context: dict = {}):
    """Start a discovery session with optional context"""
    session_messages[session_id] = []
    session_contexts[session_id] = context

    async def generate():
        full_response = ""
        async for chunk in engine.stream_response([], context):
            full_response += chunk
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        assistant_msg = Message(role="assistant", content=full_response, timestamp=datetime.utcnow())
        session_messages[session_id].append(assistant_msg)
        _persist_message(session_id, assistant_msg)
        yield f"data: {json.dumps({'done': True, 'discovery_complete': False})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{session_id}/transcript")
async def get_transcript(session_id: str):
    """Get the full discovery transcript"""
    messages = _load_messages(session_id)
    return {"session_id": session_id, "messages": messages}


@router.post("/{session_id}/extract")
async def extract_entities(session_id: str):
    """Extract structured entities from the transcript"""
    messages = _load_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for session")

    entities = await engine.extract_entities(messages)
    return {"session_id": session_id, "entities": entities}
