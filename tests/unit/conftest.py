"""Unit-test-only fixtures.

The autouse ``_isolate_env`` fixture below is scoped to ``tests/unit/``
deliberately. Integration tests under ``tests/integration/`` need the
real shell environment (OPENAI_API_KEY, XH_STAGE_*, XH_PG_DSN, ...)
to exercise live healing layers — they must NOT be scrubbed.
"""

from __future__ import annotations

import pytest


# Non-XH credentials that still affect the healer's RAG / MCP bootstrap.
_NON_XH_HERMETIC_VARS = ("OPENAI_API_KEY",)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every unit test hermetic against shell-exported env vars.

    Two leak paths to defend against:

    1. A developer shell that exports XH_PG_DSN / OPENAI_API_KEY makes
       the facade dial real backends in tests that don't pass an
       explicit repository.
    2. Any test that imports tests.integration.settings transitively
       calls load_env_into_process, which writes XH_STAGE_*, XH_RAG_*,
       XH_FINGERPRINT_* etc. from .env into os.environ. Those values
       persist into the *next* test and silently reconfigure the
       facade (e.g. disabling every stage except RAG).

    Strategy: clear every XH_* env var, plus the small set of non-XH
    credentials the healer also reads. Tests that need a specific value
    re-set it locally with monkeypatch.setenv after this fixture runs.
    """
    import os

    for name in list(os.environ):
        if name.startswith("XH_"):
            monkeypatch.delenv(name, raising=False)
    for name in _NON_XH_HERMETIC_VARS:
        monkeypatch.delenv(name, raising=False)
