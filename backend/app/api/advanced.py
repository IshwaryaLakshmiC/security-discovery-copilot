from fastapi import APIRouter, HTTPException
from app.engines.objection_engine import ObjectionEngine
from app.engines.architecture_options import ArchitectureOptionsEngine
from app.engines.stakeholder_engine import StakeholderEngine
from app.engines.deal_risk import DealRiskEngine
from app.engines.discovery import DiscoveryEngine
from app.api.gaps import gap_results
from app.api.recommendations import recommendation_results
from app.api.discovery import _load_messages
from app.api.sessions import get_session_or_none

router = APIRouter()

objection_engine = ObjectionEngine()
arch_options_engine = ArchitectureOptionsEngine()
stakeholder_engine = StakeholderEngine()
deal_risk_engine = DealRiskEngine()
discovery_engine = DiscoveryEngine()

# In-memory stores for new outputs
objection_results: dict = {}
arch_options_results: dict = {}
stakeholder_results: dict = {}
deal_risk_results: dict = {}


# ── Objection Handling ────────────────────────────────────────

@router.post("/{session_id}/objections")
async def analyse_objections(session_id: str):
    """Detect constraints from transcript and generate SE responses"""
    messages = _load_messages(session_id)
    gap_analysis = gap_results.get(session_id)
    recs = recommendation_results.get(session_id)

    if not messages:
        raise HTTPException(status_code=404, detail="No discovery transcript found")
    if not gap_analysis:
        raise HTTPException(status_code=400, detail="Run gap analysis first")
    if not recs:
        raise HTTPException(status_code=400, detail="Run recommendations first")

    transcript_text = " ".join([m.content for m in messages])
    result = await objection_engine.analyse(session_id, transcript_text, gap_analysis, recs)
    objection_results[session_id] = result
    return result


@router.get("/{session_id}/objections")
async def get_objections(session_id: str):
    result = objection_results.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No objection analysis found")
    return result


# ── Architecture Options ──────────────────────────────────────

@router.post("/{session_id}/architecture-options")
async def generate_architecture_options(session_id: str):
    """Generate 4 alternative architecture paths with tradeoff analysis"""
    messages = _load_messages(session_id)
    gap_analysis = gap_results.get(session_id)

    if not gap_analysis:
        raise HTTPException(status_code=400, detail="Run gap analysis first")

    entities = await discovery_engine.extract_entities(messages)
    result = await arch_options_engine.generate(session_id, gap_analysis, entities)
    arch_options_results[session_id] = result
    return result


@router.get("/{session_id}/architecture-options")
async def get_architecture_options(session_id: str):
    result = arch_options_results.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No architecture options found")
    return result


# ── Stakeholder Alignment ─────────────────────────────────────

@router.post("/{session_id}/stakeholders")
async def analyse_stakeholders(session_id: str):
    """Generate stakeholder-specific messaging and meeting agendas"""
    session = await get_session_or_none(session_id)
    gap_analysis = gap_results.get(session_id)
    recs = recommendation_results.get(session_id)

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
    return result


@router.get("/{session_id}/stakeholders")
async def get_stakeholders(session_id: str):
    result = stakeholder_results.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No stakeholder analysis found")
    return result


# ── Deal Risk Assessment ──────────────────────────────────────

@router.post("/{session_id}/deal-risk")
async def assess_deal_risk(session_id: str):
    """Full deal risk assessment — technical, adoption, migration, organisational, timeline"""
    messages = _load_messages(session_id)
    gap_analysis = gap_results.get(session_id)

    if not gap_analysis:
        raise HTTPException(status_code=400, detail="Run gap analysis first")

    entities = await discovery_engine.extract_entities(messages)
    objections = objection_results.get(session_id)

    result = await deal_risk_engine.assess(session_id, gap_analysis, entities, objections)
    deal_risk_results[session_id] = result
    return result


@router.get("/{session_id}/deal-risk")
async def get_deal_risk(session_id: str):
    result = deal_risk_results.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No deal risk assessment found")
    return result


# ── Full SE Package (run all engines) ────────────────────────

@router.post("/{session_id}/full-analysis")
async def run_full_analysis(session_id: str):
    """Run all 4 new engines in sequence — returns complete SE package"""
    messages = _load_messages(session_id)
    gap_analysis = gap_results.get(session_id)
    recs = recommendation_results.get(session_id)

    if not messages or not gap_analysis:
        raise HTTPException(status_code=400, detail="Complete discovery and gap analysis first")

    entities = await discovery_engine.extract_entities(messages)
    transcript_text = " ".join([m.content for m in messages])

    # Run all engines
    objections = await objection_engine.analyse(session_id, transcript_text, gap_analysis, recs) if recs else None
    arch_options = await arch_options_engine.generate(session_id, gap_analysis, entities)
    stakeholders = await stakeholder_engine.analyse(session_id, gap_analysis, recs, {}) if recs else None
    deal_risk = await deal_risk_engine.assess(session_id, gap_analysis, entities, objections)

    # Store all
    if objections: objection_results[session_id] = objections
    arch_options_results[session_id] = arch_options
    if stakeholders: stakeholder_results[session_id] = stakeholders
    deal_risk_results[session_id] = deal_risk

    return {
        "session_id": session_id,
        "objections": objections,
        "architecture_options": arch_options,
        "stakeholders": stakeholders,
        "deal_risk": deal_risk,
        "status": "complete"
    }
