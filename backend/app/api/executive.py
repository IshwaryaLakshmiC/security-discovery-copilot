from fastapi import APIRouter, HTTPException
from app.engines.executive import ExecutiveEngine
from app.api.gaps import get_gap_results_or_none
from app.api.sessions import get_session_or_none
from app.core.database import execute
from app.core.json_utils import json_default
import json

router = APIRouter()
engine = ExecutiveEngine()
executive_results: dict = {}


async def _get_recs_or_none(session_id: str):
    """Same restart-dependent shape bug found twice already today: the
    RDS column stores a plain list of dicts (what we wrote when saving),
    but every downstream engine (objection_engine, stakeholder_engine,
    executive engine) expects a RecommendationSet object with a
    .recommendations attribute -- the shape the in-memory cache always
    had, because that's the original object the /generate endpoint built.
    Wrap the raw list back into a RecommendationSet on the RDS path so
    both paths return an identical shape regardless of which one served
    the data."""
    from app.api.recommendations import recommendation_results
    from app.models.schemas import RecommendationSet, VendorRecommendation
    from datetime import datetime

    if session_id in recommendation_results:
        return recommendation_results[session_id]

    rows = execute("""
        SELECT recommendations FROM recommendation_results
        WHERE session_id = %s ORDER BY generated_at DESC LIMIT 1
    """, (session_id,), fetch=True)
    if not rows:
        return None

    raw_recs = rows[0]["recommendations"] or []
    return RecommendationSet(
        session_id=session_id,
        recommendations=[VendorRecommendation(**r) for r in raw_recs],
        architecture_notes="See executive summary for full architecture recommendation.",
        implementation_roadmap=[],
        generated_at=datetime.utcnow(),
    )


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
    """, (session_id, json.dumps(summary.model_dump() if hasattr(summary, "model_dump") else summary, default=json_default)))

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
