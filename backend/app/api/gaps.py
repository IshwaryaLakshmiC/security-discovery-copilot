from fastapi import APIRouter, HTTPException
from app.engines.gap_analysis import run_gap_analysis
from app.engines.discovery import DiscoveryEngine
from app.api.discovery import session_messages

router = APIRouter()
engine = DiscoveryEngine()

gap_results: dict[str, any] = {}


@router.post("/{session_id}/analyse")
async def analyse_gaps(session_id: str):
    """Run gap analysis on completed discovery transcript"""
    messages = session_messages.get(session_id, [])
    if not messages:
        raise HTTPException(status_code=404, detail="No discovery transcript found")

    # Extract entities from transcript
    entities = await engine.extract_entities(messages)

    # Run deterministic gap analysis
    analysis = run_gap_analysis(entities, session_id)
    gap_results[session_id] = analysis

    return analysis


@router.get("/{session_id}")
async def get_gap_analysis(session_id: str):
    """Get existing gap analysis for a session"""
    result = gap_results.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No gap analysis found. Run /analyse first.")
    return result
