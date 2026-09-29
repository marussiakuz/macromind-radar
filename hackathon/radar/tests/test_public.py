"""Проверки ограничителей публичного MVP.

Сеть здесь не нужна: запуск анализа подменяется, проверяется только то, что до денег
дело не доходит, когда бюджета или квоты не хватает.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("RADAR_NO_WATCHDOG", "1")


@pytest.fixture()
def public(tmp_path, monkeypatch):
    from radar import public as mod
    from radar import server

    monkeypatch.setattr(mod, "QUOTA_FILE", tmp_path / "quota.json")
    monkeypatch.setattr(mod, "DAILY_RUNS", 2)
    monkeypatch.setattr(mod, "IP_DAILY_RUNS", 1)
    monkeypatch.setattr(mod, "TOKEN", "")
    # Живой прогон не запускаем ни при каких условиях: проверяем только привратника бюджета.
    monkeypatch.setattr(server, "search", lambda request: {"job_id": "test", "demo": False})
    monkeypatch.setattr(server, "cached_run", lambda query: None)
    monkeypatch.setattr(mod, "budget_state", lambda: {
        "known": True, "search": 500.0, "llm": 300.0,
        "run_cost_search": 60.0, "run_cost_llm": 30.0, "runs_left": 8})
    return mod


def _request(query: str = "слабые сигналы в финтехе"):
    from radar.server import SearchRequest
    return SearchRequest(query=query)


class _Http:
    """Минимальная замена запроса: адрес клиента и заголовки."""

    def __init__(self, ip: str = "10.0.0.1", token: str = "") -> None:
        self.headers = {"x-forwarded-for": ip}
        if token:
            self.headers["x-radar-token"] = token
        self.query_params: dict[str, str] = {}
        self.client = None


def test_short_query_is_refused_before_any_check(public) -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        public.guarded_search(_request("ии"), _Http())
    assert exc.value.status_code == 400


def test_run_starts_while_budget_and_quota_allow(public) -> None:
    assert public.guarded_search(_request(), _Http())["job_id"] == "test"


def test_second_run_from_same_address_is_refused(public) -> None:
    from fastapi import HTTPException
    public.guarded_search(_request(), _Http("10.0.0.7"))
    with pytest.raises(HTTPException) as exc:
        public.guarded_search(_request("другая тема поиска"), _Http("10.0.0.7"))
    assert exc.value.status_code == 429
    assert "сохранённые разборы" in exc.value.detail.lower()


def test_daily_limit_counts_all_addresses(public) -> None:
    from fastapi import HTTPException
    public.guarded_search(_request(), _Http("10.0.0.1"))
    public.guarded_search(_request(), _Http("10.0.0.2"))
    with pytest.raises(HTTPException) as exc:
        public.guarded_search(_request(), _Http("10.0.0.3"))
    assert exc.value.status_code == 429


def test_low_budget_refuses_instead_of_starting_a_doomed_run(public, monkeypatch) -> None:
    from fastapi import HTTPException
    # Остаток модели 38 ₽ был фактическим состоянием 29.09.2026 при цене прогона 30 ₽:
    # поиска при этом хватает, поэтому важно, что отказ даёт именно модель.
    monkeypatch.setattr(public, "budget_state", lambda: {
        "known": True, "search": 500.0, "llm": 12.0,
        "run_cost_search": 60.0, "run_cost_llm": 30.0, "runs_left": 0})
    with pytest.raises(HTTPException) as exc:
        public.guarded_search(_request(), _Http())
    assert exc.value.status_code == 402
    assert "12 ₽" in exc.value.detail


def test_repeat_of_a_saved_run_is_free_and_keeps_quota(public, monkeypatch) -> None:
    from radar import server
    monkeypatch.setattr(server, "cached_run", lambda query: Path("/tmp/сохранённый-прогон"))
    monkeypatch.setattr(public, "budget_state", lambda: {
        "known": True, "search": 0.0, "llm": 0.0,
        "run_cost_search": 60.0, "run_cost_llm": 30.0, "runs_left": 0})
    out = public.guarded_search(_request(), _Http("10.0.0.9"))
    assert out["free"] is True
    assert public.quota_state("10.0.0.9")["runs_today"] == 0


def test_token_is_required_when_set(public, monkeypatch) -> None:
    from fastapi import HTTPException
    monkeypatch.setattr(public, "TOKEN", "жюри-2026")
    with pytest.raises(HTTPException) as exc:
        public.guarded_search(_request(), _Http())
    assert exc.value.status_code == 401
    assert public.guarded_search(_request(), _Http(token="жюри-2026"))["job_id"] == "test"


def test_stale_job_is_marked_failed_with_a_reason(public, monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone
    from radar import server

    old = (datetime.now(timezone.utc) - timedelta(seconds=2000)).isoformat(timespec="seconds")
    fresh = datetime.now(timezone.utc).isoformat(timespec="seconds")
    monkeypatch.setitem(server.JOBS, "зависший", {"id": "зависший", "status": "running", "started": old})
    monkeypatch.setitem(server.JOBS, "свежий", {"id": "свежий", "status": "running", "started": fresh})
    monkeypatch.setattr(public, "RUN_TIMEOUT", 1200)

    assert public.sweep_stale_jobs() == ["зависший"]
    assert server.JOBS["зависший"]["status"] == "failed"
    assert "тайм-ауту" in server.JOBS["зависший"]["error"]
    assert server.JOBS["свежий"]["status"] == "running"


def test_quota_file_survives_restart(public) -> None:
    public.guarded_search(_request(), _Http("10.0.0.5"))
    saved = json.loads(public.QUOTA_FILE.read_text(encoding="utf-8"))
    assert saved["total"] == 1 and saved["ips"]["10.0.0.5"] == 1


def test_topup_of_one_basket_is_allowed_and_idempotent(tmp_path) -> None:
    """Пополняют обычно одну корзину, и повтор разрешения не должен удваивать сумму."""
    from radar.ledger import Ledger

    ledger = Ledger(path=tmp_path / "ledger.json")
    before = ledger.remaining()
    ledger.authorize("2026-09-29-llm300", 0.0, 300.0, "пополнение под публичный MVP")
    after = ledger.remaining()
    assert round(after["llm"] - before["llm"], 2) == 300.0
    assert after["search"] == before["search"]

    ledger.authorize("2026-09-29-llm300", 0.0, 300.0, "повтор той же команды")
    assert ledger.remaining()["llm"] == after["llm"]


def test_empty_authorization_is_refused(tmp_path) -> None:
    import pytest as _pytest
    from radar.ledger import Ledger

    ledger = Ledger(path=tmp_path / "ledger.json")
    with _pytest.raises(ValueError):
        ledger.authorize("пустое", 0.0, 0.0, "ничего не пополнено")
