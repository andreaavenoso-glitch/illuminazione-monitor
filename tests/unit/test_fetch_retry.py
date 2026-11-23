import pytest
from app.collectors import adaptive_fetch as af


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(af, "RETRY_PAUSE", 0)
    monkeypatch.setattr(af, "RETRY_ENABLED", True)
    af.FAILURES.clear()
    af._HOST_OK.clear()


def _impl(results):
    calls = []

    async def fake(url, **kw):
        calls.append(url)
        return results[min(len(calls), len(results)) - 1]

    return fake, calls


@pytest.mark.asyncio
async def test_second_attempt_recovers_a_momentary_failure(monkeypatch):
    fake, calls = _impl([af.FetchResult("", "timeout"), af.FetchResult("pagina ok")])
    monkeypatch.setattr(af, "_adaptive_fetch_result_impl", fake)
    res = await af.adaptive_fetch_result("https://www.comune.x.it/a")
    assert res.text == "pagina ok" and len(calls) == 2 and not af.FAILURES


@pytest.mark.asyncio
@pytest.mark.parametrize("err", ["http_403", "http_404", "dns"])
async def test_no_retry_for_permanent_errors(monkeypatch, err):
    fake, calls = _impl([af.FetchResult("", err)])
    monkeypatch.setattr(af, "_adaptive_fetch_result_impl", fake)
    res = await af.adaptive_fetch_result("https://www.comune.x.it/a")
    assert not res.text and len(calls) == 1


@pytest.mark.asyncio
async def test_no_retry_on_platform_that_keeps_failing(monkeypatch):
    fake, calls = _impl([af.FetchResult("", "connect")])
    monkeypatch.setattr(af, "_adaptive_fetch_result_impl", fake)
    for _ in range(3):
        await af.adaptive_fetch_result("https://www.halleyweb.com/x")
    n = len(calls)
    await af.adaptive_fetch_result("https://www.halleyweb.com/y")
    assert len(calls) == n + 1  # a single attempt now
