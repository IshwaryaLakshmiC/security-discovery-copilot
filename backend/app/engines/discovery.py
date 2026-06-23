"""
Discovery Engine — the heart of the SE workflow simulation.

This encodes real SE discovery methodology:
- Domain-aware adaptive questioning
- Gap surfacing through follow-up
- Confidence tracking per domain
- Structured entity extraction
"""

import json
from typing import AsyncGenerator
from app.core.llm import get_llm_client
from app.models.schemas import ExtractedEntities, Message

# The SE methodology system prompt — this is where domain expertise lives
DISCOVERY_SYSTEM_PROMPT = """You are a world-class Solutions Engineer at a leading cybersecurity company.
You are conducting a discovery call with a potential enterprise customer.

Your goal is to understand their security environment deeply enough to recommend a solution architecture.

## Your discovery methodology

### Phase 1: Establish context (first 2-3 questions)
- Company size, industry, growth stage
- Primary cloud/infrastructure environment
- Current security maturity (inferred, not asked directly)

### Phase 2: Domain-specific deep dives
Probe each domain they mention. Do NOT ask about all domains at once.

**IAM/Identity signals:**
- Tools deployed (Okta, Azure AD, Ping, AD)
- Provisioning: automated SCIM or manual?
- Application federation %
- Privileged access management
- MFA coverage and strength
- Joiner/Mover/Leaver process

**Cloud Security signals:**
- Cloud platforms (AWS/Azure/GCP/hybrid)
- Shared responsibility understanding
- Cloud security tooling (CSPM, CWPP)
- IaC security (Terraform drift, misconfig)
- Encryption and key management

**Zero Trust signals:**
- VPN dependency
- Network segmentation approach
- BYOD/managed device ratio
- Conditional access maturity

**Privileged Access signals:**
- Admin account management
- Break-glass accounts
- Privileged session recording
- Just-in-time access

**Compliance signals:**
- Active compliance requirements
- Audit history
- Evidence collection process
- Audit fatigue

### Phase 3: Gap surfacing
When a customer mentions a tool, ask about its coverage:
- "You mentioned Okta — is lifecycle management automated end-to-end?"
- "You use AWS — do you have a CSPM tool scanning for misconfigurations?"
- "You have AD on-prem — how are you syncing to cloud identity?"

### Phase 4: Business context
- What's driving this initiative? (Audit? Incident? Board pressure? M&A?)
- Timeline and urgency
- Internal security team size and capability
- Budget posture (open-ended, not asking numbers)

## Rules

1. Ask ONE question at a time. Never list multiple questions.
2. Adapt based on their answers. Never follow a script.
3. If they give a shallow answer, probe deeper before moving on.
4. If they give a detailed technical answer, match their depth.
5. Surface gaps naturally through questions, not statements.
6. After 8-12 exchanges, you should have enough to analyse.
7. When ready to move to analysis, say: "Thank you — I have a good picture now. Let me analyse what you've shared and identify the key gaps and recommendations."

## Domain confidence tracking (internal)
Track confidence 0-1 per domain. Move on when confidence > 0.7.
Domains: iam, cloud, zerotrust, pam, endpoint, compliance, network

Begin with a warm, professional opening. Ask your first question."""


EXTRACTION_SYSTEM_PROMPT = """You are a security architecture analyst.
Extract structured information from this discovery conversation.

Return ONLY valid JSON matching this schema exactly:
{
  "identity_tools": ["okta", "azure_ad"],
  "cloud_platforms": ["aws", "azure"],
  "security_tools": ["crowdstrike", "splunk"],
  "network_tools": ["zscaler", "palo_alto"],
  "raw_gaps": ["no scim automation", "manual deprovisioning", "no mfa on 40% of users"],
  "compliance_requirements": ["soc2", "hipaa"],
  "employee_count": 500,
  "industry": "fintech",
  "it_maturity": "medium",
  "architecture_type": "hybrid",
  "domain_confidence": {
    "iam": 0.9,
    "cloud": 0.7,
    "zerotrust": 0.4,
    "pam": 0.8,
    "compliance": 0.9
  }
}

Be conservative. Only include what was explicitly mentioned or clearly implied.
Return null for unknown fields, empty arrays for unknown lists."""


class DiscoveryEngine:

    def __init__(self):
        self.llm = get_llm_client()

    async def stream_response(
        self,
        messages: list[Message],
        context: dict = None
    ) -> AsyncGenerator[str, None]:
        """Stream adaptive discovery question/response"""

        # Build message history for LLM
        llm_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
        ]

        # Inject context if available (company name, industry, scenario)
        system = DISCOVERY_SYSTEM_PROMPT
        if context:
            context_str = "\n\n## Session context\n"
            if context.get("company_name"):
                context_str += f"Company: {context['company_name']}\n"
            if context.get("industry"):
                context_str += f"Industry: {context['industry']}\n"
            if context.get("scenario"):
                context_str += f"Scenario hint: {context['scenario']}\n"
            system = DISCOVERY_SYSTEM_PROMPT + context_str

        async for chunk in self.llm.stream(system, llm_messages):
            yield chunk

    async def extract_entities(self, transcript: list[Message]) -> ExtractedEntities:
        """Extract structured entities from discovery transcript"""

        # Build transcript text
        transcript_text = "\n".join([
            f"{m.role.upper()}: {m.content}"
            for m in transcript
        ])

        messages = [{
            "role": "user",
            "content": f"Extract structured information from this discovery call transcript:\n\n{transcript_text}"
        }]

        response = await self.llm.complete(EXTRACTION_SYSTEM_PROMPT, messages, max_tokens=1000)

        try:
            data = self._extract_json_object(response)
            return ExtractedEntities(**data)
        except Exception as e:
            print(f"Entity extraction parse error: {e} | raw response: {response[:500]}")
            return ExtractedEntities()

    def _extract_json_object(self, text: str) -> dict:
        """Robustly extract a JSON object from an LLM response that may include
        markdown fences, leading/trailing prose, or other non-JSON wrapper text.
        Different providers (Claude, Llama via Groq, Gemini) format this differently."""
        cleaned = text.strip()

        # Strip markdown code fences if present
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1]
        if "```" in cleaned:
            cleaned = cleaned.split("```")[0] if cleaned.strip().startswith("```") is False else cleaned
            cleaned = cleaned.replace("```", "")

        # Find the first { and last } to strip any prose wrapper
        # e.g. "Here's the extracted information:\n\n{...}\n\nLet me know if..."
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError(f"No JSON object found in response")

        json_str = cleaned[start:end + 1]
        return json.loads(json_str)

    def is_discovery_complete(self, messages: list[Message]) -> bool:
        """Check if the assistant has signalled completion"""
        if not messages:
            return False
        last_assistant = next(
            (m for m in reversed(messages) if m.role == "assistant"),
            None
        )
        if not last_assistant:
            return False
        completion_signals = [
            "let me analyse",
            "i have a good picture",
            "good understanding now",
            "move to the analysis",
            "based on what you've shared"
        ]
        content_lower = last_assistant.content.lower()
        return any(signal in content_lower for signal in completion_signals)
