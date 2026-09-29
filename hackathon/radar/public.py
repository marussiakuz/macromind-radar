"""Ограничения публичного API: токен запуска, суточные квоты и бюджет."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

from . import server
from .config import RUNS_DIR
from .ledger import Ledger
from .server import SearchRequest

app = server.app

# Минимальные остатки для старта, а не гарантия полной стоимости анализа.
RUN_COST_LLM = float(os.environ.get("RADAR_RUN_COST_LLM", "200"))
RUN_COST_SEARCH = float(os.environ.get("RADAR_RUN_COST_SEARCH", "60"))

DAILY_RUNS = int(os.environ.get("RADAR_DAILY_RUNS", "6"))
IP_DAILY_RUNS = int(os.environ.get("RADAR_IP_DAILY_RUNS", "2"))
RUN_TIMEOUT = int(os.environ.get("RADAR_RUN_TIMEOUT", "1200"))
TOKEN = os.environ.get("RADAR_PUBLIC_TOKEN", "")

QUOTA_FILE = Path(os.environ.get("RADAR_QUOTA_FILE", str(RUNS_DIR / "public-quota.json")))
_QUOTA_LOCK = threading.RLock()


def _today() -> str:
    return date.today().isoformat()


def _read_quota() -> dict:
    try:
        data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if data.get("day") != _today():
        # Сутки сменились: счётчики обнуляются, но файл переписывается только при трате.
        return {"day": _today(), "total": 0, "ips": {}}
    data.setdefault("total", 0)
    data.setdefault("ips", {})
    return data


def _client_ip(http: Request) -> str:
    # Заголовки прокси разбирает Uvicorn только от доверенных адресов.
    return http.client.host if http.client else "unknown"


def quota_state(ip: str = "") -> dict:
    data = _read_quota()
    return {"day": data["day"], "runs_today": data["total"], "daily_limit": DAILY_RUNS,
            "ip_runs_today": data["ips"].get(ip, 0) if ip else 0,
            "ip_daily_limit": IP_DAILY_RUNS}


def _charge_quota(ip: str) -> None:
    with _QUOTA_LOCK:
        data = _read_quota()
        data["total"] = data.get("total", 0) + 1
        data["ips"][ip] = data["ips"].get(ip, 0) + 1
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        QUOTA_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def budget_state() -> dict:
    """Остаток корзин и хватает ли его на один полный прогон."""
    try:
        left = Ledger().remaining()
    except Exception:
        return {"known": False}
    capacities = [left.get(kind, 0.0) / cost for kind, cost in
                  (("search", RUN_COST_SEARCH), ("llm", RUN_COST_LLM)) if cost > 0]
    return {"known": True, "search": left.get("search", 0.0), "llm": left.get("llm", 0.0),
            "run_cost_search": RUN_COST_SEARCH, "run_cost_llm": RUN_COST_LLM,
            "runs_left": int(min(capacities)) if capacities else DAILY_RUNS}


def guarded_search(request: SearchRequest, http: Request) -> dict:
    # Проверка и списание квоты выполняются атомарно в одном процессе сервиса.
    with _QUOTA_LOCK:
        return _guarded_search(request, http)


def _guarded_search(request: SearchRequest, http: Request) -> dict:
    """Тот же запуск анализа, но с проверками до первой траты."""
    if TOKEN:
        given = http.headers.get("x-radar-token", "")
        if given != TOKEN:
            raise HTTPException(401, "Введите токен доступа, выданный администратором")

    query = (request.query or "").strip()
    if len(query) < 3:
        raise HTTPException(400, "запрос короче трёх символов")

    request_key = (query.casefold(), request.plan, request.demo, request.force)
    for job_id, job in list(server.JOBS.items()):
        if job.get("status") == "running" and job.get("_request_key") == request_key:
            return {"job_id": job_id, "demo": server.DEMO, "reused": True, "free": True}

    offline = request.demo or server.DEMO or os.environ.get("RADAR_CACHE_ONLY") == "1"
    run = server.cached_run(query, plan=request.plan, allow_legacy=offline)
    already = run is not None and server.saved_cards(run, allow_legacy=offline) is not None
    if not already and not offline:
        ip = _client_ip(http)
        used = quota_state(ip)
        if used["runs_today"] >= DAILY_RUNS:
            raise HTTPException(429, (
                f"на сегодня исчерпан общий лимит живых прогонов ({DAILY_RUNS}). "
                f"Сохранённые разборы по-прежнему открываются мгновенно и бесплатно; "
                f"живой прогон снова доступен завтра."))
        if used["ip_runs_today"] >= IP_DAILY_RUNS:
            raise HTTPException(429, (
                f"с этого адреса за сутки уже запущено {used['ip_runs_today']} прогонов из "
                f"{IP_DAILY_RUNS}. Это защита бюджета, а не отказ в доступе: "
                f"сохранённые разборы открыты."))

        money = budget_state()
        if not money.get("known"):
            raise HTTPException(503, "Не удалось прочитать бюджет; проверьте журнал расходов на сервере")
        if (money["llm"] < RUN_COST_LLM or money["search"] < RUN_COST_SEARCH):
            raise HTTPException(402, (
                f"недостаточно бюджета для запуска: поиск {money['search']:.0f} ₽, "
                f"модель {money['llm']:.0f} ₽. Минимум для старта: "
                f"{RUN_COST_SEARCH:.0f} ₽ и {RUN_COST_LLM:.0f} ₽ соответственно. "
                "Администратор может изменить лимиты. Сохранённые разборы доступны."))
        _charge_quota(ip)

    started = server.search(request)
    started["free"] = already or offline
    return started


@app.get("/api/limits")
def limits(http: Request) -> dict:
    """Что осталось: бюджет, квота, состояние очереди. Интерфейс это показывает."""
    running = [j for j in server.JOBS.values() if j.get("status") == "running"]
    return {"budget": budget_state(), "quota": quota_state(_client_ip(http)),
            "running": len(running), "run_timeout_sec": RUN_TIMEOUT,
            "token_required": bool(TOKEN), "demo": server.DEMO}


def _age_seconds(job: dict) -> float:
    try:
        started = datetime.fromisoformat(job["started"])
    except (KeyError, ValueError):
        return 0.0
    return (datetime.now(timezone.utc) - started).total_seconds()


def sweep_stale_jobs() -> list[str]:
    """Предупреждает о долгом анализе, не выдавая работающий поток за остановленный."""
    stale = []
    for job in list(server.JOBS.values()):
        if (job.get("status") != "running" or job.get("timeout_notice")
                or _age_seconds(job) <= RUN_TIMEOUT):
            continue
        job["timeout_notice"] = (
            f"Анализ идёт больше {RUN_TIMEOUT // 60} минут и продолжает выполняться. "
            "Не запускайте его повторно; проверьте журнал сервера.")
        stale.append(job.get("id", ""))
    return stale


def _watchdog(interval: int = 30) -> None:  # pragma: no cover - фоновый поток
    while True:
        time.sleep(interval)
        try:
            sweep_stale_jobs()
        except Exception:
            pass


# Наш маршрут встаёт перед маршрутом server.py: совпадает первый подходящий.
app.router.routes.insert(0, APIRoute("/api/search", guarded_search, methods=["POST"]))

# Статика должна идти после всех API-маршрутов, включая /api/limits.
from starlette.routing import Mount
app.router.routes.sort(key=lambda route: isinstance(route, Mount))

if os.environ.get("RADAR_NO_WATCHDOG") != "1":  # pragma: no cover
    threading.Thread(target=_watchdog, daemon=True).start()
