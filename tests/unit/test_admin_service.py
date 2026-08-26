"""Unit tests for admin_service.get_task_status.

The manual-collection panel used to just sleep a fixed amount of time and
hope the dispatched Celery tasks were done by then -- a full collection pass
can take several minutes, so the panel routinely moved on to normalize/score
while collection was still running. get_task_status lets a caller poll a
task's real state instead. Celery's AsyncResult talks to the result backend
(redis) as soon as its attributes are touched, so it's mocked here rather
than exercised against a live broker.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.admin_service import get_task_status


def _mock_result(status: str, *, result=None, successful=False, failed=False, ready=True):
    mock = MagicMock()
    mock.status = status
    mock.result = result
    mock.successful.return_value = successful
    mock.failed.return_value = failed
    mock.ready.return_value = ready
    return mock


class TestGetTaskStatus:
    def test_pending_task_has_no_result_or_error(self) -> None:
        with patch("app.services.admin_service.AsyncResult") as mock_async_result:
            mock_async_result.return_value = _mock_result("PENDING", ready=False)
            payload = get_task_status("abc-123")
        assert payload == {"task_id": "abc-123", "status": "PENDING", "ready": False}

    def test_successful_task_carries_its_return_value(self) -> None:
        with patch("app.services.admin_service.AsyncResult") as mock_async_result:
            mock_async_result.return_value = _mock_result(
                "SUCCESS", result={"records_valid": 3}, successful=True
            )
            payload = get_task_status("abc-123")
        assert payload["status"] == "SUCCESS"
        assert payload["result"] == {"records_valid": 3}
        assert "error" not in payload

    def test_failed_task_carries_a_string_error(self) -> None:
        with patch("app.services.admin_service.AsyncResult") as mock_async_result:
            mock_async_result.return_value = _mock_result(
                "FAILURE", result=ValueError("boom"), failed=True
            )
            payload = get_task_status("abc-123")
        assert payload["status"] == "FAILURE"
        assert payload["error"] == "boom"
        assert "result" not in payload
