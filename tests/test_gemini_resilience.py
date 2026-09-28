"""Retry / model-failover behaviour of the Gemini call, with simulated provider errors."""
import pytest

OK = {"indicators_detected": ["trash_or_debris"], "confidence": 0.8, "reasoning": "ok"}
OVERLOADED = Exception("503 UNAVAILABLE high demand")


@pytest.fixture()
def harness(monkeypatch):
    # Imported lazily so this module never touches settings before other tests configure them.
    from app import ai

    calls: list[str] = []
    behaviour = {"fn": lambda model, n: OK}

    def fake_call(client, model, data, mime, text):
        calls.append(model)
        return behaviour["fn"](model, len(calls))

    monkeypatch.setattr(ai, "_call_model", fake_call)
    monkeypatch.setattr(ai.time, "sleep", lambda s: None)
    monkeypatch.setattr(ai.genai, "Client", lambda api_key: object())
    monkeypatch.setattr(ai.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai.settings, "GEMINI_MODEL", "primary")
    monkeypatch.setattr(ai.settings, "GEMINI_FALLBACK_MODEL", "fallback")

    def run(fn):
        behaviour["fn"] = fn
        return ai._gemini_assessment(b"", "image/jpeg", "t")

    return run, calls


def _fail(exc):
    def fn(model, n):
        raise exc

    return fn


def test_recovers_after_transient_503(harness):
    run, calls = harness

    def fn(model, n):
        if n < 3:
            raise OVERLOADED
        return OK

    assert run(fn) == OK
    assert calls == ["primary"] * 3


def test_fails_over_to_fallback_model(harness):
    run, calls = harness

    def fn(model, n):
        if model == "primary":
            raise OVERLOADED
        return OK

    assert run(fn) == OK
    assert calls == ["primary"] * 3 + ["fallback"]


def test_all_models_overloaded_raises(harness):
    run, calls = harness
    with pytest.raises(Exception, match="503"):
        run(_fail(OVERLOADED))
    assert calls == ["primary"] * 3 + ["fallback"] * 3


def test_real_error_on_primary_is_not_retried(harness):
    run, calls = harness
    with pytest.raises(Exception, match="403"):
        run(_fail(Exception("403 API key invalid")))
    assert calls == ["primary"]


def test_bad_fallback_name_reports_original_overload(harness):
    run, calls = harness

    def fn(model, n):
        raise OVERLOADED if model == "primary" else Exception("404 NOT_FOUND model")

    with pytest.raises(Exception, match="503"):
        run(fn)
    assert calls == ["primary"] * 3 + ["fallback"]
