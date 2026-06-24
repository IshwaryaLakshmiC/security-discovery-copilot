from fastapi import APIRouter, HTTPException
from app.engines.gap_analysis import run_gap_analysis
from app.engines.discovery import DiscoveryEngine
from app.models.schemas import GapAnalysis
from app.api.discovery import _load_messages
from app.core.database import execute
import json

router = APIRouter()
engine = DiscoveryEngine()

# In-memory cache. RDS (gap_analysis_results table) is the source of truth.
gap_results: dict[str, GapAnalysis] = {}


def _row_to_gap_analysis(row: dict, session_id: str) -> GapAnalysis:
    return GapAnalysis(
        session_id=session_id,
        gaps=row["gaps"],
        maturity_scores=row["maturity_scores"],
        overall_risk_level=row["overall_risk_level"],
        top_3_priorities=row.get("gaps", [])[:3] if isinstance(row.get("gaps"), list) else [],
        compliance_status=row.get("compliance_status") or {},
        generated_at=row["generated_at"],
    )


def get_gap_results_or_none(session_id: str) -> GapAnalysis | None:
    """Reusable lookup with RDS fallback -- importable by recommendations.py
    and executive.py so they never read the raw in-memory dict directly."""
    if session_id in gap_results:
        return gap_results[session_id]

    rows = execute("""
        SELECT gaps, maturity_scores, overall_risk_level, compliance_status, generated_at
        FROM gap_analysis_results WHERE session_id = %s
        ORDER BY generated_at DESC LIMIT 1
    """, (session_id,), fetch=True)

    if not rows:
        return None

    analysis = _row_to_gap_analysis(rows[0], session_id)
    gap_results[session_id] = analysis
    return analysis


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
    result = get_gap_results_or_none(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No gap analysis found. Run /analyse first.")
    return result
