from fastapi import APIRouter, HTTPException
from app.engines.gap_analysis import run_gap_analysis
from app.engines.discovery import DiscoveryEngine
from app.api.discovery import _load_messages
from app.core.database import execute
import json

router = APIRouter()
engine = DiscoveryEngine()

# In-memory cache. RDS (gap_analysis_results table) is the source of truth.
gap_results: dict[str, any] = {}


@router.post("/{session_id}/analyse")
async def analyse_gaps(session_id: str):
    """Run gap analysis on completed discovery transcript"""
    messages = _load_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="No discovery transcript found")

    entities = await engine.extract_entities(messages)
    analysis = run_gap_analysis(entities, session_id)
    gap_results[session_id] = analysis

    execute("""
        INSERT INTO gap_analysis_results (session_id, gaps, maturity_scores, overall_risk_level, compliance_status, generated_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
    """, (
        session_id,
        json.dumps([g.model_dump() if hasattr(g, "model_dump") else g for g in analysis.gaps]),
        json.dumps({k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in analysis.maturity_scores.items()}),
        analysis.overall_risk_level,
        json.dumps(analysis.compliance_status),
    ))

    return analysis


@router.get("/{session_id}")
async def get_gap_analysis(session_id: str):
    """Get existing gap analysis for a session"""
    if session_id in gap_results:
        return gap_results[session_id]

    rows = execute("""
        SELECT gaps, maturity_scores, overall_risk_level, compliance_status, generated_at
        FROM gap_analysis_results WHERE session_id = %s
        ORDER BY generated_at DESC LIMIT 1
    """, (session_id,), fetch=True)

    if not rows:
        raise HTTPException(status_code=404, detail="No gap analysis found. Run /analyse first.")

    return rows[0]
