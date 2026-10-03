"""OpenTelemetry setup following the GenAI semantic conventions.

In mock mode spans go to the console exporter. In Azure mode, if
``APPLICATIONINSIGHTS_CONNECTION_STRING`` is set, we configure the Azure Monitor
OpenTelemetry distro so spans land in the App Insights linked to the Foundry
project.

The eight pipeline stages each open a span:
    guardrail_in, rewrite, clarify, retrieve, rerank, generate, guardrail_out, audit

GenAI attribute names (``gen_ai.*``) follow the OTel semantic conventions so the
traces render well in Foundry / App Insights.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from .settings import Settings

logger = logging.getLogger("ragsafety.tracing")

# GenAI semantic-convention attribute keys (subset we use).
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

_CONFIGURED = False


def configure_tracing(settings: Settings) -> None:
    """Idempotently configure the global tracer provider."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    resource = Resource.create(
        {
            "service.name": "ragsafety",
            "service.version": "0.1.0",
            "deployment.environment": "mock" if settings.mock_mode else "azure",
        }
    )
    provider = TracerProvider(resource=resource)

    if not settings.mock_mode and settings.applicationinsights_connection_string:
        try:
            # Lazy import: only needed for the real Azure path.
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(
                connection_string=settings.applicationinsights_connection_string
            )
            logger.info("Azure Monitor OpenTelemetry configured.")
            _CONFIGURED = True
            return
        except Exception as exc:  # pragma: no cover - real-Azure only
            logger.warning("Azure Monitor setup failed (%s); using console exporter.", exc)

    # Console exporter in mock mode, unless explicitly quieted (e.g. demos that
    # render their own output). quiet_tracing still runs spans; it just drops the
    # console exporter.
    if not settings.quiet_tracing:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _CONFIGURED = True


def get_tracer() -> trace.Tracer:
    return trace.get_tracer("ragsafety")


@contextmanager
def stage_span(name: str, **attributes: Any):
    """Open a span for a pipeline stage and attach attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield span
