"""Chat clients.

``MockChatClient`` is rule-based and deterministic:

* **rewrite** expands shorthand/acronyms and extracts task/equipment/voltage/
  location slots with small regexes;
* **clarify** asks a question when the hazard cannot be scoped (no equipment and
  no voltage);
* **generate** builds a checklist *only* from values extracted from retrieved
  chunks (``extraction.extract_facts``), so it can never invent a distance or
  threshold — a missing requested value becomes a ``stop_work`` instruction.

``AzureChatClient`` calls the Foundry chat deployments with prompts that encode
the same rules and a strict JSON schema.
"""

from __future__ import annotations

import json
import re

from ..concepts import detect_concepts
from ..extraction import extract_facts, find_fact
from ..schema import (
    Checklist,
    ChecklistCategory,
    ChecklistItem,
    Citation,
    ClarificationRequest,
    Domain,
    RetrievedChunk,
    RewriteResult,
    Slots,
    SourceType,
    TokenUsage,
    WebResult,
)
from ..settings import Settings
from ..util import count_tokens
from .base import ChatClient

# --- rewrite dictionaries --------------------------------------------------- #
_SHORTHAND = {
    "2moro": "tomorrow",
    "2mrw": "tomorrow",
    "2day": "today",
    "wats": "what is",
    "wat": "what",
    "w/": "with",
    "pls": "please",
    "plz": "please",
    "u": "you",
    "r": "are",
    "n": "and",
    "thx": "thanks",
    "gud": "good",
    "fr": "for",
    "nd": "need",
}
_ACRONYMS = {
    "loto": "lockout/tagout (LOTO)",
    "ppe": "PPE (personal protective equipment)",
    "hv": "high voltage (HV)",
    "lv": "low voltage (LV)",
    "lel": "LEL (lower explosive limit)",
    "cs": "confined space",
    "ptw": "permit to work (PTW)",
}
_CODE_RE = re.compile(r"\b(tx|cb|gv|cs)[\-\s]?(\d{1,3})\b", re.IGNORECASE)
_VOLTAGE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?kv\b", re.IGNORECASE)
_SUB_RE = re.compile(r"\bsub(?:station)?\s?(\d+)\b", re.IGNORECASE)
_TASK_VERBS = (
    "replace",
    "repair",
    "inspect",
    "maintain",
    "fix",
    "isolate",
    "install",
    "test",
    "commission",
    "service",
    "work on",
    "clean",
    "tighten",
    "connect",
)
_EQUIPMENT_NOUNS = (
    "conductor",
    "busbar",
    "transformer",
    "breaker",
    "compressor",
    "valve",
    "pipeline",
    "switchgear",
    "line",
)
_MAX_ITEMS = 12


def _normalize_query(query: str) -> str:
    tokens = query.split()
    out = []
    for tok in tokens:
        stripped = tok.strip(".,!?").lower()
        if stripped in _SHORTHAND:
            out.append(_SHORTHAND[stripped])
        else:
            out.append(tok)
    text = " ".join(out)
    # Normalize equipment codes: tx400 -> TX-400
    text = _CODE_RE.sub(lambda m: f"{m.group(1).upper()}-{m.group(2)}", text)
    # Normalize voltage: 11kv -> 11 kV
    text = _VOLTAGE_RE.sub(lambda m: f"{m.group(1)} kV", text)
    # Normalize substation: sub 4 -> substation 4
    text = _SUB_RE.sub(lambda m: f"substation {m.group(1)}", text)
    # Expand acronyms (word-boundary, case-insensitive).
    for acro, full in _ACRONYMS.items():
        text = re.sub(rf"\b{acro}\b", full, text, flags=re.IGNORECASE)
    return text.strip()


def _extract_slots(normalized: str, original: str) -> Slots:
    lower = normalized.lower()
    equipment = None
    code = _CODE_RE.search(normalized)
    if code:
        equipment = f"{code.group(1).upper()}-{code.group(2)}"
    else:
        for noun in _EQUIPMENT_NOUNS:
            if noun in lower:
                equipment = noun
                break
    voltage = None
    volt = _VOLTAGE_RE.search(normalized)
    if volt:
        voltage = f"{volt.group(1)} kV"
    location = None
    sub = _SUB_RE.search(original) or _SUB_RE.search(normalized)
    if sub:
        location = f"substation {sub.group(1)}"
    task = None
    for verb in _TASK_VERBS:
        if verb in lower:
            task = verb
            break
    domain = _infer_domain(lower, equipment)
    return Slots(task=task, equipment=equipment, voltage=voltage, location=location, domain=domain)


# Equipment code prefixes map to a domain (TX transformer / CB breaker = HV;
# GV gas valve / CS compressor station = gas).
_CODE_DOMAIN = {"TX": Domain.ELECTRICAL, "CB": Domain.ELECTRICAL, "GV": Domain.GAS, "CS": Domain.GAS}
_ELECTRICAL_HINTS = (
    "kv",
    "substation",
    "breaker",
    "busbar",
    "arc flash",
    "arc-flash",
    "approach distance",
    "high voltage",
    "switchgear",
    "loto",
    "lockout",
    "energized",
    "energised",
    "conductor",
)
_GAS_HINTS = (
    "gas",
    "pipeline",
    "compressor",
    "%lel",
    "lower explosive limit",
    "methane",
    "exclusion zone",
    "hot work",
    "hot-work",
    "venting",
)


def _infer_domain(lower: str, equipment: str | None) -> Domain | None:
    if equipment:
        prefix = equipment.split("-")[0].upper()
        if prefix in _CODE_DOMAIN:
            return _CODE_DOMAIN[prefix]
    if any(h in lower for h in _ELECTRICAL_HINTS):
        return Domain.ELECTRICAL
    if any(h in lower for h in _GAS_HINTS):
        return Domain.GAS
    return None


class MockChatClient(ChatClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def rewrite(self, query: str) -> tuple[RewriteResult, TokenUsage]:
        normalized = _normalize_query(query)
        slots = _extract_slots(normalized, query)
        usage = TokenUsage(
            model="mock-small",
            deployment=self.settings.chat_small_deployment,
            prompt_tokens=count_tokens(query),
            completion_tokens=count_tokens(normalized),
        )
        return RewriteResult(original_query=query, rewritten_query=normalized, slots=slots), usage

    def clarify(self, rewrite: RewriteResult) -> tuple[ClarificationRequest, TokenUsage]:
        slots = rewrite.slots
        # The request is answerable if it carries ANY concrete handle: a specific
        # equipment code, a voltage, or a recognizable safety concept (gloves,
        # gas detection, lifting, ...). A vague "what do I need for the X job?"
        # with none of these cannot be scoped safely, so we ask one question.
        has_code = bool(slots.equipment and _CODE_RE.search(slots.equipment))
        has_concept = bool(detect_concepts(rewrite.rewritten_query))
        needed = not (has_code or slots.voltage or has_concept)
        missing: list[str] = []
        question = ""
        if needed:
            missing = ["voltage", "task type", "equipment"]
            question = (
                "To give you a safe, specific checklist I need the voltage level "
                "(e.g. 11 kV or 33 kV), the task (e.g. inspect, replace, isolate), "
                "and the equipment ID if you have one."
            )
        usage = TokenUsage(
            model="mock-small",
            deployment=self.settings.chat_small_deployment,
            prompt_tokens=count_tokens(rewrite.rewritten_query),
            completion_tokens=count_tokens(question),
        )
        return ClarificationRequest(needed=needed, question=question, missing_slots=missing), usage

    def generate(
        self,
        rewrite: RewriteResult,
        retrieved: list[RetrievedChunk],
        web: list[WebResult],
        persona: str,
    ) -> tuple[Checklist, TokenUsage]:
        slots = rewrite.slots
        facts = extract_facts(retrieved)
        requested = set(detect_concepts(rewrite.rewritten_query))
        items: list[ChecklistItem] = []
        unsupported: list[str] = []

        # 1) Specific requested value: approach distance for a *stated* voltage.
        #    Match the full voltage token ("11 kV"), not the bare number, so a
        #    query about 500 kV does not accidentally match a "500 V" glove row.
        #    With no voltage the request is not specific enough to pin a single
        #    value, so we fall through to the general grounded-facts loop.
        if "approach_distance" in requested and slots.voltage:
            fact = find_fact(facts, ChecklistCategory.CLEARANCE, must_contain=[slots.voltage])
            if fact:
                items.append(
                    ChecklistItem(
                        category=ChecklistCategory.CLEARANCE,
                        instruction=fact.line,
                        value=fact.value,
                        citations=[fact.citation()],
                    )
                )
            else:
                unsupported.append(f"minimum approach distance for {slots.voltage}")

        # 2) All other grounded facts, prioritizing requested categories.
        requested_categories = {ChecklistCategory.PPE, ChecklistCategory.STOP_WORK}
        for concept in requested:
            from ..concepts import CONCEPT_TO_CATEGORY

            if concept in CONCEPT_TO_CATEGORY:
                requested_categories.add(CONCEPT_TO_CATEGORY[concept])

        def _rank(f):
            return (0 if f.category in requested_categories else 1, f.chunk.final_score * -1)

        for fact in sorted(facts, key=_rank):
            if len(items) >= _MAX_ITEMS:
                break
            if any(it.instruction == fact.line for it in items):
                continue
            if fact.category == ChecklistCategory.STOP_WORK:
                continue  # collected separately
            items.append(
                ChecklistItem(
                    category=fact.category,
                    instruction=fact.line,
                    value=fact.value,
                    citations=[fact.citation()],
                )
            )

        # 3) Stop-work conditions (grounded + mandatory defaults).
        stop_work = [f.line for f in facts if f.category == ChecklistCategory.STOP_WORK]
        stop_work.append(
            "If any required distance, voltage, or threshold is missing or unclear, "
            "stop work and contact your supervisor."
        )
        if unsupported:
            for u in unsupported:
                stop_work.append(
                    f"No source value found for {u}. Do not proceed; contact your supervisor."
                )

        # 4) Web sources (labeled separately; internal policy already applied above).
        web_sources = [
            Citation(doc=w.title, section="web", page=0, source_type=SourceType.WEB, url=w.url)
            for w in web
        ]

        checklist = Checklist(
            task=slots.task or rewrite.rewritten_query,
            equipment=slots.equipment,
            location=slots.location,
            persona=persona,
            items=items,
            stop_work_conditions=stop_work,
            unsupported_claims=unsupported,
            web_sources=web_sources,
        )
        prompt_text = rewrite.rewritten_query + "\n" + "\n".join(rc.chunk.text for rc in retrieved)
        usage = TokenUsage(
            model="mock-large",
            deployment=self.settings.chat_large_deployment,
            prompt_tokens=count_tokens(prompt_text),
            completion_tokens=count_tokens(checklist.model_dump_json()),
        )
        return checklist, usage


class AzureChatClient(ChatClient):
    """Real chat via Foundry deployments. Imported lazily."""

    def __init__(self, settings: Settings) -> None:  # pragma: no cover - real-Azure only
        self.settings = settings
        self._client = None

    def _ensure(self):  # pragma: no cover
        if self._client is not None:
            return
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI

        provider = get_bearer_token_provider(
            DefaultAzureCredential(
                managed_identity_client_id=self.settings.managed_identity_client_id or None
            ),
            "https://cognitiveservices.azure.com/.default",
        )
        self._client = AzureOpenAI(
            azure_endpoint=self.settings.foundry_endpoint,
            azure_ad_token_provider=provider,
            api_version="2024-10-21",  # VERIFY against your deployment
        )

    def _chat(self, deployment: str, system: str, user: str) -> tuple[str, TokenUsage]:  # pragma: no cover
        self._ensure()
        resp = self._client.chat.completions.create(
            model=deployment,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
        )
        msg = resp.choices[0].message.content or ""
        usage = TokenUsage(
            model=deployment,
            deployment=deployment,
            prompt_tokens=getattr(resp.usage, "prompt_tokens", 0),
            completion_tokens=getattr(resp.usage, "completion_tokens", 0),
        )
        return msg, usage

    def rewrite(self, query):  # pragma: no cover
        system = (
            "You rewrite messy field-technician queries. Fix typos and shorthand, "
            "expand acronyms, and extract slots. Return JSON with keys "
            "rewritten_query, task, equipment, voltage, location, domain."
        )
        text, usage = self._chat(self.settings.chat_small_deployment, system, query)
        data = _safe_json(text)
        slots = Slots(
            task=data.get("task"),
            equipment=data.get("equipment"),
            voltage=data.get("voltage"),
            location=data.get("location"),
            domain=data.get("domain"),
        )
        return RewriteResult(
            original_query=query, rewritten_query=data.get("rewritten_query", query), slots=slots
        ), usage

    def clarify(self, rewrite):  # pragma: no cover
        system = (
            "Decide if the task can be scoped safely. If equipment and voltage are "
            "both unknown, ask ONE clarifying question. Return JSON: needed(bool), "
            "question(str), missing_slots(list)."
        )
        text, usage = self._chat(
            self.settings.chat_small_deployment, system, rewrite.model_dump_json()
        )
        data = _safe_json(text)
        return ClarificationRequest(
            needed=bool(data.get("needed")),
            question=data.get("question", ""),
            missing_slots=data.get("missing_slots", []),
        ), usage

    def generate(self, rewrite, retrieved, web, persona):  # pragma: no cover
        schema = Checklist.model_json_schema()
        context = "\n\n".join(
            f"[{i}] {rc.chunk.doc} / {rc.chunk.section_display} (p{rc.chunk.page})\n{rc.chunk.text}"
            for i, rc in enumerate(retrieved)
        )
        web_ctx = "\n".join(f"WEB: {w.title} <{w.url}> {w.snippet}" for w in web)
        system = (
            "You generate a grounded pre-task safety checklist. HARD RULE: never "
            "invent a distance, voltage, or threshold. If a value is not in the "
            "sources, add it to unsupported_claims and a stop_work condition to "
            "contact a supervisor. Cite every value with doc/section/page. Label "
            "web-sourced content separately; internal policy wins on conflict. "
            f"Return ONLY JSON matching this schema: {json.dumps(schema)}"
        )
        user = f"PERSONA: {persona}\nQUERY: {rewrite.rewritten_query}\n\nSOURCES:\n{context}\n\n{web_ctx}"
        text, usage = self._chat(self.settings.chat_large_deployment, system, user)
        data = _safe_json(text)
        data.setdefault("task", rewrite.slots.task or rewrite.rewritten_query)
        data.setdefault("persona", persona)
        return Checklist.model_validate(data), usage


def _safe_json(text: str) -> dict:  # pragma: no cover - real-Azure only
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start : end + 1]) if start >= 0 else {}
