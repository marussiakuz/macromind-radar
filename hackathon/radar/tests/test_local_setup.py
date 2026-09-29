"""Запуск без приватных файлов, замена модели и отсутствие платных вызовов в демо."""
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from radar.config import Settings, Prices, load_env_file
from radar.ledger import Ledger, LimitReached


def test_env_model_is_read_when_settings_are_created(tmp_path, monkeypatch):
    monkeypatch.delenv("RADAR_MODEL", raising=False)
    path = tmp_path / ".env"
    path.write_text("RADAR_MODEL=local-test-model\n")
    load_env_file(path)
    assert Settings().model_uri == "local-test-model"
    monkeypatch.setenv("RADAR_MODEL", "shell-model")
    load_env_file(path)
    assert Settings().model_uri == "shell-model"


def test_new_ledger_is_zero_and_does_not_reset_existing_file(tmp_path):
    p = tmp_path / "ledger.json"
    ledger = Ledger(p)
    assert ledger.remaining() == {"search": 0, "llm": 0, "spent": {"search": 0, "llm": 0}}
    with pytest.raises(LimitReached):
        ledger.reserve(0.01, "search")
    ledger.authorize("first", 100, 200, "test")
    ledger.reserve(10, "search")
    assert Ledger(p).remaining()["search"] == 90


def test_custom_model_auth_request_cost_and_cache_isolation(tmp_path, monkeypatch):
    from radar import extract, ledger
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    budget = Ledger(tmp_path / "ledger.json")
    budget.authorize("test", 10, 10, "test")
    monkeypatch.setattr(ledger, "_shared", budget)
    monkeypatch.setattr(extract, "RUNS_DIR", tmp_path)
    monkeypatch.delenv("RADAR_LLM_REASONING_EFFORT", raising=False)
    settings = Settings(yandex_api_key="search-only-secret", model_uri_template="my-model",
                        llm_endpoint="http://model-one.test/v1/chat/completions", llm_api_key="model-secret",
                        prices=Prices(llm_input_rub_per_mtok=10, llm_output_rub_per_mtok=20))
    assert "secret" not in repr(settings)
    for endpoint in (settings.llm_endpoint, "http://model-two.test/v1/chat/completions"):
        client = extract.YandexLLM(replace(settings, llm_endpoint=endpoint))
        client._client.close()
        client._client = httpx.Client(transport=httpx.MockTransport(respond))
        assert client.complete("return JSON", {})[0] == '{"ok":true}'
        assert client.complete("return JSON", {})[1:] == (0, 0)
        client._client.close()
    assert len(calls) == 2
    assert all(r.headers["authorization"] == "Bearer model-secret" for r in calls)
    body = json.loads(calls[0].content)
    assert body["model"] == "my-model" and "reasoning_effort" not in body
    assert budget.remaining()["spent"]["llm"] == pytest.approx(0.0004)
    assert replace(settings, llm_api_key=None).llm_headers == {}


def test_yandex_keeps_provider_auth_and_reasoning(monkeypatch):
    monkeypatch.delenv("RADAR_LLM_REASONING_EFFORT", raising=False)
    s = Settings(yandex_api_key="private-search", yandex_folder_id="folder", llm_api_key=None,
                 model_uri_template="gpt://{folder}/qwen")
    s.validate_llm()
    assert s.llm_headers == {"Authorization": "Api-Key private-search"}
    assert s.model_uri == "gpt://folder/qwen" and s.reasoning_effort == "none"


def test_demo_opens_bundled_cards_without_network_or_budget(tmp_path, monkeypatch):
    from radar import server
    monkeypatch.setattr(server, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(server, "JOBS", {"demo": {"status": "running"}})
    monkeypatch.setattr(server, "DEMO", True)
    def forbidden(*args, **kwargs):
        raise AssertionError("demo attempted live processing")
    monkeypatch.setattr(server, "run_pool", forbidden)
    monkeypatch.setattr(server, "build_cards", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    server.worker("demo", server.SearchRequest(query="Edge"))
    job = server.JOBS["demo"]
    assert job["status"] == "completed", job.get("error")
    assert job["cards_from_cache"] and job["demo"] and job["trends"]
    assert not list(tmp_path.iterdir())
    server.JOBS["absent"] = {"status": "running"}
    server.worker("absent", server.SearchRequest(query="missing example"))
    assert server.JOBS["absent"]["status"] == "failed"
    assert not list(tmp_path.iterdir())


def test_api_hides_internal_trace_and_keeps_limits_route(monkeypatch):
    from radar import server, public
    monkeypatch.setattr(server, "JOBS", {"demo": {"status": "failed", "trace": "private path", "_request_key": "private"}})
    with TestClient(public.app) as client:
        assert client.get("/api/search/demo").json() == {"status": "failed"}
        assert client.get("/api/limits").status_code == 200


def test_zero_model_cost_does_not_divide_by_zero(monkeypatch, tmp_path):
    from radar import public
    ledger = Ledger(tmp_path / "ledger.json")
    ledger.authorize("test", 120, 0, "local model")
    monkeypatch.setattr(public, "Ledger", lambda: ledger)
    monkeypatch.setattr(public, "RUN_COST_SEARCH", 60)
    monkeypatch.setattr(public, "RUN_COST_LLM", 0)
    assert public.budget_state()["runs_left"] == 2


def test_fixture_pipeline_extracts_without_reference_or_network(tmp_path, monkeypatch):
    from radar.pipeline import run_pool
    def forbidden(*args, **kwargs):
        raise AssertionError("fixture pipeline attempted network")
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    run = run_pool("", "Защита ИИ", "fixtures", Settings(), runs_dir=tmp_path)
    rows = [json.loads(line) for line in (run / "candidates.jsonl").read_text().splitlines()]
    assert rows and all(row["evidence"] for row in rows)
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["cost_rub"] == 0 and not manifest["reference_sha256"]
