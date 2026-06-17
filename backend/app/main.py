from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
from app.core.config import get_settings
from app.api import sessions, discovery, gaps, recommendations, executive, advanced

settings = get_settings()

app = FastAPI(
    title="Security Discovery Copilot API",
    description="AI-powered SE discovery and solution design system",
    version="1.0.0",
    docs_url="/api/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(discovery.router, prefix="/api/v1/discovery", tags=["discovery"])
app.include_router(gaps.router, prefix="/api/v1/gaps", tags=["gap-analysis"])
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["recommendations"])
app.include_router(executive.router, prefix="/api/v1/executive", tags=["executive"])
app.include_router(advanced.router, prefix="/api/v1/advanced", tags=["advanced-se"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "security-discovery-copilot"}


@app.get("/api/v1/scenarios")
async def get_scenarios():
    """Return prebuilt customer scenarios for demo"""
    return {
        "scenarios": [
            {
                "id": "saas_soc2",
                "title": "SaaS Company — SOC2 Compliance",
                "description": "500-employee SaaS company with Okta deployed, manual provisioning, SOC2 Type II required",
                "industry": "saas",
                "company_size": "500",
                "hint": "Okta deployed but no SCIM. SOC2 audit in 6 months. AWS primary. No CSPM.",
                "expected_gaps": ["no_scim_automation", "low_mfa_coverage", "no_cspm"]
            },
            {
                "id": "fintech_zerotrust",
                "title": "FinTech — Zero Trust Initiative",
                "description": "2000-employee FinTech, hybrid environment, new CISO mandating Zero Trust",
                "industry": "fintech",
                "company_size": "2000",
                "hint": "AD + Azure AD hybrid. VPN-dependent. New CISO. PCI-DSS scope. No PAM.",
                "expected_gaps": ["vpn_dependency", "no_pam", "shared_admin_credentials"]
            },
            {
                "id": "healthcare_phi",
                "title": "Healthcare — PHI + Identity Governance",
                "description": "750-employee healthcare provider, remote workforce, HIPAA requirements, identity governance gaps",
                "industry": "healthcare",
                "company_size": "750",
                "hint": "Remote workforce. PHI in AWS S3. No PAM. No access reviews. HIPAA scope.",
                "expected_gaps": ["phi_data_exposure", "no_iga", "no_pam", "low_mfa_coverage"]
            },
            {
                "id": "enterprise_acquisition",
                "title": "Global Enterprise — Post-Acquisition IAM",
                "description": "10,000-employee enterprise integrating an acquired company's identity estate",
                "industry": "enterprise",
                "company_size": "10000",
                "hint": "Multi-cloud: AWS + Azure + GCP. Recent acquisition with separate AD. Shadow IT. No IGA.",
                "expected_gaps": ["no_iga", "no_cspm", "low_mfa_coverage", "no_low_app_federation"]
            }
        ]
    }


# Serve frontend at /ui — same pattern as governance copilot
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/ui", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    @app.get("/")
    async def root():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
