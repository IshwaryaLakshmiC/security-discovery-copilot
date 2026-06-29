from fastapi import APIRouter, HTTPException
from app.engines.gap_analysis import run_gap_analysis
from app.engines.discovery import DiscoveryEngine
from app.models.schemas import GapAnalysis
from app.api.discovery import _load_messages
from app.core.database import execute
from app.core.json_utils import json_default
import json

router = APIRouter()
engine = DiscoveryEngine()

# In-memory cache. RDS (gap_analysis_results table) is the source of truth.
gap_results: dict[str, GapAnalysis] = {}


def _row_to_gap_analysis(row: dict, session_id: str) -> GapAnalysis:
    """Rebuild a GapAnalysis from an RDS row. The 'gaps' column stores the
    full gap objects as JSONB; top_3_priorities needs to be a list of gap
    ID STRINGS, not the objects themselves -- this bug was invisible until
    today because every prior test happened to hit the in-memory cache
    (same process, never restarted between gap analysis and downstream
    calls), where the original GapAnalysis object already had
    top_3_priorities computed correctly by run_gap_analysis(). The moment
    a restart forced this RDS-reload path to run for the first time, the
    bug surfaced as a Pydantic validation error (dicts where strings were
    expected)."""
    gaps_list = row.get("gaps") or []

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    effort_order = {"low": 0, "medium": 1, "high": 2}

    sorted_gaps = sorted(
        gaps_list,
        key=lambda g: (
            severity_order.get(g.get("severity"), 99),
            effort_order.get(g.get("remediation_effort"), 99),
        ),
    )
    top_3 = [g["id"] for g in sorted_gaps[:3] if "id" in g]

    return GapAnalysis(
        session_id=session_id,
        gaps=gaps_list,
        maturity_scores=row["maturity_scores"],
        overall_risk_level=row["overall_risk_level"],
        top_3_priorities=top_3,
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
        json.dumps([g.model_dump() if hasattr(g, "model_dump") else g for g in analysis.gaps], default=json_default),
        json.dumps({k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in analysis.maturity_scores.items()}, default=json_default),
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
