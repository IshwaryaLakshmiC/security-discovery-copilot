"""
Executive Summary Engine — AI-powered.

Justified AI usage: synthesising complex technical findings
into clear, business-level communication is exactly what
LLMs excel at. The inputs (gaps, scores, recommendations)
are all deterministic — only the language generation is AI.
"""

from app.core.llm import get_llm_client
from app.core.json_utils import extract_json_object
from app.models.schemas import (
    GapAnalysis, RecommendationSet, ExecutiveSummary,
    RoadmapPhase, Session
)
from datetime import datetime
import json


EXECUTIVE_SYSTEM_PROMPT = """You are a Principal Solutions Architect writing a post-discovery executive summary for a CISO and CIO.

Your audience: C-suite security decision makers. They are not interested in technical implementation details. They care about:
- Business risk in plain English
- Financial and reputational impact
- Prioritised roadmap with realistic timelines
- Clear next steps

Style:
- Direct, confident, concise
- Business impact framing — not technical jargon
- Quantify risk where possible (cost of breach, compliance fines)
- 3 phases max for roadmap
- No bullet point overload — use prose where possible

You will be given:
- Company context (name, size, industry)
- Gap analysis results (gaps, severity, framework refs)
- Maturity scores per domain
- Vendor recommendations

Generate a professional executive summary following the JSON schema provided."""


class ExecutiveEngine:

    def __init__(self):
        self.llm = get_llm_client()

    async def generate(
        self,
        session: Session,
        gap_analysis: GapAnalysis,
        recommendations: RecommendationSet
    ) -> ExecutiveSummary:

        # Build context for LLM
        gap_summary = [
            {
                "title": g.title,
                "severity": g.severity,
                "business_impact": g.business_impact,
                "framework_refs": g.framework_references[:2]
            }
            for g in sorted(
                gap_analysis.gaps,
                key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}[x.severity]
            )
        ]

        maturity_summary = {
            domain: {"score": score.score, "rationale": score.rationale}
            for domain, score in gap_analysis.maturity_scores.items()
        }

        vendor_summary = [
            {
                "vendor": r.vendor,
                "product": r.product,
                "addresses": r.addresses_gaps[:2],
                "why_fits": r.why_it_fits[:200]
            }
            for r in recommendations.recommendations[:5]
        ]

        prompt_data = {
            "company_name": session.company_name,
            "industry": session.industry or "technology",
            "employee_count": session.company_size or "unknown",
            "overall_risk": gap_analysis.overall_risk_level,
            "compliance_status": gap_analysis.compliance_status,
            "gaps": gap_summary,
            "maturity_scores": maturity_summary,
            "top_vendors": vendor_summary,
        }

        schema_instruction = """
Return ONLY valid JSON with this exact schema:
{
  "executive_overview": "2-3 sentence summary for a CIO/CISO",
  "key_risks": [
    {"risk": "string", "business_impact": "string", "urgency": "immediate|30-days|90-days"}
  ],
  "current_state_summary": "1 paragraph describing current security posture",
  "recommended_architecture": "1 paragraph describing the target architecture",
  "roadmap": [
    {
      "phase": 1,
      "title": "string",
      "duration": "0-90 days",
      "objectives": ["string"],
      "vendors": ["string"],
      "estimated_cost_range": "string",
      "success_metrics": ["string"]
    }
  ],
  "top_vendor_recommendations": ["vendor: reason in one sentence"],
  "estimated_total_investment": "ballpark range with rationale",
  "next_steps": ["specific actionable next step"]
}"""

        messages = [{
            "role": "user",
            "content": f"Generate an executive summary for this security discovery engagement:\n\n{json.dumps(prompt_data, indent=2)}\n\n{schema_instruction}"
        }]

        response = await self.llm.complete(EXECUTIVE_SYSTEM_PROMPT, messages, max_tokens=3000)

        try:
            data = extract_json_object(response)

            roadmap = [RoadmapPhase(**phase) for phase in data.get("roadmap", [])]

            return ExecutiveSummary(
                session_id=session.id,
                company_name=session.company_name,
                date=datetime.utcnow(),
                executive_overview=data.get("executive_overview", ""),
                key_risks=data.get("key_risks", []),
                current_state_summary=data.get("current_state_summary", ""),
                recommended_architecture=data.get("recommended_architecture", ""),
                roadmap=roadmap,
                top_vendor_recommendations=data.get("top_vendor_recommendations", []),
                estimated_total_investment=data.get("estimated_total_investment", ""),
                next_steps=data.get("next_steps", []),
                generated_at=datetime.utcnow()
            )
        except Exception as e:
            print(f"Executive summary parse error: {e} | raw response: {response[:500]}")
            raise ValueError(f"Failed to generate executive summary: {e}")
