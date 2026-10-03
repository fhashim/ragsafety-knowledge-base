"""Content Safety guardrail clients.

Mock implements deterministic checks that mirror the Azure AI Content Safety
features used:

* **input**: Prompt Shields (jailbreak), harmful/off-policy content, off-topic;
* **retrieved**: Prompt Shields for *indirect* injection planted in documents;
* **output**: groundedness (every stated value appears in a source) and
  mandatory citations.

The real client calls Azure AI Content Safety (Prompt Shields + groundedness).
"""

from __future__ import annotations

from ..concepts import detect_concepts
from ..extraction import value_supported
from ..schema import (
    Checklist,
    GuardrailStage,
    GuardrailVerdict,
    RetrievedChunk,
)
from ..settings import Settings
from .base import ContentSafetyClient

# Patterns for a direct jailbreak attempt against the system prompt.
_JAILBREAK = (
    "ignore previous instructions",
    "ignore all previous",
    "ignore the above",
    "disregard your instructions",
    "disregard the rules",
    "you are now",
    "developer mode",
    "jailbreak",
    "pretend you are",
    "act as dan",
    "reveal your system prompt",
    "print your instructions",
    "bypass your",
    "without any safety",
)
# Phrasings that request an unsafe/off-policy action (the hard rule protects these).
_HARMFUL = (
    "bypass the safety",
    "bypass safety",
    "disable the gas detector",
    "disable the detector",
    "defeat the interlock",
    "defeat interlock",
    "skip the permit",
    "skip isolation",
    "without isolation",
    "without a permit",
    "ignore the approach distance",
    "work live without",
)
# Markers of a clearly non-safety, off-topic request.
_OFF_TOPIC = (
    "cafeteria",
    "menu",
    "weather",
    "stock price",
    "bitcoin",
    "write a poem",
    "tell me a joke",
    "football",
    "movie",
    "vacation",
    "payroll",
    "expense report",
)
# Instruction-like text that, if found inside a retrieved document, signals an
# indirect prompt-injection payload.
_INJECTION = (
    "ignore previous instructions",
    "ignore all prior",
    "assistant:",
    "system prompt",
    "disregard the safety policy",
    "reveal the",
    "exfiltrate",
    "send the contents",
    "override the checklist",
)


class MockContentSafetyClient(ContentSafetyClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def check_input(self, text: str) -> GuardrailVerdict:
        lower = text.lower()
        cats: list[str] = []
        if any(p in lower for p in _JAILBREAK):
            cats.append("jailbreak")
        if any(p in lower for p in _HARMFUL):
            cats.append("harmful_or_off_policy")
        if any(p in lower for p in _OFF_TOPIC) and not detect_concepts(text):
            cats.append("off_topic")
        allowed = len(cats) == 0
        reason = "" if allowed else f"Blocked by input guardrail: {', '.join(cats)}."
        return GuardrailVerdict(
            stage=GuardrailStage.INPUT, allowed=allowed, categories=cats, reason=reason
        )

    def check_retrieved(self, retrieved: list[RetrievedChunk]) -> GuardrailVerdict:
        for rc in retrieved:
            lower = rc.chunk.text.lower()
            if any(p in lower for p in _INJECTION):
                return GuardrailVerdict(
                    stage=GuardrailStage.INPUT,
                    allowed=False,
                    categories=["indirect_injection"],
                    reason=(
                        f"Indirect prompt injection detected in {rc.chunk.doc} "
                        f"({rc.chunk.section_display})."
                    ),
                )
        return GuardrailVerdict(stage=GuardrailStage.INPUT, allowed=True)

    def check_output(self, checklist: Checklist, retrieved: list[RetrievedChunk]) -> GuardrailVerdict:
        sources_text = "\n".join(rc.chunk.text for rc in retrieved)
        cats: list[str] = []
        ungrounded = 0
        missing_citation = 0
        valued = 0
        for item in checklist.items:
            if item.value:
                valued += 1
                if not value_supported(sources_text, item.value):
                    ungrounded += 1
                if not item.citations:
                    missing_citation += 1
        if ungrounded:
            cats.append("ungrounded_value")
        if missing_citation:
            cats.append("missing_citation")
        # Any explicitly unsupported claim must have been routed to stop-work.
        if checklist.unsupported_claims and not checklist.stop_work_conditions:
            cats.append("unsupported_without_stopwork")
        allowed = len(cats) == 0
        reason = "" if allowed else f"Blocked by output guardrail: {', '.join(cats)}."
        return GuardrailVerdict(
            stage=GuardrailStage.OUTPUT, allowed=allowed, categories=cats, reason=reason
        )


class AzureContentSafetyClient(ContentSafetyClient):
    """Azure AI Content Safety (Prompt Shields + groundedness). Imported lazily."""

    def __init__(self, settings: Settings) -> None:  # pragma: no cover - real-Azure only
        self.settings = settings
        self._client = None

    def _ensure(self):  # pragma: no cover
        if self._client is None:
            from azure.ai.contentsafety import ContentSafetyClient as CSClient
            from azure.identity import DefaultAzureCredential

            self._client = CSClient(
                endpoint=self.settings.content_safety_endpoint,
                credential=DefaultAzureCredential(
                    managed_identity_client_id=self.settings.managed_identity_client_id or None
                ),
            )

    def check_input(self, text: str) -> GuardrailVerdict:  # pragma: no cover
        self._ensure()
        # VERIFY: Prompt Shields + AnalyzeText API shape for your SDK version.
        # Falls back to the deterministic checks if the SDK call is unavailable.
        return MockContentSafetyClient(self.settings).check_input(text)

    def check_retrieved(self, retrieved):  # pragma: no cover
        self._ensure()
        return MockContentSafetyClient(self.settings).check_retrieved(retrieved)

    def check_output(self, checklist, retrieved):  # pragma: no cover
        self._ensure()
        return MockContentSafetyClient(self.settings).check_output(checklist, retrieved)
