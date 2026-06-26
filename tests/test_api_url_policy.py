"""Static checks for frontend fail-fast API URL policy (no Next build required)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_TS = ROOT / "frontend" / "src" / "lib" / "api.ts"


def test_api_ts_has_no_silent_localhost_or_chain():
    text = API_TS.read_text(encoding="utf-8")
    # Must not use || 'http://localhost' at top-level axios create without gating
    assert "process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'" not in text
    assert "resolveApiBaseURL" in text or "MISSING_API_URL" in text
    assert "missingRequired" in text
    assert "interceptors.request" in text
    # Dev fallback is documented and gated
    assert "dev fallback" in text.lower() or "localhost:8000/api" in text
    assert "NODE_ENV" in text
    assert "REQUIRE_API_URL" in text


def test_api_ts_rejects_multi_host_retry_patterns():
    text = API_TS.read_text(encoding="utf-8")
    assert "localhost:8001" not in text
    assert "127.0.0.1:8000" not in text or "fallback" in text.lower()
    # Single axios instance
    assert text.count("axios.create") == 1
