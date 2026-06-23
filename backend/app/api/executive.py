from fastapi import APIRouter, HTTPException
from app.engines.executive import ExecutiveEngine
from app.api.gaps import gap_results
from app.api.recommendations import recommendation_results
from app.api.sessions import get_session_or_none

router = APIRouter()
engine = ExecutiveEngine()
executive_results: dict[str, any] = {}


@router.post("/{session_id}/generate")
async def generate_executive_summary(session_id: str):
    """Generate executive summary from completed analysis"""
    session = await get_session_or_none(session_id)
    gap_analysis = gap_results.get(session_id)
    recs = recommendation_results.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not gap_analysis:
        raise HTTPException(status_code=400, detail="Run gap analysis first")
    if not recs:
        raise HTTPException(status_code=400, detail="Run recommendations first")

    summary = await engine.generate(session, gap_analysis, recs)
    executive_results[session_id] = summary
    return summary


@router.get("/{session_id}")
async def get_executive_summary(session_id: str):
    result = executive_results.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No executive summary found")
    return result
