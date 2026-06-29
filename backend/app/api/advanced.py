from fastapi import APIRouter, HTTPException
from app.engines.objection_engine import ObjectionEngine
from app.engines.architecture_options import ArchitectureOptionsEngine
from app.engines.stakeholder_engine import StakeholderEngine
from app.engines.deal_risk import DealRiskEngine
from app.engines.discovery import DiscoveryEngine
from app.api.gaps import get_gap_results_or_none
from app.api.recommendations import get_recommendations as _get_recs_route
from app.api.discovery import _load_messages
from app.api.sessions import get_session_or_none
from app.core.database import execute
from app.core.json_utils import json_default
import json

router = APIRouter()

objection_engine = ObjectionEngine()
arch_options_engine = ArchitectureOptionsEngine()
stakeholder_engine = StakeholderEngine()
deal_risk_engine = DealRiskEngine()
discovery_engine = DiscoveryEngine()

# In-memory cache. RDS (advanced_analysis table) is the source of truth,
# discriminated by analysis_type. Every store/load below mirrors the
# pattern already proven in sessions.py / discovery.py / gaps.py.
objection_results: dict = {}
arch_options_results: dict = {}
stakeholder_results: dict = {}
deal_risk_results: dict = {}


def _save(session_id: str, analysis_type: str, result) -> None:
    payload = result.model_dump() if hasattr(result, "model_dump") else result
    execute("""
        INSERT INTO advanced_analysis (session_id, analysis_type, result, generated_at)
        VALUES (%s, %s, %s, NOW())
    """, (session_id, analysis_type, json.dumps(payload, default=json_default)))


def _load(session_id: str, analysis_type: str, cache: dict):
    if session_id in cache:
        return cache[session_id]

    rows = execute("""
        SELECT result FROM advanced_analysis
        WHERE session_id = %s AND analysis_type = %s
        ORDER BY generated_at DESC LIMIT 1
    """, (session_id, analysis_type), fetch=True)

    if not rows:
        return None

    cache[session_id] = rows[0]["result"]
    return cache[session_id]


async def _get_recs_or_none(session_id: str):
    """recommendations.py has no importable loader of its own yet (it returns
    a FastAPI route response directly) -- read via the same cache/RDS pattern
    used everywhere else instead of calling the route function directly.

    Same restart-dependent shape bug found in executive.py's copy of this
    function: the RDS column stores a plain list of dicts, but
    objection_engine and stakeholder_engine both expect a RecommendationSet
    object with a .recommendations attribute. Wrap the raw list back into
    a RecommendationSet so both the in-memory and RDS paths return an
    identical shape."""
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


# ── Objection Handling ────────────────────────────────────────

@router.post("/{session_id}/objections")
async def analyse_objections(session_id: str):
    """Detect constraints from transcript and generate SE responses"""
    messages = _load_messages(session_id)
    gap_analysis = get_gap_results_or_none(session_id)
    recs = await _get_recs_or_none(session_id)

    if not messages:
        raise HTTPException(status_code=404, detail="No discovery transcript found")
    if not gap_analysis:
        raise HTTPException(status_code=400, detail="Run gap analysis first")
    if not recs:
        raise HTTPException(status_code=400, detail="Run recommendations first")

    transcript_text = " ".join([m.content for m in messages])
    result = await objection_engine.analyse(session_id, transcript_text, gap_analysis, recs)
    objection_results[session_id] = result
    _save(session_id, "objections", result)
    return result


@router.get("/{session_id}/objections")
async def get_objections(session_id: str):
    result = _load(session_id, "objections", objection_results)
    if not result:
        raise HTTPException(status_code=404, detail="No objection analysis found")
    return result


# ── Architecture Options ──────────────────────────────────────

@router.post("/{session_id}/architecture-options")
async def generate_architecture_options(session_id: str):
    """Generate 4 alternative architecture paths with tradeoff analysis"""
    messages = _load_messages(session_id)
    gap_analysis = get_gap_results_or_none(session_id)

    if not gap_analysis:
        raise HTTPException(status_code=400, detail="Run gap analysis first")

    entities = await discovery_engine.extract_entities(messages)
    result = await arch_options_engine.generate(session_id, gap_analysis, entities)
    arch_options_results[session_id] = result
    _save(session_id, "arch_options", result)
    return result


@router.get("/{session_id}/architecture-options")
async def get_architecture_options(session_id: str):
    result = _load(session_id, "arch_options", arch_options_results)
    if not result:
        raise HTTPException(status_code=404, detail="No architecture options found")
    return result


# ── Stakeholder Alignment ─────────────────────────────────────

@router.post("/{session_id}/stakeholders")
async def analyse_stakeholders(session_id: str):
    """Generate stakeholder-specific messaging and meeting agendas"""
    session = await get_session_or_none(session_id)
    gap_analysis = get_gap_results_or_none(session_id)
    recs = await _get_recs_or_none(session_id)

    if not gap_analysis:
        raise HTTPException(status_code=400, detail="Run gap analysis first")
    if not recs:
        raise HTTPException(status_code=400, detail="Run recommendations first")

    company_context = {
        "company_name": session.company_name if session else "Prospect",
        "industry": session.industry if session else None,
        "company_size": session.company_size if session else None
    }

    result = await stakeholder_engine.analyse(session_id, gap_analysis, recs, company_context)
    stakeholder_results[session_id] = result
    _save(session_id, "stakeholders", result)
    return result


@router.get("/{session_id}/stakeholders")
async def get_stakeholders(session_id: str):
    result = _load(session_id, "stakeholders", stakeholder_results)
    if not result:
        raise HTTPException(status_code=404, detail="No stakeholder analysis found")
    return result


# ── Deal Risk Assessment ──────────────────────────────────────

@router.post("/{session_id}/deal-risk")
async def assess_deal_risk(session_id: str):
    """Full deal risk assessment -- technical, adoption, migration, organisational, timeline"""
    messages = _load_messages(session_id)
    gap_analysis = get_gap_results_or_none(session_id)

    if not gap_analysis:
        raise HTTPException(status_code=400, detail="Run gap analysis first")

    entities = await discovery_engine.extract_entities(messages)
    objections = _load(session_id, "objections", objection_results)

    result = await deal_risk_engine.assess(session_id, gap_analysis, entities, objections)
    deal_risk_results[session_id] = result
    _save(session_id, "deal_risk", result)
    return result


@router.get("/{session_id}/deal-risk")
async def get_deal_risk(session_id: str):
    result = _load(session_id, "deal_risk", deal_risk_results)
    if not result:
        raise HTTPException(status_code=404, detail="No deal risk assessment found")
    return result


# ── Full SE Package (run all engines) ────────────────────────

@router.post("/{session_id}/full-analysis")
async def run_full_analysis(session_id: str):
    """Run all 4 engines in sequence -- returns complete SE package"""
    messages = _load_messages(session_id)
    gap_analysis = get_gap_results_or_none(session_id)
    recs = await _get_recs_or_none(session_id)

    if not messages or not gap_analysis:
        raise HTTPException(status_code=400, detail="Complete discovery and gap analysis first")

    entities = await discovery_engine.extract_entities(messages)
    transcript_text = " ".join([m.content for m in messages])

    objections = await objection_engine.analyse(session_id, transcript_text, gap_analysis, recs) if recs else None
    arch_options = await arch_options_engine.generate(session_id, gap_analysis, entities)
    stakeholders = await stakeholder_engine.analyse(session_id, gap_analysis, recs, {}) if recs else None
    deal_risk = await deal_risk_engine.assess(session_id, gap_analysis, entities, objections)

    if objections:
        objection_results[session_id] = objections
        _save(session_id, "objections", objections)
    arch_options_results[session_id] = arch_options
    _save(session_id, "arch_options", arch_options)
    if stakeholders:
        stakeholder_results[session_id] = stakeholders
        _save(session_id, "stakeholders", stakeholders)
    deal_risk_results[session_id] = deal_risk
    _save(session_id, "deal_risk", deal_risk)

    return {
        "session_id": session_id,
        "objections": objections,
        "architecture_options": arch_options,
        "stakeholders": stakeholders,
        "deal_risk": deal_risk,
        "status": "complete"
    }
