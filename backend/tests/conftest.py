"""Fixtures every test gets.

The rate limits are real in the tests, deliberately — switching them off would
mean the end-to-end limit tests measure nothing. But the limiter counts against
the caller's address, and under a `TestClient` every test in the session is the
same caller, `testclient`. Left alone the counters accumulate across the whole
run, so a test that posts one message fails because eleven earlier tests in
other files posted theirs. That is not a finding about the code; it is one test
leaking into the next.

So the budget is reset before each test. Every test then starts with a full
allowance, and a test that wants to reach a limit still reaches it inside its
own body.
"""
import pytest

from app.core.ratelimit import limiter


@pytest.fixture(autouse=True)
def a_fresh_rate_limit_budget():
    limiter.reset()
    yield


@pytest.fixture
def dg_review_disabled(monkeypatch):
    """Rendering, retention and regulation fixtures opt out of the new workflow.

    They intentionally construct incomplete or synthetic shipments to test a
    specific renderer or persistence rule. Keep the release policy disabled
    in that explicit test configuration; test_dg_review_permissions exercises
    the real default-on policy across all final-output routes.
    """
    from app.services import dg_review
    original = dg_review.instance_settings
    monkeypatch.setattr(dg_review, "instance_settings", lambda db:
                        original(db).model_copy(update={"dg_review_enabled": False}))
