"""Production readiness framework.

Structured logging, health checks, metrics, tracing, retries,
circuit breakers, rate limiting, and config validation.

Does not redesign existing AI agents — observability & resilience only.
"""

from backend.production.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    get_circuit_breaker,
    reset_circuit_breakers,
)
from backend.production.config_validator import (
    ConfigIssue,
    ConfigValidationResult,
    ConfigValidator,
    validate_config,
)
from backend.production.health import health
from backend.production.logging import (
    clear_context,
    configure_structured_logging,
    get_request_id,
    get_trace_id,
    log_event,
    set_request_id,
    set_trace_id,
)
from backend.production.metrics import (
    MetricsCollector,
    get_metrics_collector,
    metrics,
    reset_metrics_collector,
)
from backend.production.rate_limiter import (
    RateLimitExceeded,
    RateLimiter,
    get_rate_limiter,
    reset_rate_limiters,
)
from backend.production.request_tracker import (
    RequestTracker,
    get_request_tracker,
    new_request_id,
    reset_request_tracker,
)
from backend.production.retry import RetryPolicy, Retryable, retry_call
from backend.production.tracing import Tracer, get_tracer, reset_tracer, trace_request

__all__ = [
    # Public entrypoints
    "health",
    "metrics",
    "trace_request",
    # Logging / request context
    "configure_structured_logging",
    "log_event",
    "set_request_id",
    "get_request_id",
    "set_trace_id",
    "get_trace_id",
    "clear_context",
    "new_request_id",
    # Metrics / tracing / requests
    "MetricsCollector",
    "get_metrics_collector",
    "reset_metrics_collector",
    "Tracer",
    "get_tracer",
    "reset_tracer",
    "RequestTracker",
    "get_request_tracker",
    "reset_request_tracker",
    # Resilience
    "RetryPolicy",
    "Retryable",
    "retry_call",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "CircuitOpenError",
    "get_circuit_breaker",
    "reset_circuit_breakers",
    "RateLimiter",
    "RateLimitExceeded",
    "get_rate_limiter",
    "reset_rate_limiters",
    # Config
    "ConfigValidator",
    "ConfigValidationResult",
    "ConfigIssue",
    "validate_config",
]
