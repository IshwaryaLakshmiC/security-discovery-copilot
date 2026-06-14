from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.engines.discovery import DiscoveryEngine
from app.models.schemas import DiscoveryMessage, Message
from datetime import datetime
import json

router = APIRouter()
engine = DiscoveryEngine()

# In-memory session store (replace with DB in production)
session_messages: dict[str, list[Message]] = {}
session_contexts: dict[str, dict] = {}


@router.post("/{session_id}/message")
async def send_message(session_id: str, body: DiscoveryMessage):
    """Send a message and get a streaming response from the discovery engine"""

    if session_id not in session_messages:
        session_messages[session_id] = []

    # Add user message
    user_msg = Message(role="user", content=body.content, timestamp=datetime.utcnow())
    session_messages[session_id].append(user_msg)

    messages = session_messages[session_id]
    context = session_contexts.get(session_id, {})

    async def generate():
        full_response = ""
        async for chunk in engine.stream_response(messages, context):
            full_response += chunk
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        # Store assistant response
        assistant_msg = Message(role="assistant", content=full_response, timestamp=datetime.utcnow())
        session_messages[session_id].append(assistant_msg)

        # Check completion
        is_complete = engine.is_discovery_complete(session_messages[session_id])
        yield f"data: {json.dumps({'done': True, 'discovery_complete': is_complete})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/{session_id}/start")
async def start_discovery(session_id: str, context: dict = {}):
    """Start a discovery session with optional context"""
    session_messages[session_id] = []
    session_contexts[session_id] = context

    async def generate():
        full_response = ""
        # Send opening message with empty history (LLM will open the conversation)
        async for chunk in engine.stream_response([], context):
            full_response += chunk
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        assistant_msg = Message(role="assistant", content=full_response, timestamp=datetime.utcnow())
        session_messages[session_id].append(assistant_msg)
        yield f"data: {json.dumps({'done': True, 'discovery_complete': False})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{session_id}/transcript")
async def get_transcript(session_id: str):
    """Get the full discovery transcript"""
    messages = session_messages.get(session_id, [])
    return {"session_id": session_id, "messages": messages}


@router.post("/{session_id}/extract")
async def extract_entities(session_id: str):
    """Extract structured entities from the transcript"""
    messages = session_messages.get(session_id, [])
    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for session")

    entities = await engine.extract_entities(messages)
    return {"session_id": session_id, "entities": entities}
