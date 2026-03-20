"""Basic tests for the Piper TTS agent."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# Ensure registration doesn't fire during tests
os.environ.setdefault("BACKEND_URL", "")
os.environ.setdefault("LLM_MANAGER_AGENT_PSK", "")


from main import (  # noqa: E402
    _build_capabilities,
    _list_voices,
    _resolve_voice,
    app,
)

client = TestClient(app)


# ── Import / smoke ────────────────────────────────────────────────────────────

def test_app_import():
    """The FastAPI app object should be importable and have the expected title."""
    assert app.title == "Piper TTS Agent"


# ── Pure helpers ──────────────────────────────────────────────────────────────

def test_list_voices_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        with patch("main.PIPER_VOICES_DIR", tmp):
            assert _list_voices() == []


def test_list_voices_finds_onnx():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "en_US-lessac-medium.onnx").touch()
        (Path(tmp) / "en_US-lessac-medium.onnx.json").touch()  # config, not a voice
        (Path(tmp) / "de_DE-thorsten-high.onnx").touch()
        with patch("main.PIPER_VOICES_DIR", tmp):
            voices = _list_voices()
            assert voices == ["de_DE-thorsten-high", "en_US-lessac-medium"]


def test_list_voices_nonexistent_dir():
    with patch("main.PIPER_VOICES_DIR", "/nonexistent/path"):
        assert _list_voices() == []


def test_resolve_voice_falls_back_to_default():
    with patch("main.PIPER_VOICES_DIR", "/nonexistent"):
        result = _resolve_voice("missing-voice")
        assert result == "en_US-lessac-medium"


def test_resolve_voice_returns_existing():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "custom-voice.onnx").touch()
        with patch("main.PIPER_VOICES_DIR", tmp):
            assert _resolve_voice("custom-voice") == "custom-voice"


def test_resolve_voice_none_returns_default():
    assert _resolve_voice(None) == "en_US-lessac-medium"


def test_build_capabilities():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "voice1.onnx").touch()
        with patch("main.PIPER_VOICES_DIR", tmp):
            caps = _build_capabilities()
            assert caps["tts"] is True
            assert caps["stt"] is False
            assert caps["gpu"] is False
            assert "voice1" in caps["voices"]
            assert caps["default_voice"] == "en_US-lessac-medium"


# ── HTTP endpoints ────────────────────────────────────────────────────────────

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_metrics():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "piper_agent_requests_total" in resp.text


def test_status_no_psk():
    """Status should be accessible when no PSK is configured."""
    resp = client.get("/v1/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tts"] is True
    assert "voices" in data


def test_voices_endpoint():
    resp = client.get("/v1/voices")
    assert resp.status_code == 200
    assert "voices" in resp.json()


def test_psk_blocks_when_set():
    """When AGENT_PSK is set, non-exempt endpoints require the header."""
    with patch("main.AGENT_PSK", "secret123"):
        resp = client.get("/v1/status")
        assert resp.status_code == 401

        resp = client.get("/v1/status", headers={"X-Agent-PSK": "secret123"})
        assert resp.status_code == 200


def test_psk_exempts_health_and_metrics():
    with patch("main.AGENT_PSK", "secret123"):
        assert client.get("/health").status_code == 200
        assert client.get("/metrics").status_code == 200


def test_speech_missing_voice():
    """Speech with a non-existent voice model returns 404."""
    with patch("main.PIPER_VOICES_DIR", "/nonexistent"):
        with patch("main.PIPER_DEFAULT_VOICE", "missing"):
            resp = client.post("/v1/audio/speech", json={"input": "hello"})
            assert resp.status_code == 404
