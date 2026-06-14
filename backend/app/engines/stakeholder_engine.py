"""
Stakeholder Alignment Engine

Enterprise deals die because the right message reaches the wrong person,
or the wrong message reaches the right person.

A senior SE knows how to tailor the conversation to each stakeholder.
This engine maps the security architecture to stakeholder concerns.

Design: stakeholder priorities are deterministic. Messaging is AI-generated
but constrained by the deterministic priority model.
"""

import json
from app.core.llm import get_llm_client
from app.models.schemas import GapAnalysis, RecommendationSet
from pydantic import BaseModel
from typing import Optional


class StakeholderProfile(BaseModel):
    role: str
    primary_concern: str
    secondary_concern: str
    success_metric: str
    likely_objection: str
    message_frame: str          # How to frame security for this person
    avoid: str                  # What NOT to say to this person


class StakeholderBrief(BaseModel):
    role: str
    profile: StakeholderProfile
    key_message: str            # The ONE thing to communicate to this stakeholder
    supporting_points: list[str]
    likely_objection: str
    objection_response: str
    recommended_content: str    # What to send them (exec summary, technical doc, ROI model, etc.)
    meeting_agenda: list[str]   # Suggested agenda for a 30-min stakeholder meeting


class StakeholderAnalysis(BaseModel):
    session_id: str
    stakeholders: list[StakeholderBrief]
    critical_path: str          # Which stakeholder is the biggest blocker
    recommended_sequence: str   # Who to engage first, second, third
    coalition_strategy: str     # How to build internal champions


# ── Deterministic stakeholder priority model ──────────────────

STAKEHOLDER_PROFILES = {
    "ciso": StakeholderProfile(
        role="CISO",
        primary_concern="Risk reduction and board-level defensibility",
        secondary_concern="Compliance posture and audit readiness",
        success_metric="Measurable reduction in attack surface and mean time to detect/respond",
        likely_objection="We've heard these promises before — what's different this time?",
        message_frame="Business risk in dollar terms. What is the cost of NOT acting? Board-level risk language.",
        avoid="Feature lists, technical specifications, product demos without business context"
    ),
    "cio": StakeholderProfile(
        role="CIO",
        primary_concern="Business enablement and technology strategy alignment",
        secondary_concern="IT operational efficiency and budget optimisation",
        success_metric="Security that enables the business rather than slows it down",
        likely_objection="How does this fit into our existing technology roadmap and investments?",
        message_frame="How security becomes a business accelerator. Productivity impact of SSO, reduced helpdesk tickets from password resets.",
        avoid="Threat landscape statistics, CVE counts, technical risk — speak business outcomes"
    ),
    "security_architect": StakeholderProfile(
        role="Security Architect",
        primary_concern="Technical correctness and architecture integrity",
        secondary_concern="Integration complexity and maintenance burden",
        success_metric="Clean architecture that can be maintained and evolved",
        likely_objection="We evaluated this 18 months ago and the integration with X was a nightmare.",
        message_frame="Reference architectures, integration patterns, technical depth. Show you understand the plumbing.",
        avoid="Marketing language, vague claims, anything that oversimplifies the technical reality"
    ),
    "iam_team": StakeholderProfile(
        role="IAM Team",
        primary_concern="Operational manageability and day-to-day workflow impact",
        secondary_concern="Learning curve and disruption to existing processes",
        success_metric="Can we manage this with our current team without burning out?",
        likely_objection="We already have X tool — why are we adding another one to manage?",
        message_frame="Operational efficiency, automation reducing manual work, what they stop having to do.",
        avoid="Anything that implies more work for them without explaining what gets automated away"
    ),
    "infrastructure_team": StakeholderProfile(
        role="Infrastructure Team",
        primary_concern="System stability, performance, and deployment complexity",
        secondary_concern="Impact on existing CI/CD pipelines and cloud infrastructure",
        success_metric="No production incidents caused by security tool deployment",
        likely_objection="Last time we deployed a security agent, it caused a 15-minute outage.",
        message_frame="Agentless where possible, phased rollout, rollback capability, SLA commitments.",
        avoid="Dismissing their past negative experiences, underselling deployment complexity"
    ),
    "procurement": StakeholderProfile(
        role="Procurement",
        primary_concern="Contract terms, commercial risk, and vendor viability",
        secondary_concern="Total cost of ownership and exit clauses",
        success_metric="Favourable commercial terms with acceptable risk transfer",
        likely_objection="The price is too high and the contract terms are not flexible.",
        message_frame="Multi-year pricing, ROI documentation, vendor financial stability, reference customers.",
        avoid="Technical features, security outcomes — they don't evaluate on these"
    ),
    "finance": StakeholderProfile(
        role="Finance / CFO",
        primary_concern="Cost justification and budget impact",
        secondary_concern="Risk quantification in financial terms",
        success_metric="Approved budget with clear ROI within acceptable payback period",
        likely_objection="Security is a cost centre. What's the ROI?",
        message_frame="Cost of a breach vs cost of prevention. Cyber insurance premium reduction. Productivity gains from reduced friction.",
        avoid="Technical risk language, CVSS scores, feature comparisons — translate everything to dollars"
    )
}


STAKEHOLDER_PROMPT = """You are a Principal Solutions Engineer preparing stakeholder briefing materials for an enterprise security deal.

You have been given the customer's security gap analysis and recommended solutions.

For each stakeholder, generate:
1. The single most important message for this person
2. 3 supporting points that resonate with their priorities
3. Their most likely objection and how to respond
4. What content to send them
5. A suggested 30-minute meeting agenda

Tone: Sound like a genuinely experienced SE who has had these conversations hundreds of times.
Do NOT be generic. Reference the specific gaps and recommendations in your messaging.

Return ONLY valid JSON array."""


class StakeholderEngine:

    def __init__(self):
        self.llm = get_llm_client()

    async def analyse(
        self,
        session_id: str,
        gap_analysis: GapAnalysis,
        recommendations: RecommendationSet,
        company_context: dict = None
    ) -> StakeholderAnalysis:

        # Determine which stakeholders are most relevant
        relevant_stakeholders = list(STAKEHOLDER_PROFILES.keys())

        # Filter based on gaps — if no PAM gaps, IAM team less critical
        if not any(g.domain.value in ["pam", "governance"] for g in gap_analysis.gaps):
            relevant_stakeholders = [s for s in relevant_stakeholders if s != "iam_team"]

        gaps_summary = [
            {"title": g.title, "severity": g.severity, "business_impact": g.business_impact}
            for g in gap_analysis.gaps[:5]
        ]

        vendors_summary = [
            {"vendor": r.vendor, "why_fits": r.why_it_fits[:150]}
            for r in recommendations.recommendations[:4]
        ]

        stakeholder_profiles_context = {
            role: {
                "primary_concern": profile.primary_concern,
                "message_frame": profile.message_frame,
                "likely_objection": profile.likely_objection,
                "avoid": profile.avoid
            }
            for role, profile in STAKEHOLDER_PROFILES.items()
            if role in relevant_stakeholders
        }

        messages = [{
            "role": "user",
            "content": f"""Generate stakeholder briefs for this security engagement.

Top security gaps:
{json.dumps(gaps_summary, indent=2)}

Recommended vendors/solutions:
{json.dumps(vendors_summary, indent=2)}

Stakeholder profiles and priorities:
{json.dumps(stakeholder_profiles_context, indent=2)}

Company context: {json.dumps(company_context or {}, indent=2)}

For each stakeholder, return:
{{
  "role": "CISO",
  "key_message": "The single most important thing — specific to THIS customer's gaps",
  "supporting_points": ["point 1", "point 2", "point 3"],
  "likely_objection": "Their most likely objection given this context",
  "objection_response": "How a senior SE would respond",
  "recommended_content": "What to send them — exec summary | ROI model | technical architecture | reference customer",
  "meeting_agenda": ["Agenda item 1 (5 min)", "Agenda item 2 (15 min)", "Agenda item 3 (10 min)"]
}}"""
        }]

        response = await self.llm.complete(STAKEHOLDER_PROMPT, messages, max_tokens=3000)

        try:
            cleaned = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            briefs_data = data if isinstance(data, list) else data.get("stakeholders", [])

            briefs = []
            for item in briefs_data:
                role_key = item["role"].lower().replace(" ", "_").replace("/", "_")
                profile = STAKEHOLDER_PROFILES.get(role_key, STAKEHOLDER_PROFILES["ciso"])

                briefs.append(StakeholderBrief(
                    role=item["role"],
                    profile=profile,
                    key_message=item.get("key_message", ""),
                    supporting_points=item.get("supporting_points", []),
                    likely_objection=item.get("likely_objection", profile.likely_objection),
                    objection_response=item.get("objection_response", ""),
                    recommended_content=item.get("recommended_content", "Executive summary"),
                    meeting_agenda=item.get("meeting_agenda", [])
                ))

            # Determine critical path stakeholder
            has_budget_concern = any(g.severity in ["critical", "high"] for g in gap_analysis.gaps)
            critical_path = "CISO" if has_budget_concern else "CIO"

            return StakeholderAnalysis(
                session_id=session_id,
                stakeholders=briefs,
                critical_path=f"{critical_path} is the critical path stakeholder — without their sponsorship, other stakeholders will not commit.",
                recommended_sequence="Start with CISO to establish risk context → CIO for business alignment → Security Architect for technical validation → IAM team for operational buy-in → Procurement for commercial terms",
                coalition_strategy="Build a champion at the CISO or CIO level before engaging procurement. Technical champions (Security Architect, IAM team) become your internal advocates once the business case is established."
            )

        except Exception as e:
            print(f"Stakeholder analysis parse error: {e}")
            raise ValueError(f"Stakeholder analysis failed: {e}")
