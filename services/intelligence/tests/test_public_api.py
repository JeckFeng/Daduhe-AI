"""Verify daduhe_common's public API surface — all symbols importable from package root."""

import daduhe_common


def test_all_public_symbols_exported():
    """Every symbol used by the three services must be importable from daduhe_common directly."""
    expected = [
        # middleware
        "TraceMiddleware",
        # logging
        "info",
        "warn",
        "error",
        # tracing
        "get_or_generate_trace_id",
        "generate_trace_id",
        # health
        "create_health_router",
        # error_codes
        "ErrorCode",
        "error_response",
    ]
    missing = [name for name in expected if not hasattr(daduhe_common, name)]
    assert not missing, f"Missing exports: {missing}"


def test_no_private_symbols_leaked():
    """Internal submodules (logging, tracing, etc.) should not be re-exported as modules
    unless intentionally part of the public API. The package __all__ or explict exports
    should gate this."""
    # Check that internal module internals aren't accidentally exported
    assert not hasattr(daduhe_common, "log"), (
        "low-level 'log' function should not be exported; use info/warn/error"
    )
