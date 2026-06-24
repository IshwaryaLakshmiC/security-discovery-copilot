from fastapi import APIRouter, HTTPException
from app.engines.executive import ExecutiveEngine
from app.api.gaps import get_gap_results_or_none
from app.api.sessions import get_session_or_none
from app.core.database import execute
import json

router = APIRouter()
engine = ExecutiveEngine()
executive_results: dict = {}


async def _get_recs_or_none(session_id: str):
    from app.api.recommendations import recommendation_results
    if session_id in recommendation_results:
        return recommendation_results[session_id]

    rows = execute("""
        SELECT recommendations FROM recommendation_results
        WHERE session_id = %s ORDER BY generated_at DESC LIMIT 1
    """, (session_id,), fetch=True)
    return rows[0]["recommendations"] if rows else None


@router.post("/{session_id}/generate")
async def generate_executive_summary(session_id: str):
    """Generate executive summary from completed analysis"""
    session = await get_session_or_none(session_id)
    gap_analysis = get_gap_results_or_none(session_id)
    recs = await _get_recs_or_none(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not gap_analysis:
        raise HTTPException(status_code=400, detail="Run gap analysis first")
    if not recs:
        raise HTTPException(status_code=400, detail="Run recommendations first")

    summary = await engine.generate(session, gap_analysis, recs)
    executive_results[session_id] = summary

    execute("""
        INSERT INTO advanced_analysis (session_id, analysis_type, result, generated_at)
        VALUES (%s, 'executive', %s, NOW())
    """, (session_id, json.dumps(summary.model_dump() if hasattr(summary, "model_dump") else summary)))

    return summary


@router.get("/{session_id}")
async def get_executive_summary(session_id: str):
    if session_id in executive_results:
        return executive_results[session_id]

    rows = execute("""
        SELECT result FROM advanced_analysis
        WHERE session_id = %s AND analysis_type = 'executive'
        ORDER BY generated_at DESC LIMIT 1
    """, (session_id,), fetch=True)

    if not rows:
        raise HTTPException(status_code=404, detail="No executive summary found")

    return rows[0]["result"]
