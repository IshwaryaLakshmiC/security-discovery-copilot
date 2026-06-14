"""
Deal Risk Assessment Engine

An SE who only sees technical risk misses the real reasons
implementations fail. This engine surfaces the full risk picture:
technical, adoption, migration, organisational, and timeline.

Design: risk categories and scoring are deterministic.
Mitigation strategy generation is AI-assisted.
"""

import json
from app.core.llm import get_llm_client
from app.models.schemas import GapAnalysis, ExtractedEntities
from app.engines.objection_engine import ObjectionAnalysis
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RiskItem(BaseModel):
    category: str           # technical | adoption | migration | organisational | timeline
    title: str
    description: str
    severity: str           # critical | high | medium | low
    likelihood: str         # high | medium | low
    impact: str             # What happens if this risk materialises
    mitigation: str
    owner: str              # Who needs to own the mitigation
    requires_exec_sponsorship: bool


class DealRiskAssessment(BaseModel):
    session_id: str
    overall_risk_score: int         # 1-10, higher = riskier
    risk_rating: str                # low | medium | high | very-high
    risks: list[RiskItem]
    red_flags: list[str]
    green_flags: list[str]          # Positive signals that de-risk the engagement
    go_no_go_assessment: str        # Honest assessment of whether to proceed
    critical_success_factors: list[str]
    recommended_next_actions: list[str]
    generated_at: datetime


# ── Deterministic risk detection ─────────────────────────────

def detect_risks(
    gap_analysis: GapAnalysis,
    entities: ExtractedEntities,
    objections: Optional[ObjectionAnalysis] = None
) -> list[RiskItem]:
    risks = []

    # Technical risks
    critical_gaps = [g for g in gap_analysis.gaps if g.severity == "critical"]
    if len(critical_gaps) >= 3:
        risks.append(RiskItem(
            category="technical",
            title="Multiple critical security gaps create complex remediation dependency",
            description=f"{len(critical_gaps)} critical gaps identified. Remediating them independently may create conflicts or require specific sequencing.",
            severity="high",
            likelihood="high",
            impact="Implementation stalls due to dependency conflicts. Security posture gets worse before it gets better.",
            mitigation="Define explicit sequencing plan. Address identity foundation (IAM/MFA) before adding overlay controls.",
            owner="Security Architect + Implementation team",
            requires_exec_sponsorship=False
        ))

    # No cloud security tooling + multi-cloud
    if len(entities.cloud_platforms) >= 2 and not any(
        t in entities.security_tools for t in ["wiz", "prisma", "lacework", "orca", "defender"]
    ):
        risks.append(RiskItem(
            category="technical",
            title="Multi-cloud environment without unified security visibility",
            description=f"Operating across {', '.join(entities.cloud_platforms)} without a CSPM creates blind spots that compound across clouds.",
            severity="high",
            likelihood="high",
            impact="Security gaps in one cloud go undetected. Compliance reporting requires manual reconciliation across platforms.",
            mitigation="Deploy agentless CSPM (Wiz or Prisma Cloud) as a first step — provides visibility without disrupting workloads.",
            owner="Cloud Infrastructure Team",
            requires_exec_sponsorship=False
        ))

    # Adoption risks
    if entities.employee_count and entities.employee_count > 1000:
        risks.append(RiskItem(
            category="adoption",
            title="Large user base creates significant change management risk",
            description=f"Rolling out identity changes to {entities.employee_count}+ users without structured change management typically results in 20-40% adoption failure.",
            severity="medium",
            likelihood="medium",
            impact="Low MFA adoption, helpdesk ticket surge, executive pressure to rollback.",
            mitigation="Pilot with 50-100 users first. Build internal champions. Communicate 'what's in it for me' to end users (fewer passwords, faster login).",
            owner="IT + HR + Communications",
            requires_exec_sponsorship=True
        ))

    # Migration risks
    if any("migration" in g.lower() or "legacy" in g.lower() for g in entities.raw_gaps):
        risks.append(RiskItem(
            category="migration",
            title="Legacy system dependency creates migration complexity",
            description="Legacy systems in scope increase integration complexity and testing requirements significantly.",
            severity="high",
            likelihood="medium",
            impact="Timeline extends 2-3x original estimate. Budget overrun. Integration failures cause production incidents.",
            mitigation="Scope legacy systems explicitly. Allocate 30% buffer on timeline. Consider identity bridge/proxy pattern before full migration.",
            owner="Infrastructure Team + Vendor Professional Services",
            requires_exec_sponsorship=False
        ))

    # Organisational risks from objections
    if objections:
        blocking = [c for c in objections.detected_constraints if c.severity == "blocking"]
        if blocking:
            risks.append(RiskItem(
                category="organisational",
                title=f"Blocking constraint: {blocking[0].type.replace('_', ' ')}",
                description=f"A blocking constraint ({blocking[0].type}) was identified in discovery that prevents standard approach.",
                severity="critical",
                likelihood="high",
                impact="Project cannot proceed as designed. Architecture must be fundamentally adjusted or project paused.",
                mitigation="Escalate to executive sponsor. Adjust architecture to work within constraint. See objection analysis for specific response.",
                owner="Executive Sponsor + Account Team",
                requires_exec_sponsorship=True
            ))

        political = [c for c in objections.detected_constraints if c.category == "political"]
        if political:
            risks.append(RiskItem(
                category="organisational",
                title="Internal political resistance identified",
                description="Discovery revealed internal resistance that could derail implementation regardless of technical success.",
                severity="high",
                likelihood="medium",
                impact="Project gets deprioritised, budget reallocated, or cancelled after partial implementation.",
                mitigation="Map internal champions and detractors. Build coalition with CISO sponsorship. Address detractor concerns directly in design.",
                owner="CISO + Account Executive",
                requires_exec_sponsorship=True
            ))

    # Timeline risks
    compliance_urgent = any(
        r in entities.compliance_requirements for r in ["soc2", "hipaa", "pci"]
    )
    if compliance_urgent:
        risks.append(RiskItem(
            category="timeline",
            title="Compliance deadline creates timeline pressure",
            description=f"Active compliance requirements ({', '.join(entities.compliance_requirements)}) create external timeline pressure that may not align with realistic implementation schedule.",
            severity="high",
            likelihood="medium",
            impact="Audit finding, compliance failure, potential fine or loss of certification.",
            mitigation="Prioritise controls required for compliance first. Accept higher initial cost to meet deadline. Plan improvement roadmap post-audit.",
            owner="CISO + Compliance Team",
            requires_exec_sponsorship=True
        ))

    return risks


def score_overall_risk(risks: list[RiskItem]) -> tuple[int, str]:
    score = 0
    for r in risks:
        if r.severity == "critical": score += 3
        elif r.severity == "high": score += 2
        elif r.severity == "medium": score += 1
    # Cap at 10
    score = min(10, score)
    if score >= 8: rating = "very-high"
    elif score >= 6: rating = "high"
    elif score >= 4: rating = "medium"
    else: rating = "low"
    return score, rating


class DealRiskEngine:

    def __init__(self):
        self.llm = get_llm_client()

    async def assess(
        self,
        session_id: str,
        gap_analysis: GapAnalysis,
        entities: ExtractedEntities,
        objections: Optional[ObjectionAnalysis] = None
    ) -> DealRiskAssessment:

        risks = detect_risks(gap_analysis, entities, objections)
        score, rating = score_overall_risk(risks)

        # Red flags
        red_flags = []
        exec_sponsor_needed = [r for r in risks if r.requires_exec_sponsorship]
        if exec_sponsor_needed:
            red_flags.append(f"{len(exec_sponsor_needed)} risk(s) require executive sponsorship — confirm champion exists before proceeding")
        if score >= 7:
            red_flags.append("High overall risk score — recommend a structured POC before full commitment")
        if objections and any(c.severity == "blocking" for c in objections.detected_constraints):
            red_flags.append("Blocking constraint present — architecture adjustment required before scoping")

        # Green flags
        green_flags = []
        if entities.identity_tools:
            green_flags.append(f"Existing identity tooling ({', '.join(entities.identity_tools)}) reduces greenfield complexity")
        if entities.compliance_requirements:
            green_flags.append("Active compliance requirement creates executive urgency and budget justification")
        if entities.cloud_platforms:
            green_flags.append("Cloud-first environment reduces legacy migration complexity")
        if score <= 4:
            green_flags.append("Risk profile is manageable — standard implementation approach is viable")

        # Success factors
        critical_success_factors = [
            "Executive sponsor identified and committed at CISO or CIO level",
            "Clear sequencing plan for gap remediation agreed upfront",
            "Change management plan for end-user adoption",
            "Defined success metrics and measurement approach before go-live",
            "Rollback plan tested before production cutover"
        ]

        next_actions = [
            "Confirm executive sponsor and schedule kickoff",
            "Define POC scope and success criteria (recommend 30-day POC before full commitment)",
            "Map integration points with existing tools and test in staging environment",
            "Establish change management and communication plan with HR/IT",
            "Define compliance evidence requirements and map to implementation milestones"
        ]

        # Go/no-go
        if score >= 8:
            go_no_go = "HIGH RISK — recommend pausing to resolve blocking constraints before proceeding. A poorly executed implementation will be harder to recover from than a delayed start."
        elif score >= 6:
            go_no_go = "PROCEED WITH CAUTION — significant risks present. Recommend a structured POC with defined exit criteria before full commitment. Executive sponsorship is non-negotiable."
        elif score >= 4:
            go_no_go = "PROCEED — manageable risk level with standard mitigation. Run a 30-day pilot before full rollout."
        else:
            go_no_go = "PROCEED — risk profile is favourable. Standard implementation approach is appropriate."

        return DealRiskAssessment(
            session_id=session_id,
            overall_risk_score=score,
            risk_rating=rating,
            risks=risks,
            red_flags=red_flags,
            green_flags=green_flags,
            go_no_go_assessment=go_no_go,
            critical_success_factors=critical_success_factors,
            recommended_next_actions=next_actions,
            generated_at=datetime.utcnow()
        )
