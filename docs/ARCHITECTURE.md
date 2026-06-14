# Architecture — Security Discovery & Solution Design Copilot

## What This System Does

Maps the first 3 customer meetings of an SE engagement into an AI-powered system:

```
Meeting 1: Discovery         → Dynamic question engine
Meeting 2: Gap Analysis      → Deterministic scoring + risk register
Meeting 3: Recommendations   → RAG-grounded vendor recommendations
Post-meeting: Deliverables   → Executive summary PDF + architecture diagram
```

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        React Frontend                               │
│                                                                     │
│  ┌──────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │
│  │  Discovery   │  │   Gap Analysis  │  │  Recommendation     │   │
│  │  Chat UI     │  │   Dashboard     │  │  Engine UI          │   │
│  │              │  │                 │  │                     │   │
│  │  Streaming   │  │  Maturity radar │  │  Vendor cards       │   │
│  │  responses   │  │  Risk register  │  │  Why it fits /      │   │
│  │  Scenario    │  │  Compliance gap │  │  why it may not     │   │
│  │  library     │  │  table          │  │  Cost/ops notes     │   │
│  └──────────────┘  └─────────────────┘  └─────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │           Executive Summary + Architecture Diagram           │  │
│  │           PDF export · Mermaid diagram · Roadmap             │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬────────────────────────────────────┘
                                │ REST + WebSocket
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                               │
│                                                                    │
│  /api/v1/sessions          Session management                     │
│  /api/v1/discovery         Discovery engine + streaming           │
│  /api/v1/gaps              Gap analysis engine                    │
│  /api/v1/recommendations   RAG-grounded recommendations           │
│  /api/v1/executive         Executive summary generation           │
│  /api/v1/architecture      Diagram generation (Mermaid)           │
└──────────┬──────────────────────┬──────────────────────┬──────────┘
           │                      │                      │
           ▼                      ▼                      ▼
┌─────────────────┐  ┌────────────────────┐  ┌──────────────────────┐
│  Discovery      │  │   Gap Analysis     │  │   RAG + MCP Layer    │
│  Engine         │  │   Engine           │  │                      │
│  (AI)           │  │   (Deterministic)  │  │  pgvector search     │
│                 │  │                    │  │  Vendor capability   │
│  Claude via     │  │  CIS Controls      │  │  cards               │
│  Bedrock        │  │  NIST CSF          │  │  Framework mappings  │
│                 │  │  SOC2 / ISO27001   │  │  Reference archs     │
│  Adaptive       │  │  Zero Trust        │  │                      │
│  questions      │  │  maturity model    │  │  MCP tools:          │
│  based on       │  │                    │  │  search_vendors()    │
│  prior answers  │  │  Severity scores   │  │  get_controls()      │
│                 │  │  Business impact   │  │  score_maturity()    │
└────────┬────────┘  └────────────────────┘  └──────────┬───────────┘
         │                                               │
         └───────────────────┬───────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │   AWS Bedrock            │
              │   Claude 3 Sonnet        │
              │   (primary LLM)          │
              │                          │
              │   OpenRouter fallback    │
              │   Mistral 7B (free)      │
              └──────────────────────────┘
```

---

## AI vs Deterministic — The Critical Design Decision

```
Component                    Approach        Reason
────────────────────────────────────────────────────────────────────
Discovery questioning        AI (Claude)     Adaptive reasoning
                                             required — static
                                             questionnaires miss
                                             context-dependent gaps

Gap severity scoring         Deterministic   Compliance frameworks
                                             are exact. AI scoring
                                             would be inconsistent
                                             and non-auditable.

Vendor feature facts         Deterministic   Pulled from RAG store.
(in pgvector)                (RAG retrieval) AI cannot be trusted
                                             to recall product
                                             capabilities accurately.

Vendor recommendation        AI + RAG        AI reasons over
rationale                                    deterministic facts
                                             retrieved from vector DB.

Executive summary writing    AI (Claude)     Language generation —
                                             appropriate AI use.

Compliance control mapping   Deterministic   CIS/NIST/SOC2 controls
                                             are fixed. No ambiguity.

Architecture diagram code    AI (Claude)     Mermaid DSL generation
                                             from discovery context.
```

---

## Discovery Engine — SE Methodology Encoded

```
System prompt encodes:

1. Domain detection
   Customer mentions "Okta" → IAM domain flagged
   Customer mentions "AWS" → Cloud domain flagged
   Customer mentions "SOC2" → Compliance domain flagged

2. Adaptive question depth
   Shallow answer → probe deeper
   Technical answer → match technical depth
   Executive answer → translate to business impact

3. Gap surfacing patterns
   Tool mentioned → ask about automation/integration
   Compliance mentioned → ask about evidence collection
   Cloud mentioned → ask about shared responsibility understanding

4. Completion signals
   All critical domains covered → transition to gap analysis
   Confidence threshold met per domain → stop probing that domain

Example adaptive flow:
  Customer: "We use Okta"
  → Is lifecycle management automated or manual?
  Customer: "Manual onboarding"
  → How many applications are in scope?
  Customer: "About 80 apps"
  → What percentage are federated vs password-vaulted?
  Customer: "Maybe 30% federated"
  → [Surfaces: Federation gap, SCIM gap, lifecycle automation gap]
```

---

## RAG Design — Vendor Capability Cards

```
Vector DB (pgvector) schema for vendor data:

vendor_capabilities table
─────────────────────────────────────────────────────
id           SERIAL PRIMARY KEY
vendor       TEXT    -- okta, cloudflare, crowdstrike...
domain       TEXT    -- iam, ztna, cspm, edr, pam...
capability   TEXT    -- specific feature/capability
description  TEXT    -- detailed description
fits_when    TEXT    -- conditions where this is a good fit
not_fits_when TEXT   -- conditions where this is a poor fit
cost_tier    TEXT    -- enterprise|mid-market|startup
embedding    vector(1536)

Example cards:
  vendor=okta, domain=iam, capability="SCIM Provisioning"
  vendor=cloudflare, domain=ztna, capability="Access Policies"
  vendor=wiz, domain=cspm, capability="Cloud Configuration Scanning"
  vendor=crowdstrike, domain=edr, capability="Behavioral Detection"
  vendor=cyberark, domain=pam, capability="Privileged Session Recording"

Query pattern:
  Customer gap: "No automated deprovisioning"
  → search_vendors(query="user deprovisioning automation",
                   domain="iam",
                   company_size="500",
                   industry="saas")
  → Returns: Okta Lifecycle, SailPoint, Saviynt cards
  → Claude reasons: "Okta fits because already deployed,
                     SailPoint overkill at 500 employees"
```

---

## MCP Tools

```python
# Tools the LLM can call during reasoning

@mcp_tool
def search_vendor_capabilities(
    query: str,
    domain: str,           # iam|ztna|cspm|edr|pam|siem
    company_size: str,     # startup|mid-market|enterprise
    industry: str = None,  # fintech|healthcare|saas|retail
) -> list[VendorCapability]:
    """RAG search over vendor capability cards"""

@mcp_tool
def get_compliance_controls(
    framework: str,        # cis|nist_csf|soc2|iso27001|hipaa|pci
    category: str,         # iam|network|data|ops|incident
) -> list[ComplianceControl]:
    """Returns exact control requirements for a framework/category"""

@mcp_tool
def score_maturity(
    domain: str,           # iam|cloud|zerotrust|ops
    answers: dict,         # extracted from discovery transcript
) -> MaturityScore:
    """Deterministic maturity scoring 1-5 per domain"""

@mcp_tool
def get_gap_severity(
    gap_type: str,         # no_mfa|no_scim|public_s3|no_pam...
    context: dict,         # company_size, industry, compliance_req
) -> GapSeverity:
    """Returns severity + business impact for a specific gap"""
```

---

## Data Flow — Full Engagement

```
1. User selects scenario OR starts fresh
        │
        ▼
2. Discovery Engine (Claude)
   Adaptive questions → Structured transcript
   Extracted entities: tools, gaps, constraints, compliance reqs
        │
        ▼
3. Gap Analysis Engine (Deterministic)
   Transcript → Gap scoring matrix
   Output: Risk register with severity + framework ref
        │
        ▼
4. Recommendation Engine (RAG + Claude)
   Gaps → search_vendor_capabilities() → Retrieved cards
   Claude reasons over cards → Ranked recommendations
        │
        ▼
5. Architecture Diagram (Claude)
   Discovery context → Mermaid DSL → Rendered diagram
   Current state + Recommended future state
        │
        ▼
6. Executive Summary (Claude)
   All outputs → 1-page CISO deliverable
   Key risks · Roadmap · Vendor recommendations · Next steps
        │
        ▼
7. PDF Export
   Full deliverable package ready to send to customer
```

---

## Prebuilt Scenarios

```
Scenario 1: SaaS startup (500 employees)
  • AWS + Okta deployed, no SCIM automation
  • SOC2 Type II required within 12 months
  • Expected gaps: SCIM, app federation, MFA gaps, CloudTrail

Scenario 2: FinTech (2000 employees)
  • Hybrid: AD + Azure AD + AWS
  • Zero Trust initiative from new CISO
  • Expected gaps: Legacy VPN, no ZTNA, PAM gaps, lateral movement

Scenario 3: Healthcare (750 employees)
  • Remote workforce, PHI requirements
  • Identity governance gaps, no PAM
  • Expected gaps: HIPAA access logging, PHI encryption, privileged access

Scenario 4: Global enterprise (10,000 employees)
  • Multi-cloud: AWS + Azure + GCP
  • Post-acquisition IAM complexity
  • Expected gaps: Federation inconsistency, shadow IT, IGA gaps
```

---

## Repository Structure

```
security-discovery-copilot/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI route handlers
│   │   │   ├── sessions.py
│   │   │   ├── discovery.py
│   │   │   ├── gaps.py
│   │   │   ├── recommendations.py
│   │   │   └── executive.py
│   │   ├── core/          # Config, DB, LLM clients
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   └── llm.py
│   │   ├── engines/       # Core business logic
│   │   │   ├── discovery.py    # Adaptive question engine
│   │   │   ├── gap_analysis.py # Deterministic gap scoring
│   │   │   └── executive.py    # Summary generation
│   │   ├── mcp/           # MCP tool definitions
│   │   │   └── tools.py
│   │   ├── rag/           # RAG pipeline
│   │   │   ├── embeddings.py
│   │   │   └── retrieval.py
│   │   └── models/        # Pydantic data models
│   │       └── schemas.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/    # Chat, GapDashboard, VendorCard, etc.
│   │   ├── pages/         # Discovery, Analysis, Recommendations
│   │   ├── hooks/         # useDiscovery, useGapAnalysis
│   │   └── lib/           # API client, utils
│   ├── package.json
│   └── index.html
├── data/
│   ├── vendor_cards/      # Vendor capability JSON files
│   ├── frameworks/        # CIS, NIST, SOC2 control mappings
│   └── scenarios/         # Prebuilt customer scenarios
├── docs/
│   └── ARCHITECTURE.md    # This file
├── docker-compose.yml
├── .env.example
└── README.md
```
