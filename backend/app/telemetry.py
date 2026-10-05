"""OpenTelemetry tracing. Exports to Azure Monitor / Application Insights when
APPLICATIONINSIGHTS_CONNECTION_STRING is set (pip install -r requirements-azure.txt), else to the console
when OTEL_CONSOLE=1, else spans are created but dropped (no-op exporter)."""
from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

log = logging.getLogger(__name__)
_configured = False


def setup() -> str:
    global _configured
    if _configured:
        return "configured"
    _configured = True
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if conn:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor
            configure_azure_monitor(connection_string=conn)
            return "azure-monitor"
        except ImportError:
            log.warning("azure-monitor-opentelemetry not installed; falling back to console/no-op")
    provider = TracerProvider(resource=Resource.create({"service.name": "procurement-integrity-agent"}))
    if os.getenv("OTEL_CONSOLE") == "1":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return "console" if os.getenv("OTEL_CONSOLE") == "1" else "no-op"


tracer = trace.get_tracer("procurement-integrity-agent")
