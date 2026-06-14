from fastapi import APIRouter, HTTPException
from app.models.schemas import SessionCreate, Session
from datetime import datetime
import uuid

router = APIRouter()
sessions_store: dict[str, Session] = {}


@router.post("/", response_model=Session)
async def create_session(body: SessionCreate):
    session = Session(
        id=str(uuid.uuid4()),
        company_name=body.company_name or "Prospect",
        industry=body.industry,
        company_size=body.company_size,
        scenario_id=body.scenario_id,
        status="discovery",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    sessions_store[session.id] = session
    return session


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str):
    session = sessions_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}/status")
async def update_status(session_id: str, status: str):
    session = sessions_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.status = status
    session.updated_at = datetime.utcnow()
    return session
