"""
Objection & Constraint Handling Engine

This is what separates junior SEs from senior SEs.
Enterprise customers always have constraints. The SE's job
is to navigate them — not ignore them.

Design principle: constraint detection is deterministic.
Response strategy is AI-assisted but grounded in real SE playbooks.
"""

import json
from app.core.llm import get_llm_client
from app.models.schemas import GapAnalysis, RecommendationSet
from pydantic import BaseModel
from typing import Optional


class Constraint(BaseModel):
    type: str
    detected_text: str
    severity: str           # blocking | significant | manageable
    category: str           # investment | team | budget | compliance | political | contract | risk


class ObjectionResponse(BaseModel):
    constraint: Constraint
    acknowledgement: str    # How an SE would acknowledge this without dismissing it
    reframe: str            # How to reframe the constraint as a solvable problem
    adjusted_approach: str  # Specific architecture/recommendation adjustment
    tradeoffs: list[str]    # What the customer gives up vs gains
    questions_to_ask: list[str]  # Follow-up discovery to qualify the constraint
    vendor_specific_response: Optional[str] = None  # If constraint involves a specific vendor


class ObjectionAnalysis(BaseModel):
    session_id: str
    detected_constraints: list[Constraint]
    responses: list[ObjectionResponse]
    overall_strategy: str   # How to approach this engagement given all constraints
    red_flags: list[str]    # Constraints that suggest the deal or project may fail


# ── Constraint detection library (deterministic) ──────────────
# Pattern matching against known enterprise constraint types

CONSTRAINT_PATTERNS = {
    "microsoft_e5": {
        "patterns": ["microsoft e5", "e5 license", "microsoft 365", "m365 e5", "already have microsoft", "azure ad", "entra id"],
        "category": "investment",
        "severity": "significant",
        "implication": "Customer has Entra ID included in E5. Will question ROI of Okta/separate IdP."
    },
    "existing_okta": {
        "patterns": ["already have okta", "okta deployed", "okta contract", "okta renewal"],
        "category": "investment",
        "severity": "manageable",
        "implication": "Okta already present — opportunity to expand (IGA, PAM, Device Trust) rather than replace."
    },
    "small_team": {
        "patterns": ["small team", "one person", "two person", "no dedicated", "part time", "no security team", "understaffed", "resource constrained"],
        "category": "team",
        "severity": "significant",
        "implication": "Operational overhead is a critical buying criterion. SaaS with low admin burden wins."
    },
    "budget_constraint": {
        "patterns": ["budget", "cost", "expensive", "can't afford", "limited budget", "no budget", "cost reduction", "cheaper alternative"],
        "category": "budget",
        "severity": "significant",
        "implication": "Must lead with ROI and risk-reduction framing. Consider phased approach or starter tier."
    },
    "existing_contract": {
        "patterns": ["contract", "locked in", "renewal", "3 year", "5 year", "just renewed", "vendor lock"],
        "category": "contract",
        "severity": "blocking",
        "implication": "Cannot displace incumbent until renewal window. Focus on co-existence or expansion."
    },
    "migration_risk": {
        "patterns": ["migration risk", "disruption", "can't afford downtime", "production system", "business critical", "no outage window", "risk averse"],
        "category": "risk",
        "severity": "significant",
        "implication": "Phased migration with parallel-run period. Rollback plan required. POC before full deployment."
    },
    "compliance_constraint": {
        "patterns": ["gdpr", "data residency", "data sovereignty", "must stay in", "eu data", "fips", "fedramp", "government cloud"],
        "category": "compliance",
        "severity": "blocking",
        "implication": "Vendor must have compliant deployment option. Check certifications before recommending."
    },
    "political_resistance": {
        "patterns": ["pushback", "resistance", "politics", "internal opposition", "not convinced", "skeptical", "board won't approve", "ceo said no", "not a priority"],
        "category": "political",
        "severity": "significant",
        "implication": "Executive sponsor required. Focus on business risk framing, not technical features."
    },
    "legacy_infrastructure": {
        "patterns": ["legacy", "on-premises", "on-prem", "mainframe", "cobol", "20 year old", "cannot migrate", "hybrid forever"],
        "category": "risk",
        "severity": "significant",
        "implication": "Hybrid architecture required. Identity bridge or proxy approach for legacy systems."
    },
    "no_mfa_appetite": {
        "patterns": ["users won't accept", "user friction", "employees complain", "adoption problem", "change management", "culture"],
        "category": "political",
        "severity": "manageable",
        "implication": "Phased MFA rollout with SSO-first to reduce password fatigue. Show UX improvements."
    }
}

# ── SE playbooks per constraint type ─────────────────────────
CONSTRAINT_PLAYBOOKS = {
    "microsoft_e5": {
        "acknowledgement": "Understood — E5 includes Entra ID which covers core SSO and MFA. That's a significant existing investment worth maximising.",
        "reframe": "The question isn't Entra ID vs Okta — it's whether Entra ID alone covers your full identity surface. E5 doesn't include IGA, PAM, or cross-cloud federation at the depth enterprises typically need as they scale.",
        "questions": [
            "What percentage of your applications are native Azure/M365 vs third-party SaaS?",
            "How are you handling provisioning and deprovisioning for non-Microsoft apps today?",
            "Do you have a Privileged Identity Management use case beyond Azure resources?",
            "Is there an AWS or GCP footprint where Entra ID integration is limited?"
        ],
        "tradeoffs": [
            "Staying E5-only: simpler licensing, single vendor, lower cost — but limited SCIM to non-MS apps, weaker IGA, no PAM",
            "Entra ID + Okta: best-of-breed for multi-cloud, stronger third-party app coverage — higher cost, two IdP complexity",
            "Entra ID + SailPoint: strong IGA on top of existing investment — adds governance without replacing IdP"
        ]
    },
    "small_team": {
        "acknowledgement": "A small team changes the operational requirements significantly — any recommendation needs to be manageable by the team you have, not the team you wish you had.",
        "reframe": "This is actually a vendor selection criterion, not a blocker. We should weight operational overhead heavily in the evaluation. SaaS-first, low-admin-burden tools win here.",
        "questions": [
            "How many hours per week does your team currently spend on identity-related tasks?",
            "What's your on-call rotation and incident response capacity?",
            "Do you have a managed service or MSSP relationship that could augment?",
            "What's the acceptable learning curve for a new tool?"
        ],
        "tradeoffs": [
            "Best security vs manageable security: enterprise PAM is powerful but needs a team to run it",
            "SaaS-delivered tools (Wiz, Cloudflare Zero Trust) vs on-prem — significantly lower operational overhead",
            "Automation-first architecture reduces ongoing team burden at the cost of upfront implementation time"
        ]
    },
    "budget_constraint": {
        "acknowledgement": "Budget is always a real constraint and it shapes what's achievable in what timeframe. Let's work within it rather than around it.",
        "reframe": "The question is what risk is being accepted by not spending — and whether that risk is quantifiable. A single breach often costs more than multiple years of security tooling.",
        "questions": [
            "Is there a specific budget number or is it more about prioritisation?",
            "Is this a capex vs opex conversation — could subscription licensing change the equation?",
            "What's the cost of a security incident in your industry — have you modelled breach cost?",
            "Are there existing tools that can be decommissioned to fund new capabilities?"
        ],
        "tradeoffs": [
            "Free/open-source tools: lower cost, higher operational overhead, less enterprise support",
            "Phased investment: address critical gaps now, defer lower-severity items to next fiscal year",
            "Vendor consolidation: fewer vendors at better pricing vs best-of-breed at higher cost"
        ]
    },
    "existing_contract": {
        "acknowledgement": "Contract terms are a real constraint — there's no point recommending a displacement if you're locked in for two more years.",
        "reframe": "This engagement becomes about planning the future state and building the business case for the renewal decision, not an immediate replacement.",
        "questions": [
            "When does the current contract expire?",
            "What's your satisfaction with the current vendor — are there pain points driving this conversation?",
            "Is there flexibility to add capabilities while keeping the core contract?",
            "Who owns the vendor relationship — procurement, IT, or the business?"
        ],
        "tradeoffs": [
            "Stay and optimise: reduce risk, no disruption — miss opportunity to address architectural gaps",
            "Plan now, switch at renewal: proper time to evaluate, build business case, pilot — requires 12-18 month planning horizon",
            "Layer on top: add capability alongside existing vendor — costs more but de-risks the transition"
        ]
    },
    "migration_risk": {
        "acknowledgement": "Migration risk on production identity systems is legitimate — a failed identity migration can lock users out of everything.",
        "reframe": "The risk isn't binary. The question is how we sequence the migration to eliminate single points of failure. Parallel-run periods, phased cutover, and rollback plans are standard practice.",
        "questions": [
            "What's your change management process for production identity changes?",
            "Have you migrated identity systems before — what was the experience?",
            "What's the acceptable downtime window, if any?",
            "Are there specific high-risk applications where identity change is particularly sensitive?"
        ],
        "tradeoffs": [
            "Big bang migration: faster total timeline, higher risk, requires more executive sponsorship",
            "Phased migration: lower risk, longer duration, maintains dual-run overhead during transition",
            "Pilot first: validate with non-critical systems, prove the approach before production — adds 4-8 weeks"
        ]
    },
    "political_resistance": {
        "acknowledgement": "Internal resistance is often the biggest implementation risk — technical problems are solvable, political ones are harder.",
        "reframe": "This is a stakeholder management challenge, not a technical one. The solution design needs to address the concerns of the resistant parties directly.",
        "questions": [
            "Who specifically is resistant, and what are their stated objections?",
            "Is there a champion at CISO or CIO level who is driving this initiative?",
            "Has there been a recent incident or audit finding that creates urgency?",
            "What would it take for the resistant party to become neutral or supportive?"
        ],
        "tradeoffs": [
            "Proceed without buy-in: faster start, higher adoption failure risk, blame landing on the project",
            "Invest in alignment first: slower start, higher success rate, requires executive time",
            "Pilot in supportive team: build evidence of success before broader rollout"
        ]
    }
}

OBJECTION_SYSTEM_PROMPT = """You are a Principal Solutions Engineer at a leading cybersecurity company with 15 years of enterprise sales experience.

You have been given:
1. A customer discovery transcript
2. Detected constraints/objections from that transcript
3. SE playbook guidance for each constraint

Your job is to generate responses that sound like a genuine, experienced SE — not a salesperson, not a consultant, not a chatbot.

Key principles:
- Acknowledge constraints before addressing them — never dismiss
- Reframe problems as solvable, not as objections to overcome
- Show you understand the customer's position
- Offer tradeoffs, not one-size answers
- Ask qualifying questions before jumping to solutions
- Be honest about where your recommended approach doesn't fit

Tone: Confident but not arrogant. Direct but not dismissive. Technical but accessible to business stakeholders.

Return ONLY valid JSON matching the schema provided."""


def detect_constraints(transcript_text: str) -> list[Constraint]:
    """Deterministic pattern matching against known constraint types"""
    detected = []
    text_lower = transcript_text.lower()

    for constraint_type, config in CONSTRAINT_PATTERNS.items():
        for pattern in config["patterns"]:
            if pattern in text_lower:
                detected.append(Constraint(
                    type=constraint_type,
                    detected_text=pattern,
                    severity=config["severity"],
                    category=config["category"]
                ))
                break  # One match per constraint type

    return detected


class ObjectionEngine:

    def __init__(self):
        self.llm = get_llm_client()

    async def analyse(
        self,
        session_id: str,
        transcript_text: str,
        gap_analysis: GapAnalysis,
        recommendations: RecommendationSet
    ) -> ObjectionAnalysis:

        constraints = detect_constraints(transcript_text)

        if not constraints:
            return ObjectionAnalysis(
                session_id=session_id,
                detected_constraints=[],
                responses=[],
                overall_strategy="No significant constraints detected. Standard solution design approach applies.",
                red_flags=[]
            )

        # Build context for LLM
        constraint_context = []
        for c in constraints:
            playbook = CONSTRAINT_PLAYBOOKS.get(c.type, {})
            constraint_context.append({
                "type": c.type,
                "severity": c.severity,
                "category": c.category,
                "playbook_acknowledgement": playbook.get("acknowledgement", ""),
                "playbook_reframe": playbook.get("reframe", ""),
                "playbook_questions": playbook.get("questions", []),
                "playbook_tradeoffs": playbook.get("tradeoffs", [])
            })

        top_gaps = [
            {"id": g.id, "title": g.title, "severity": g.severity}
            for g in gap_analysis.gaps[:5]
        ]

        messages = [{
            "role": "user",
            "content": f"""Analyse these customer constraints and generate SE responses.

Constraints detected: {json.dumps(constraint_context, indent=2)}

Customer gap analysis (top 5): {json.dumps(top_gaps, indent=2)}

Return JSON array matching this schema:
[{{
  "constraint_type": "string",
  "acknowledgement": "how a senior SE would acknowledge this constraint genuinely",
  "reframe": "how to reframe this as a solvable problem without dismissing it",
  "adjusted_approach": "specific change to architecture/recommendation given this constraint",
  "tradeoffs": ["what customer gains", "what customer gives up"],
  "questions_to_ask": ["qualifying question 1", "qualifying question 2"],
  "vendor_specific_response": "if constraint involves a specific vendor, how to position"
}}]

Also provide:
{{
  "overall_strategy": "paragraph describing how to approach this engagement given all constraints",
  "red_flags": ["constraint combination that suggests high deal/project risk"]
}}"""
        }]

        response = await self.llm.complete(OBJECTION_SYSTEM_PROMPT, messages, max_tokens=3000)

        try:
            cleaned = response.replace("```json", "").replace("```", "").strip()
            # Handle case where LLM returns array + object
            if cleaned.startswith('['):
                # Split array and overall context if combined
                data = json.loads(cleaned)
                responses_data = data if isinstance(data, list) else data.get("responses", [])
                overall = "See individual constraint responses for engagement strategy."
                red_flags = []
            else:
                data = json.loads(cleaned)
                responses_data = data.get("responses", data if isinstance(data, list) else [])
                overall = data.get("overall_strategy", "")
                red_flags = data.get("red_flags", [])

            responses = []
            for i, r in enumerate(responses_data):
                if i >= len(constraints):
                    break
                responses.append(ObjectionResponse(
                    constraint=constraints[i],
                    acknowledgement=r.get("acknowledgement", ""),
                    reframe=r.get("reframe", ""),
                    adjusted_approach=r.get("adjusted_approach", ""),
                    tradeoffs=r.get("tradeoffs", []),
                    questions_to_ask=r.get("questions_to_ask", []),
                    vendor_specific_response=r.get("vendor_specific_response")
                ))

            return ObjectionAnalysis(
                session_id=session_id,
                detected_constraints=constraints,
                responses=responses,
                overall_strategy=overall,
                red_flags=red_flags
            )

        except Exception as e:
            print(f"Objection analysis parse error: {e}")
            # Return deterministic fallback using playbooks
            responses = []
            for c in constraints:
                playbook = CONSTRAINT_PLAYBOOKS.get(c.type, {})
                responses.append(ObjectionResponse(
                    constraint=c,
                    acknowledgement=playbook.get("acknowledgement", "This is a valid constraint we need to account for."),
                    reframe=playbook.get("reframe", "Let's explore how we work within this constraint."),
                    adjusted_approach="Architecture adjusted to account for this constraint — see gap analysis for revised recommendations.",
                    tradeoffs=playbook.get("tradeoffs", []),
                    questions_to_ask=playbook.get("questions", [])
                ))

            blocking = [c for c in constraints if c.severity == "blocking"]
            return ObjectionAnalysis(
                session_id=session_id,
                detected_constraints=constraints,
                responses=responses,
                overall_strategy=f"Engagement has {len(constraints)} constraints, {len(blocking)} blocking. Requires careful sequencing.",
                red_flags=[f"{c.type} is a blocking constraint" for c in blocking]
            )
