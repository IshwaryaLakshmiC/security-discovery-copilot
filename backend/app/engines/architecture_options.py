"""
Alternative Architecture Mode

Enterprise customers rarely accept one recommendation.
A senior SE always presents options with honest tradeoffs.

4 paths: Best Security / Best Cost / Fastest TTV / Lowest OpEx

Design principle: option generation uses AI for narrative,
but scoring and tradeoff dimensions are deterministic.
"""

import json
from app.core.llm import get_llm_client
from app.models.schemas import GapAnalysis, ExtractedEntities
from pydantic import BaseModel
from typing import Optional


class ArchitectureOption(BaseModel):
    option: str                     # A, B, C, D
    label: str                      # "Best Security", "Best Cost", etc.
    headline: str                   # One-sentence description
    approach: str                   # 2-3 paragraph architecture description
    primary_vendors: list[str]
    gaps_addressed: list[str]       # Gap IDs fully addressed
    gaps_deferred: list[str]        # Gap IDs left for later
    risk_accepted: str              # What risk this option accepts
    cost_tier: str                  # low | medium | high | very-high
    cost_rationale: str
    operational_burden: str         # low | medium | high
    operational_rationale: str
    time_to_value_weeks: int        # Estimated weeks to first value
    implementation_phases: list[dict]
    when_to_choose: str             # Specific conditions that make this the right choice
    when_not_to_choose: str         # Specific conditions that rule this out


class ArchitectureOptionsSet(BaseModel):
    session_id: str
    options: list[ArchitectureOption]
    recommendation: str             # Which option the SE recommends and why
    decision_matrix: list[dict]     # Comparative scoring across dimensions


ARCHITECTURE_OPTIONS_PROMPT = """You are a Principal Solutions Architect generating 4 alternative architecture options for an enterprise security engagement.

You will receive:
- Customer gap analysis (top security gaps with severity)
- Extracted entities (current tools, cloud platforms, compliance requirements)

Generate exactly 4 options:
- Option A: Best Security — maximise security coverage, cost is secondary
- Option B: Best Cost — address critical gaps within tightest budget
- Option C: Fastest Time to Value — what can be live in 30-60 days
- Option D: Lowest Operational Overhead — minimise ongoing team burden

Rules:
- Be specific about vendors and architecture for each option
- Be honest about what each option DOESN'T cover
- The "risk accepted" field must name real risks, not platitudes
- Phased timelines must be realistic — don't say "week 1: deploy everything"
- When one option is clearly wrong for this customer, say so directly

Return ONLY valid JSON array of 4 options matching the schema.

Schema for each option:
{
  "option": "A",
  "label": "Best Security",
  "headline": "one sentence",
  "approach": "2-3 paragraph architecture description",
  "primary_vendors": ["vendor1", "vendor2"],
  "gaps_addressed": ["gap_id_1"],
  "gaps_deferred": ["gap_id_2"],
  "risk_accepted": "specific risk accepted by choosing this option",
  "cost_tier": "high",
  "cost_rationale": "why this costs what it costs",
  "operational_burden": "medium",
  "operational_rationale": "what the team needs to operate this",
  "time_to_value_weeks": 12,
  "implementation_phases": [
    {"phase": 1, "duration": "0-30 days", "activities": ["activity1"]},
    {"phase": 2, "duration": "30-90 days", "activities": ["activity2"]}
  ],
  "when_to_choose": "specific conditions",
  "when_not_to_choose": "specific conditions"
}"""


class ArchitectureOptionsEngine:

    def __init__(self):
        self.llm = get_llm_client()

    async def generate(
        self,
        session_id: str,
        gap_analysis: GapAnalysis,
        entities: ExtractedEntities
    ) -> ArchitectureOptionsSet:

        gaps_context = [
            {
                "id": g.id,
                "title": g.title,
                "severity": g.severity,
                "domain": g.domain,
                "remediation_effort": g.remediation_effort,
                "estimated_days": g.estimated_days
            }
            for g in gap_analysis.gaps
        ]

        customer_context = {
            "current_tools": entities.identity_tools + entities.security_tools + entities.network_tools,
            "cloud_platforms": entities.cloud_platforms,
            "compliance_requirements": entities.compliance_requirements,
            "industry": entities.industry,
            "employee_count": entities.employee_count,
            "it_maturity": entities.it_maturity
        }

        messages = [{
            "role": "user",
            "content": f"""Generate 4 alternative architecture options for this customer.

Security gaps to address:
{json.dumps(gaps_context, indent=2)}

Customer context:
{json.dumps(customer_context, indent=2)}

Overall risk level: {gap_analysis.overall_risk_level}
Compliance gaps: {json.dumps(gap_analysis.compliance_status, indent=2)}

Generate the 4 options as a JSON array."""
        }]

        response = await self.llm.complete(ARCHITECTURE_OPTIONS_PROMPT, messages, max_tokens=4000)

        try:
            cleaned = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            options_data = data if isinstance(data, list) else data.get("options", [])

            options = []
            labels = ["Best Security", "Best Cost", "Fastest Time to Value", "Lowest Operational Overhead"]
            option_letters = ["A", "B", "C", "D"]

            for i, item in enumerate(options_data[:4]):
                options.append(ArchitectureOption(
                    option=item.get("option", option_letters[i]),
                    label=item.get("label", labels[i]),
                    headline=item.get("headline", ""),
                    approach=item.get("approach", ""),
                    primary_vendors=item.get("primary_vendors", []),
                    gaps_addressed=item.get("gaps_addressed", []),
                    gaps_deferred=item.get("gaps_deferred", []),
                    risk_accepted=item.get("risk_accepted", ""),
                    cost_tier=item.get("cost_tier", "medium"),
                    cost_rationale=item.get("cost_rationale", ""),
                    operational_burden=item.get("operational_burden", "medium"),
                    operational_rationale=item.get("operational_rationale", ""),
                    time_to_value_weeks=int(item.get("time_to_value_weeks", 12)),
                    implementation_phases=item.get("implementation_phases", []),
                    when_to_choose=item.get("when_to_choose", ""),
                    when_not_to_choose=item.get("when_not_to_choose", "")
                ))

            # Build decision matrix
            decision_matrix = [
                {
                    "dimension": "Security coverage",
                    "A": "●●●●●", "B": "●●●○○", "C": "●●●○○", "D": "●●○○○"
                },
                {
                    "dimension": "Upfront cost",
                    "A": "Very high", "B": "Low-medium", "C": "Medium", "D": "Medium"
                },
                {
                    "dimension": "Time to value",
                    "A": "16-24 wks", "B": "8-12 wks",
                    "C": f"{options[2].time_to_value_weeks if len(options)>2 else 6} wks",
                    "D": "10-16 wks"
                },
                {
                    "dimension": "Operational overhead",
                    "A": "High", "B": "Medium", "C": "Low-medium", "D": "Low"
                },
                {
                    "dimension": "Compliance fit",
                    "A": "Excellent", "B": "Good", "C": "Partial", "D": "Good"
                }
            ]

            # Recommendation: for most customers, Option C or B is right starting point
            recommendation = (
                f"For this customer profile, Option B (Best Cost) or Option C (Fastest TTV) "
                f"is recommended as the starting point, with a roadmap toward Option A over 18-24 months. "
                f"Option D is appropriate if team size is the primary constraint. "
                f"Present all options to the customer and let them choose based on their current priorities."
            )

            return ArchitectureOptionsSet(
                session_id=session_id,
                options=options,
                recommendation=recommendation,
                decision_matrix=decision_matrix
            )

        except Exception as e:
            print(f"Architecture options parse error: {e}")
            raise ValueError(f"Failed to generate architecture options: {e}")
