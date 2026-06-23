from fastapi import APIRouter, HTTPException
from app.models.schemas import SessionCreate, Session
from app.core.database import execute
from datetime import datetime
import uuid

router = APIRouter()

# In-memory cache -- speeds up repeated reads within a process lifetime.
# RDS is the source of truth; this is just a cache, never the only copy.
sessions_store: dict[str, Session] = {}


def _row_to_session(row: dict) -> Session:
    return Session(
        id=row["id"],
        company_name=row["company_name"],
        industry=row.get("industry"),
        company_size=row.get("company_size"),
        scenario_id=row.get("scenario_id"),
        status=row.get("status", "discovery"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


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

    execute("""
        INSERT INTO discovery_sessions (id, company_name, industry, company_size, scenario_id, status, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (session.id, session.company_name, session.industry, session.company_size,
          session.scenario_id, session.status, session.created_at, session.updated_at))

    sessions_store[session.id] = session
    return session


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str):
    session = await get_session_or_none(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def get_session_or_none(session_id: str) -> Session | None:
    """Reusable lookup with RDS fallback -- importable by other routers
    so they don't read the raw in-memory dict directly."""
    if session_id in sessions_store:
        return sessions_store[session_id]

    rows = execute("SELECT * FROM discovery_sessions WHERE id = %s", (session_id,), fetch=True)
    if not rows:
        return None

    session = _row_to_session(rows[0])
    sessions_store[session_id] = session
    return session


@router.patch("/{session_id}/status")
async def update_status(session_id: str, status: str):
    execute("""
        UPDATE discovery_sessions SET status = %s, updated_at = NOW() WHERE id = %s
    """, (status, session_id))

    if session_id in sessions_store:
        sessions_store[session_id].status = status

    return {"session_id": session_id, "status": status}
