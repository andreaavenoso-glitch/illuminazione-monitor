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


@pytest.mark.asyncio
async def test_429_waits_the_retry_after_and_slows_the_host(monkeypatch):
    import httpx

    seen = []

    async def fake_sleep(sec):
        seen.append(sec)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    req = httpx.Request("GET", "https://www.comune.x.it/a")
    exc = httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, headers={"Retry-After": "7"}, request=req))
    monkeypatch.setattr(af, "HOST_MIN_INTERVAL", 1.5)
    af._note_429("www.comune.x.it", exc)
    assert af._RETRY_AFTER["www.comune.x.it"] == 7.0
    assert af._HOST_INTERVAL["www.comune.x.it"] == af.SLOW_INTERVAL

    fake, calls = _impl([af.FetchResult("", "http_429"), af.FetchResult("ok")])
    monkeypatch.setattr(af, "_adaptive_fetch_result_impl", fake)
    res = await af.adaptive_fetch_result("https://www.comune.x.it/a")
    assert res.text == "ok" and 7.0 in seen


@pytest.mark.asyncio
async def test_same_host_requests_are_spaced(monkeypatch):
    import time

    waits = []

    async def fake_sleep(sec):
        waits.append(sec)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr(af, "HOST_MIN_INTERVAL", 1.5)
    af._HOST_NEXT.clear()
    af._HOST_INTERVAL.clear()
    t0 = time.monotonic()
    for _ in range(3):
        await af._wait_turn("www.comune.x.it")
    assert len(waits) == 2 and waits[0] >= 1.0 and waits[1] >= 2.5 and time.monotonic() - t0 < 1
    await af._wait_turn("altro.it")  # another host: no wait
    assert len(waits) == 2


@pytest.mark.asyncio
async def test_persistent_429_puts_the_host_in_cooldown_and_stops_requests(monkeypatch):
    async def fake_sleep(sec):
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setattr(af, "COOLDOWN_S", 300.0)
    fake, calls = _impl([af.FetchResult("", "http_429")])
    monkeypatch.setattr(af, "_adaptive_fetch_result_impl", fake)
    r1 = await af.adaptive_fetch_result("https://www.comune.x.it/a")
    n = len(calls)
    assert not r1.text and n == 3  # first + two retries
    r2 = await af.adaptive_fetch_result("https://www.comune.x.it/b")
    assert r2.error == "http_429" and len(calls) == n  # no request while cooling down
    await af.adaptive_fetch_result("https://altro.it/c")
    assert len(calls) > n  # other hosts are not affected
