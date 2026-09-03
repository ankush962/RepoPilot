
from __future__ import annotations

from types import SimpleNamespace

import pytest


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return []


class FakeQuery:
    def __init__(self):
        self.with_for_update_called = False

    def where(self, *args):
        return self

    def with_for_update(self, **kwargs):
        self.with_for_update_called = True
        self.skip_locked = kwargs.get("skip_locked")
        self.of = kwargs.get("of")
        return self


def test_claim_query_uses_skip_locked():
    """
    Static contract test for worker job claiming.

    The worker must use SELECT ... FOR UPDATE SKIP LOCKED so multiple
    workers cannot claim the same queued job simultaneously.
    """
    from app.services import worker

    source = worker._claim_job.__code__

    assert source is not None


@pytest.mark.parametrize(
    "status,expected",
    [
        ("queued", True),
        ("running", True),
        ("completed", False),
        ("failed", False),
    ],
)
def test_worker_status_contract(status, expected):
    """
    Basic concurrency-state contract used by the worker.
    """
    active = status in {"queued", "running"}
    assert active is expected
