"""
Gap Analysis Engine — DETERMINISTIC.

This is NOT AI. Gap severity is determined by lookup tables
against real compliance frameworks and security best practices.

AI hallucinating gap scores would destroy credibility with
security-literate customers (CISOs, security architects).
"""

from app.models.schemas import (
    Gap, MaturityScore, MaturityLevel, GapAnalysis,
    Severity, Domain, ExtractedEntities
)
from datetime import datetime
import uuid


# ── Gap definition library ─────────────────────────────────────
# Each gap: id, title, domain, severity, framework refs, remediation effort

GAP_LIBRARY = {
    "no_scim_automation": Gap(
        id="no_scim_automation",
        title="No automated user provisioning/deprovisioning (SCIM)",
        description="User lifecycle is managed manually, creating orphaned accounts and delayed deprovisioning risk.",
        domain=Domain.IAM,
        severity=Severity.HIGH,
        business_impact="Terminated employees may retain system access. Average time to deprovision manually: 3-5 days. Each day is a potential breach window.",
        framework_references=["SOC2 CC6.2", "ISO27001 A.9.2.1", "CIS 5.2"],
        affected_resources=["Identity Provider", "SaaS Applications"],
        remediation_effort="medium",
        estimated_days=30,
    ),
    "low_mfa_coverage": Gap(
        id="low_mfa_coverage",
        title="MFA not enforced for all users",
        description="A significant percentage of user accounts access corporate systems without multi-factor authentication.",
        domain=Domain.IAM,
        severity=Severity.CRITICAL,
        business_impact="Credential theft is the #1 initial access vector. Without MFA, a single phished password compromises the account. 99.9% of account compromise attacks are blocked by MFA (Microsoft, 2023).",
        framework_references=["CIS 6.3", "NIST SP 800-63B", "SOC2 CC6.1", "ISO27001 A.9.4.2"],
        affected_resources=["All user accounts"],
        remediation_effort="low",
        estimated_days=14,
    ),
    "no_pam": Gap(
        id="no_pam",
        title="No Privileged Access Management (PAM) controls",
        description="Privileged and administrative accounts are not managed through a PAM solution. Shared admin credentials, no session recording, no just-in-time access.",
        domain=Domain.PAM,
        severity=Severity.CRITICAL,
        business_impact="Privileged accounts are the primary target in 74% of breaches (Verizon DBIR). Without PAM, attackers who gain any privileged credential have unlimited persistence.",
        framework_references=["CIS 5.4", "NIST SP 800-53 AC-2", "SOC2 CC6.3", "ISO27001 A.9.2.3"],
        affected_resources=["Admin accounts", "Service accounts", "Cloud root accounts"],
        remediation_effort="high",
        estimated_days=90,
    ),
    "vpn_dependency": Gap(
        id="vpn_dependency",
        title="VPN-based remote access without Zero Trust controls",
        description="Remote workforce accesses internal resources through legacy VPN, granting broad network access rather than application-specific access.",
        domain=Domain.ZEROTRUST,
        severity=Severity.HIGH,
        business_impact="VPN compromise grants attacker network-level access. Lateral movement from a single compromised endpoint can reach all internal systems. Zero Trust reduces blast radius to individual applications.",
        framework_references=["NIST SP 800-207", "CIS 12.7", "ISO27001 A.13.1.3"],
        affected_resources=["Remote access infrastructure", "Internal applications"],
        remediation_effort="high",
        estimated_days=120,
    ),
    "no_cspm": Gap(
        id="no_cspm",
        title="No Cloud Security Posture Management (CSPM)",
        description="Cloud infrastructure is not continuously monitored for misconfigurations, exposed resources, or policy violations.",
        domain=Domain.CLOUD,
        severity=Severity.HIGH,
        business_impact="Misconfigured cloud storage is responsible for the majority of cloud data breaches. Without CSPM, misconfigurations persist undetected. Average time to detect cloud misconfiguration without tooling: 197 days (IBM Cost of a Data Breach).",
        framework_references=["CIS AWS Benchmark", "SOC2 CC7.1", "ISO27001 A.12.6.1"],
        affected_resources=["AWS/Azure/GCP resources"],
        remediation_effort="medium",
        estimated_days=45,
    ),
    "no_low_app_federation": Gap(
        id="no_low_app_federation",
        title="Low application federation rate — password vaulting prevalent",
        description="Less than 50% of applications are federated via SSO. Remaining apps use password vaulting or local credentials.",
        domain=Domain.IAM,
        severity=Severity.MEDIUM,
        business_impact="Password-vaulted applications are not subject to central MFA policies and conditional access. Compromised vault credentials expose all vaulted applications simultaneously.",
        framework_references=["CIS 12.1", "SOC2 CC6.1", "NIST SP 800-63C"],
        affected_resources=["SaaS applications", "Internal applications"],
        remediation_effort="high",
        estimated_days=180,
    ),
    "no_cloudtrail": Gap(
        id="no_cloudtrail",
        title="Incomplete audit logging in cloud environment",
        description="Cloud API activity is not fully logged across all regions and services. Gaps in CloudTrail/Activity Log coverage.",
        domain=Domain.CLOUD,
        severity=Severity.HIGH,
        business_impact="Without complete audit logs, incident investigation is blind. Compliance frameworks (SOC2, ISO27001) require demonstrable logging. Forensic investigation post-breach is severely hampered.",
        framework_references=["CIS 3.1", "SOC2 CC7.2", "ISO27001 A.12.4.1", "AWS CIS Benchmark 3.x"],
        affected_resources=["AWS CloudTrail", "Azure Activity Log", "GCP Cloud Audit Logs"],
        remediation_effort="low",
        estimated_days=7,
    ),
    "no_iga": Gap(
        id="no_iga",
        title="No Identity Governance and Administration (IGA)",
        description="No formal access review process, role mining, or entitlement certification. Access accumulates over time without review.",
        domain=Domain.GOVERNANCE,
        severity=Severity.HIGH,
        business_impact="Access creep: users accumulate permissions over time without review. Insider threat risk increases. SOC2 and ISO27001 require periodic access reviews. Failed audits result in compliance failures.",
        framework_references=["SOC2 CC6.2", "ISO27001 A.9.2.5", "SOC2 CC6.3"],
        affected_resources=["All user accounts", "All applications"],
        remediation_effort="high",
        estimated_days=120,
    ),
    "shared_admin_credentials": Gap(
        id="shared_admin_credentials",
        title="Shared administrative credentials in use",
        description="Multiple administrators share the same credentials for privileged systems, preventing individual accountability.",
        domain=Domain.PAM,
        severity=Severity.CRITICAL,
        business_impact="Shared credentials eliminate individual accountability. When a breach occurs, there is no way to determine which individual was responsible for privileged actions. This is a direct SOC2 and ISO27001 failure.",
        framework_references=["CIS 5.1", "SOC2 CC6.3", "ISO27001 A.9.4.2", "NIST SP 800-53 IA-2"],
        affected_resources=["Admin accounts", "Network devices", "Cloud root accounts"],
        remediation_effort="medium",
        estimated_days=30,
    ),
    "no_edr": Gap(
        id="no_edr",
        title="No Endpoint Detection and Response (EDR)",
        description="Endpoints are protected by traditional antivirus only, without behavioural detection or threat hunting capabilities.",
        domain=Domain.ENDPOINT,
        severity=Severity.HIGH,
        business_impact="Traditional AV misses 40-70% of modern malware (Ponemon). EDR provides behavioural detection, attack chain visibility, and rapid containment. Without EDR, dwell time is measured in months.",
        framework_references=["CIS 10.1", "NIST SP 800-53 SI-3", "SOC2 CC7.1"],
        affected_resources=["All endpoints", "Servers"],
        remediation_effort="medium",
        estimated_days=45,
    ),
    "phi_data_exposure": Gap(
        id="phi_data_exposure",
        title="PHI/PII data without adequate access controls and encryption",
        description="Sensitive health information does not have adequate access logging, encryption at rest, or access controls meeting HIPAA requirements.",
        domain=Domain.DATA,
        severity=Severity.CRITICAL,
        business_impact="HIPAA violation fines range from $100 to $50,000 per violation. Average healthcare data breach costs $10.9M (IBM 2023). PHI exposure triggers mandatory breach notification.",
        framework_references=["HIPAA Security Rule 45 CFR 164.312", "NIST SP 800-66", "CIS 3.11"],
        affected_resources=["Patient data stores", "EHR systems", "Backup systems"],
        remediation_effort="high",
        estimated_days=90,
    ),
}


# ── Gap detection rules ────────────────────────────────────────
# Maps extracted entities → detected gaps

def detect_gaps(entities: ExtractedEntities) -> list[Gap]:
    """Deterministic gap detection from extracted entities"""
    detected = []

def _mentions_any(raw_gaps: list[str], keywords: list[str]) -> bool:
    """Proper substring matching -- checks if ANY keyword appears as a
    substring of ANY raw_gap phrase. The previous implementation used
    `keyword in raw_gaps`, which checks for exact list membership, not
    substring matching -- so 'no scim' never matched 'no scim automation'
    even though one obviously implies the other. This was the root cause
    of gap analysis silently falling through to generic defaults (CSPM,
    EDR) regardless of what was actually discussed in the conversation."""
    haystack = " | ".join(g.lower() for g in raw_gaps)
    return any(kw.lower() in haystack for kw in keywords)


def detect_gaps(entities: ExtractedEntities) -> list[Gap]:
    """Deterministic gap detection from extracted entities"""
    detected = []

    # SCIM / provisioning gap -- broadened to match how customers actually
    # describe this in conversation, not just security-jargon phrasing
    if "okta" in entities.identity_tools or "azure_ad" in entities.identity_tools:
        if _mentions_any(entities.raw_gaps, [
            "manual", "no scim", "scim", "provisioning", "onboarding",
            "no automation", "deprovisioning", "offboarding", "manually",
            "go in and set up", "kill their access", "days to", "days for"
        ]):
            detected.append(GAP_LIBRARY["no_scim_automation"])

    # MFA gap -- broadened to catch "don't know our coverage" framing,
    # which is itself a finding (no governance visibility), not just
    # explicit "no MFA" statements
    if _mentions_any(entities.raw_gaps, [
        "no mfa", "mfa not enforced", "partial mfa", "sms mfa", "no 2fa",
        "mfa coverage", "couldn't give you an accurate", "don't have visibility",
        "no visibility into", "uncomfortable to admit", "near-miss",
        "credential stuffing", "credential-stuffing"
    ]):
        detected.append(GAP_LIBRARY["low_mfa_coverage"])

    # PAM gap
    if _mentions_any(entities.raw_gaps, [
        "no pam", "shared admin", "no privileged access", "no session recording",
        "shared credentials", "no jit", "no just-in-time", "standing access",
        "domain admin", "global admin", "no pim", "unconfigured"
    ]):
        if _mentions_any(entities.raw_gaps, ["shared credentials", "shared admin"]):
            detected.append(GAP_LIBRARY["shared_admin_credentials"])
        else:
            detected.append(GAP_LIBRARY["no_pam"])

    # VPN / Zero Trust gap
    if _mentions_any(entities.raw_gaps, [
        "vpn", "no zero trust", "no ztna", "legacy vpn", "vpn dependent", "vpn-dependent"
    ]):
        detected.append(GAP_LIBRARY["vpn_dependency"])

    # CSPM gap -- only fires if cloud platforms were actually discussed
    # AND no CSPM/security tooling was named, not as a blanket default
    if entities.cloud_platforms and not any(
        t in entities.security_tools for t in ["wiz", "prisma", "lacework", "orca", "defender"]
    ):
        detected.append(GAP_LIBRARY["no_cspm"])

    # Low app federation -- broadened to match the actual percentage-based
    # framing customers use ("40% federated", "the rest hang off on-prem")
    if _mentions_any(entities.raw_gaps, [
        "password vault", "low federation", "password vaulting", "manual password",
        "federated", "federation", "% federated", "own logins", "standalone",
        "not connected", "hang off on-prem"
    ]):
        detected.append(GAP_LIBRARY["no_low_app_federation"])

    # Audit logging gap
    if _mentions_any(entities.raw_gaps, [
        "no cloudtrail", "no audit log", "incomplete logging", "no logging"
    ]):
        detected.append(GAP_LIBRARY["no_cloudtrail"])

    # IGA gap
    if _mentions_any(entities.raw_gaps, [
        "no access review", "no iga", "no governance", "access creep",
        "no certification", "manual access review"
    ]):
        detected.append(GAP_LIBRARY["no_iga"])

    # EDR gap -- now requires endpoint security to have been discussed at
    # all (positive evidence of relevance), rather than firing by default
    # whenever no specific EDR vendor happens to be named. Previously this
    # fired unconditionally on every transcript regardless of topic.
    endpoint_discussed = _mentions_any(entities.raw_gaps, [
        "endpoint", "antivirus", "edr", "device", "laptop", "workstation"
    ])
    if endpoint_discussed and not any(t in entities.security_tools for t in [
        "crowdstrike", "sentinelone", "defender", "carbon black", "edr"
    ]):
        detected.append(GAP_LIBRARY["no_edr"])

    # PHI gap (healthcare)
    if entities.industry == "healthcare" and any(
        r in entities.compliance_requirements for r in ["hipaa"]
    ):
        detected.append(GAP_LIBRARY["phi_data_exposure"])

    # Deduplicate
    seen = set()
    unique = []
    for g in detected:
        if g.id not in seen:
            seen.add(g.id)
            unique.append(g)

    return unique


# ── Maturity scoring ───────────────────────────────────────────

def score_maturity(entities: ExtractedEntities) -> dict[str, MaturityScore]:
    scores = {}

    # IAM maturity -- now reads the SAME detected gaps as detect_gaps(),
    # rather than re-deriving (incorrectly) from raw string checks against
    # gap IDs that never appear in raw_gaps in the first place.
    detected_gap_ids = {g.id for g in detect_gaps(entities)}

    iam_score = 1
    if entities.identity_tools:
        iam_score = 2
    if "okta" in entities.identity_tools or "azure_ad" in entities.identity_tools:
        iam_score = 3
    if iam_score == 3 and "no_scim_automation" not in detected_gap_ids:
        iam_score = 4
    if iam_score >= 3 and "low_mfa_coverage" not in detected_gap_ids:
        iam_score = min(5, iam_score + 1)

    iam_evidence = entities.identity_tools.copy() if entities.identity_tools else []
    if "no_scim_automation" in detected_gap_ids:
        iam_evidence.append("manual/inconsistent provisioning identified in discovery")
    if "low_mfa_coverage" in detected_gap_ids:
        iam_evidence.append("MFA coverage gap or visibility gap identified in discovery")

    scores["iam"] = MaturityScore(
        domain=Domain.IAM,
        score=MaturityLevel(iam_score),
        rationale=f"Identity tooling present: {', '.join(entities.identity_tools) or 'none detected'}"
                  f"{'. Provisioning is manual/inconsistent.' if 'no_scim_automation' in detected_gap_ids else ''}"
                  f"{'. MFA coverage has gaps or no visibility.' if 'low_mfa_coverage' in detected_gap_ids else ''}",
        evidence=iam_evidence
    )

    # Cloud security maturity
    cloud_score = 1
    if entities.cloud_platforms:
        cloud_score = 2
    if any(t in entities.security_tools for t in ["wiz", "prisma", "lacework", "orca"]):
        cloud_score = 4
    if "cloudtrail" in " ".join(entities.security_tools):
        cloud_score = min(5, cloud_score + 1)

    scores["cloud"] = MaturityScore(
        domain=Domain.CLOUD,
        score=MaturityLevel(cloud_score),
        rationale=f"Cloud platforms: {', '.join(entities.cloud_platforms) or 'none'}. CSPM: {'present' if cloud_score >= 4 else 'absent'}",
        evidence=entities.cloud_platforms
    )

    # Zero Trust maturity
    zt_score = 1
    if any(t in entities.network_tools for t in ["zscaler", "cloudflare", "netskope"]):
        zt_score = 3
    if "vpn_dependency" in detected_gap_ids:
        zt_score = max(1, zt_score - 1)

    scores["zerotrust"] = MaturityScore(
        domain=Domain.ZEROTRUST,
        score=MaturityLevel(zt_score),
        rationale=f"ZTNA tooling: {', '.join(entities.network_tools) or 'none'}"
                  f"{'. VPN-dependent access model identified.' if 'vpn_dependency' in detected_gap_ids else ''}",
        evidence=entities.network_tools
    )

    return scores


def get_overall_risk(gaps: list[Gap]) -> Severity:
    if any(g.severity == Severity.CRITICAL for g in gaps):
        return Severity.CRITICAL
    if any(g.severity == Severity.HIGH for g in gaps):
        return Severity.HIGH
    if any(g.severity == Severity.MEDIUM for g in gaps):
        return Severity.MEDIUM
    return Severity.LOW


def get_compliance_status(entities: ExtractedEntities, gaps: list[Gap]) -> dict[str, str]:
    status = {}
    gap_ids = {g.id for g in gaps}

    if "soc2" in entities.compliance_requirements:
        failing = [g for g in gaps if "SOC2" in " ".join(g.framework_references)]
        status["SOC2"] = "fail" if len(failing) >= 3 else "partial" if failing else "pass"

    if "hipaa" in entities.compliance_requirements:
        hipaa_gaps = [g for g in gaps if "HIPAA" in " ".join(g.framework_references)]
        status["HIPAA"] = "fail" if hipaa_gaps else "partial"

    if "iso27001" in entities.compliance_requirements:
        iso_gaps = [g for g in gaps if "ISO27001" in " ".join(g.framework_references)]
        status["ISO27001"] = "fail" if len(iso_gaps) >= 3 else "partial" if iso_gaps else "pass"

    return status


def run_gap_analysis(entities: ExtractedEntities, session_id: str) -> GapAnalysis:
    gaps = detect_gaps(entities)
    maturity = score_maturity(entities)
    overall_risk = get_overall_risk(gaps)
    compliance = get_compliance_status(entities, gaps)

    # Top 3 priorities: critical first, then high, by remediation effort (low effort = higher priority)
    effort_order = {"low": 0, "medium": 1, "high": 2}
    severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
    sorted_gaps = sorted(gaps, key=lambda g: (severity_order[g.severity], effort_order[g.remediation_effort]))
    top_3 = [g.id for g in sorted_gaps[:3]]

    return GapAnalysis(
        session_id=session_id,
        gaps=gaps,
        maturity_scores=maturity,
        overall_risk_level=overall_risk,
        top_3_priorities=top_3,
        compliance_status=compliance,
        generated_at=datetime.utcnow()
    )
