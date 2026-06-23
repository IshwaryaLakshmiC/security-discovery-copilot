from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Domain(str, Enum):
    IAM = "iam"
    CLOUD = "cloud"
    ZEROTRUST = "zerotrust"
    PAM = "pam"
    ENDPOINT = "endpoint"
    NETWORK = "network"
    DATA = "data"
    GOVERNANCE = "governance"
    COMPLIANCE = "compliance"
    OPERATIONS = "operations"


class MaturityLevel(int, Enum):
    INITIAL = 1      # Ad hoc, no formal process
    DEVELOPING = 2   # Some processes, inconsistent
    DEFINED = 3      # Documented, consistently applied
    MANAGED = 4      # Measured and controlled
    OPTIMISING = 5   # Continuous improvement


# ── Session ───────────────────────────────────────────────────

class SessionCreate(BaseModel):
    scenario_id: Optional[str] = None
    company_name: Optional[str] = "Prospect"
    industry: Optional[str] = None
    company_size: Optional[str] = None


class Session(BaseModel):
    id: str
    company_name: str
    industry: Optional[str]
    company_size: Optional[str]
    scenario_id: Optional[str]
    status: str = "discovery"  # discovery|analysis|recommendations|complete
    created_at: datetime
    updated_at: datetime


# ── Discovery ─────────────────────────────────────────────────

class Message(BaseModel):
    role: str  # user | assistant
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DiscoveryMessage(BaseModel):
    session_id: str
    content: str


class DiscoveryResponse(BaseModel):
    message: str
    extracted_entities: Optional[Dict[str, Any]] = None
    domains_covered: Optional[List[str]] = None
    discovery_complete: bool = False


class ExtractedEntities(BaseModel):
    """Structured data extracted from discovery conversation"""
    # Tools and vendors already in use
    identity_tools: List[str] = []        # okta, azure_ad, ping, etc.
    cloud_platforms: List[str] = []       # aws, azure, gcp
    security_tools: List[str] = []        # crowdstrike, splunk, etc.
    network_tools: List[str] = []         # zscaler, palo_alto, etc.

    # Identified gaps (raw strings, scored later)
    raw_gaps: List[str] = []

    # Context
    compliance_requirements: List[str] = []  # soc2, hipaa, pci, iso27001
    employee_count: Optional[int] = None
    industry: Optional[str] = None
    it_maturity: Optional[str] = None       # low|medium|high (inferred)
    architecture_type: Optional[str] = None # cloud|hybrid|on-prem

    # Domain confidence (0.0 - 1.0)
    domain_confidence: Dict[str, Optional[float]] = {}


# ── Gap Analysis ──────────────────────────────────────────────

class Gap(BaseModel):
    id: str
    title: str
    description: str
    domain: Domain
    severity: Severity
    business_impact: str
    framework_references: List[str] = []   # "CIS 1.10", "SOC2 CC6.1"
    affected_resources: List[str] = []
    remediation_effort: str               # low|medium|high
    estimated_days: Optional[int] = None


class MaturityScore(BaseModel):
    domain: Domain
    score: MaturityLevel
    rationale: str
    evidence: List[str] = []             # From discovery transcript


class GapAnalysis(BaseModel):
    session_id: str
    gaps: List[Gap]
    maturity_scores: Dict[str, MaturityScore]
    overall_risk_level: Severity
    top_3_priorities: List[str]          # Gap IDs
    compliance_status: Dict[str, str]    # framework -> pass|partial|fail
    generated_at: datetime


# ── Vendor Recommendations ────────────────────────────────────

class VendorCapability(BaseModel):
    vendor: str
    domain: str
    capability: str
    description: str
    fits_when: str
    not_fits_when: str
    cost_tier: str                       # startup|mid-market|enterprise
    implementation_complexity: str       # low|medium|high


class VendorRecommendation(BaseModel):
    vendor: str
    product: str
    domain: Domain
    addresses_gaps: List[str]            # Gap IDs this addresses
    fit_score: float                     # 0.0 - 1.0
    why_it_fits: str
    why_it_may_not_fit: str
    cost_consideration: str
    operational_consideration: str
    implementation_phase: int            # 1, 2, or 3


class RecommendationSet(BaseModel):
    session_id: str
    recommendations: List[VendorRecommendation]
    architecture_notes: str
    implementation_roadmap: List[Dict[str, Any]]
    generated_at: datetime


# ── Executive Summary ─────────────────────────────────────────

class RoadmapPhase(BaseModel):
    phase: int
    title: str
    duration: str
    objectives: List[str]
    vendors: List[str]
    estimated_cost_range: str
    success_metrics: List[str]


class ExecutiveSummary(BaseModel):
    session_id: str
    company_name: str
    date: datetime
    executive_overview: str              # 2-3 sentence summary
    key_risks: List[Dict[str, str]]      # risk, business_impact, urgency
    current_state_summary: str
    recommended_architecture: str
    roadmap: List[RoadmapPhase]
    top_vendor_recommendations: List[str]
    estimated_total_investment: str
    next_steps: List[str]
    generated_at: datetime


# ── MCP Tool Schemas ──────────────────────────────────────────

class VendorSearchRequest(BaseModel):
    query: str
    domain: Optional[str] = None
    company_size: Optional[str] = None
    industry: Optional[str] = None
    top_k: int = 5


class ComplianceControlRequest(BaseModel):
    framework: str   # cis|nist_csf|soc2|iso27001|hipaa|pci
    category: str    # iam|network|data|ops|incident


class MaturityScoreRequest(BaseModel):
    domain: str
    answers: Dict[str, Any]


class GapSeverityRequest(BaseModel):
    gap_type: str
    context: Dict[str, Any]
