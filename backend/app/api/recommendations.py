from fastapi import APIRouter, HTTPException
from app.api.gaps import gap_results
from app.core.llm import get_llm_client
from app.models.schemas import RecommendationSet, VendorRecommendation, Domain
from datetime import datetime
import json

router = APIRouter()
llm = get_llm_client()
recommendation_results: dict[str, RecommendationSet] = {}

# Vendor recommendation data — deterministic facts, AI does the reasoning
VENDOR_DATA = {
    "okta": {
        "domains": ["iam", "governance"],
        "strengths": "Market-leading SSO/MFA, deep SCIM integrations, 7000+ pre-built app connectors, Okta Lifecycle Management for automated provisioning",
        "fits_when": "Okta already deployed, need SCIM automation, SaaS-heavy environment, SOC2 compliance",
        "not_fits_when": "Heavy on-prem AD dependency without cloud migration plan, very small companies (<100)",
        "cost_tier": "mid-market to enterprise",
        "gaps_addressed": ["no_scim_automation", "low_mfa_coverage", "no_low_app_federation"]
    },
    "cloudflare_access": {
        "domains": ["zerotrust", "network"],
        "strengths": "Fastest ZTNA deployment, 300+ global PoPs, built-in DNS filtering (Gateway), generous free tier for POC",
        "fits_when": "Fast Zero Trust deployment needed, SaaS-first company, replacing VPN quickly, small-medium security team",
        "not_fits_when": "Need deep DLP inline inspection, complex on-prem application publishing",
        "cost_tier": "startup to mid-market",
        "gaps_addressed": ["vpn_dependency"]
    },
    "crowdstrike": {
        "domains": ["endpoint", "identity"],
        "strengths": "Best-in-class behavioural EDR, Falcon Identity Threat Detection (ITDR), threat intelligence, AI-powered detection",
        "fits_when": "Modern endpoint protection needed, identity threat detection required, strong threat intelligence value",
        "not_fits_when": "Very budget-constrained, need lightweight agent",
        "cost_tier": "enterprise",
        "gaps_addressed": ["no_edr"]
    },
    "wiz": {
        "domains": ["cloud"],
        "strengths": "Agentless CSPM, graph-based risk assessment, fastest cloud visibility deployment (hours not weeks), multi-cloud",
        "fits_when": "AWS/Azure/GCP environment, need CSPM quickly, small security team, cloud-native organisation",
        "not_fits_when": "On-prem only environment, need agent-based deep workload protection",
        "cost_tier": "mid-market to enterprise",
        "gaps_addressed": ["no_cspm"]
    },
    "cyberark": {
        "domains": ["pam"],
        "strengths": "Most comprehensive PAM platform, session recording, JIT access, credential vaulting, secrets management",
        "fits_when": "Enterprise PAM requirement, heavy compliance (PCI, SOX), large privileged user base, on-prem systems",
        "not_fits_when": "Small company, cloud-only environment, need fast deployment",
        "cost_tier": "enterprise",
        "gaps_addressed": ["no_pam", "shared_admin_credentials"]
    },
    "sailpoint": {
        "domains": ["governance"],
        "strengths": "Leading IGA platform, role mining, access certification, SaaS and on-prem coverage, AI-driven access recommendations",
        "fits_when": "Enterprise IGA requirement, complex role landscape, regulatory compliance (SOX, HIPAA), large user base",
        "not_fits_when": "Under 500 employees, need fast deployment, budget-constrained",
        "cost_tier": "enterprise",
        "gaps_addressed": ["no_iga", "no_scim_automation"]
    },
    "zscaler": {
        "domains": ["zerotrust", "network"],
        "strengths": "Most mature SASE platform, strongest inline DLP, Internet Access + Private Access, large enterprise track record",
        "fits_when": "Large enterprise ZTNA, strong DLP requirements, existing Zscaler Internet Access, global workforce",
        "not_fits_when": "Small company, simple ZTNA requirement, budget-constrained, cloud-native DevOps teams",
        "cost_tier": "enterprise",
        "gaps_addressed": ["vpn_dependency"]
    },
    "palo_alto_prisma": {
        "domains": ["cloud", "network"],
        "strengths": "Comprehensive SASE + CSPM, NGFW capabilities inline, strong for existing Palo Alto customers, deep inspection",
        "fits_when": "Existing Palo Alto firewall investment, need NGFW-level inspection inline, large enterprise",
        "not_fits_when": "No existing Palo Alto investment, need fast deployment, cloud-native org",
        "cost_tier": "enterprise",
        "gaps_addressed": ["vpn_dependency", "no_cspm"]
    }
}

RECOMMENDATION_SYSTEM_PROMPT = """You are a Principal Solutions Architect making vendor recommendations to a CISO.

You have been given:
1. A list of security gaps with severity and business impact
2. The customer's context (size, industry, compliance requirements)
3. Vendor capability facts (verified, deterministic data)

Your job: recommend the RIGHT vendors for this specific customer — not the most expensive or most popular.

Rules:
1. Recommend based on the gaps, not vendor prestige
2. Always explain WHY it fits AND why it may NOT fit
3. Consider company size — don't recommend enterprise PAM to a 100-person startup
4. Flag overlapping products honestly
5. Rank by impact vs implementation effort (quick wins first)
6. Maximum 5 vendor recommendations

Return ONLY valid JSON as an array of recommendations:
[{
  "vendor": "string",
  "product": "string",
  "domain": "iam|cloud|zerotrust|pam|endpoint|governance",
  "addresses_gaps": ["gap_id"],
  "fit_score": 0.0-1.0,
  "why_it_fits": "specific to this customer context",
  "why_it_may_not_fit": "honest assessment",
  "cost_consideration": "practical cost note",
  "operational_consideration": "practical ops note",
  "implementation_phase": 1|2|3
}]"""


@router.post("/{session_id}/generate")
async def generate_recommendations(session_id: str):
    """Generate RAG-grounded vendor recommendations from gap analysis"""
    gap_analysis = gap_results.get(session_id)
    if not gap_analysis:
        raise HTTPException(status_code=404, detail="Run gap analysis first")

    # Build gap context
    gap_context = [
        {"id": g.id, "title": g.title, "severity": g.severity, "domain": g.domain}
        for g in gap_analysis.gaps
    ]

    # Find relevant vendor data based on gaps
    gap_ids = {g.id for g in gap_analysis.gaps}
    relevant_vendors = {
        vendor: data for vendor, data in VENDOR_DATA.items()
        if any(gap in data["gaps_addressed"] for gap in gap_ids)
    }

    messages = [{
        "role": "user",
        "content": f"""Customer gaps: {json.dumps(gap_context, indent=2)}

Overall risk: {gap_analysis.overall_risk_level}
Compliance requirements: {gap_analysis.compliance_status}

Available vendor data:
{json.dumps(relevant_vendors, indent=2)}

Generate vendor recommendations for this customer."""
    }]

    response = await llm.complete(RECOMMENDATION_SYSTEM_PROMPT, messages, max_tokens=3000)

    try:
        cleaned = response.replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned)

        vendor_recs = []
        for item in data:
            try:
                rec = VendorRecommendation(
                    vendor=item["vendor"],
                    product=item["product"],
                    domain=Domain(item["domain"]),
                    addresses_gaps=item.get("addresses_gaps", []),
                    fit_score=float(item.get("fit_score", 0.7)),
                    why_it_fits=item["why_it_fits"],
                    why_it_may_not_fit=item["why_it_may_not_fit"],
                    cost_consideration=item["cost_consideration"],
                    operational_consideration=item["operational_consideration"],
                    implementation_phase=int(item.get("implementation_phase", 2))
                )
                vendor_recs.append(rec)
            except Exception as e:
                print(f"Vendor rec parse error: {e}")

        result = RecommendationSet(
            session_id=session_id,
            recommendations=sorted(vendor_recs, key=lambda x: (x.implementation_phase, -x.fit_score)),
            architecture_notes="See executive summary for full architecture recommendation.",
            implementation_roadmap=[],
            generated_at=datetime.utcnow()
        )
        recommendation_results[session_id] = result
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation generation failed: {e}")


@router.get("/{session_id}")
async def get_recommendations(session_id: str):
    result = recommendation_results.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No recommendations found")
    return result
