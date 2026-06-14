# Security Discovery & Solution Design Copilot

> **An AI system that performs the first three meetings of a Solutions Engineering engagement** — adaptive customer discovery, deterministic gap analysis, RAG-grounded vendor recommendations, and CISO-ready executive summary.

Live demo: **[ishwaryaaunfiltered.live/discovery](https://ishwaryaaunfiltered.live/discovery)**  
Built by [Ishwarya Lakshmi C](https://github.com/IshwaryaLakshmiC) · [ishwaryaaunfiltered.live](https://ishwaryaaunfiltered.live)

---

## Why this exists

Enterprise customers engage security vendors with vague requirements: *"We want Zero Trust"*, *"We need better IAM"*, *"We need to reduce risk."* A Solutions Engineer's job is to turn that into a specific, prioritised, architecturally sound recommendation.

This system codifies that SE workflow:

| SE Meeting | System Component |
|-----------|-----------------|
| Discovery call | Adaptive question engine (Claude) |
| Architecture analysis | Gap scoring engine (deterministic) |
| Solution recommendation | RAG-grounded vendor recommendation (Claude + pgvector) |
| Post-meeting deliverable | Executive summary PDF (Claude) |

---

## What makes this different from a chatbot

**Most of the system is deterministic, not AI.**

| Component | Approach | Why |
|-----------|----------|-----|
| Discovery questions | AI (Claude) | Adaptive reasoning required |
| Gap severity scores | Deterministic | Compliance frameworks are exact |
| Vendor feature facts | RAG (pgvector) | AI cannot be trusted to recall product capabilities |
| Vendor recommendations | AI + RAG | Reasoning over deterministic facts |
| Executive summary writing | AI (Claude) | Language generation — appropriate |
| Compliance control mapping | Deterministic | CIS/NIST/SOC2 controls are fixed |

---

## Four customer scenarios included

| Scenario | Company | Key gaps |
|----------|---------|----------|
| SaaS SOC2 | 500-employee SaaS, Okta deployed | SCIM automation, MFA gaps, no CSPM |
| FinTech Zero Trust | 2000-employee FinTech, hybrid | VPN dependency, no PAM, shared admin creds |
| Healthcare HIPAA | 750-employee healthcare, remote | PHI exposure, no IGA, no PAM |
| Enterprise M&A | 10,000-employee post-acquisition | IGA gaps, federation inconsistency, shadow IT |

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full system diagram.

```
Discovery Engine (Claude)
    → Entity Extraction
    → Gap Analysis Engine (deterministic)
    → Vendor Recommendations (Claude + pgvector RAG)
    → Executive Summary (Claude)
    → PDF Export
```

**Shared infrastructure** with [aws-governance-copilot](https://github.com/IshwaryaLakshmiC/aws-governance-copilot):
- Same RDS PostgreSQL + pgvector instance
- Same EC2 app server (separate FastAPI router on `/discovery`)
- Separate table namespace in shared DB

---

## Running locally (Docker)

```bash
git clone https://github.com/IshwaryaLakshmiC/security-discovery-copilot
cd security-discovery-copilot

# Configure environment
cp backend/.env.example backend/.env
# Edit .env — add your OpenRouter API key for local dev

# Start everything
docker-compose up

# Access
# Frontend: http://localhost:3000
# API docs: http://localhost:8001/api/docs
```

---

## Running on AWS (production)

Uses infrastructure from [aws-governance-copilot-infra](https://github.com/IshwaryaLakshmiC/aws-governance-copilot-infra).

```bash
# After terraform apply in the infra repo:
ssh -i ~/.ssh/governance-copilot.pem ec2-user@<EC2_PUBLIC_IP>

# Deploy
git clone https://github.com/IshwaryaLakshmiC/security-discovery-copilot /opt/discovery-copilot
cd /opt/discovery-copilot/backend
pip3.11 install -r requirements.txt
cp .env.example .env
# Fill in DB credentials from terraform output

# Run on port 8001 (alongside governance copilot on 8000)
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

---

## API Reference

Full docs at `/api/docs` (Swagger UI).

```
POST /api/v1/sessions/                    Create discovery session
POST /api/v1/discovery/{id}/start         Start adaptive discovery
POST /api/v1/discovery/{id}/message       Send message (streaming SSE)
GET  /api/v1/discovery/{id}/transcript    Get full transcript
POST /api/v1/gaps/{id}/analyse            Run gap analysis
GET  /api/v1/gaps/{id}                    Get gap analysis results
POST /api/v1/recommendations/{id}/generate Generate vendor recommendations
POST /api/v1/executive/{id}/generate      Generate executive summary
GET  /api/v1/scenarios                    List prebuilt demo scenarios
```

---

## Gap library

10 pre-defined gaps with deterministic severity scoring:

| Gap | Domain | Severity | Framework refs |
|-----|--------|----------|---------------|
| No SCIM automation | IAM | HIGH | SOC2 CC6.2, CIS 5.2 |
| MFA not enforced | IAM | CRITICAL | CIS 6.3, NIST 800-63B |
| No PAM | PAM | CRITICAL | CIS 5.4, SOC2 CC6.3 |
| VPN dependency | Zero Trust | HIGH | NIST 800-207 |
| No CSPM | Cloud | HIGH | CIS AWS Benchmark |
| Low app federation | IAM | MEDIUM | CIS 12.1 |
| Incomplete audit logs | Cloud | HIGH | CIS 3.1, SOC2 CC7.2 |
| No IGA | Governance | HIGH | SOC2 CC6.2 |
| Shared admin credentials | PAM | CRITICAL | CIS 5.1, SOC2 CC6.3 |
| No EDR | Endpoint | HIGH | CIS 10.1 |

---

## Vendors covered

Okta · Cloudflare Access · CrowdStrike · Wiz · CyberArk · SailPoint · Zscaler · Palo Alto Prisma

Each vendor has deterministic capability cards covering: fits_when, not_fits_when, cost_tier, gaps_addressed.

---

## Related projects

- [aws-governance-copilot-infra](https://github.com/IshwaryaLakshmiC/aws-governance-copilot-infra) — Shared Terraform infrastructure
- [aws-governance-copilot](https://github.com/IshwaryaLakshmiC/aws-governance-copilot) — AI security + cost intelligence over real AWS
- [ztna-simulator](https://github.com/IshwaryaLakshmiC/ztna-simulator) — Interactive Zero Trust policy engine with Okta SSO

---

**Ishwarya Lakshmi C** — Senior DevOps & Cloud Security Engineer  
[GitHub](https://github.com/IshwaryaLakshmiC) · [Website](https://ishwaryaaunfiltered.live) · [LinkedIn](https://linkedin.com/in/ishwaryachengalvarayan)
