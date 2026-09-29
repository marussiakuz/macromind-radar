"""Публичный MVP: тот же сервис, но пригодный для открытого адреса.

Живой прогон стоит денег (замер 28.09.2026: 89,7 ₽, из них около 30 ₽ модели и около
60 ₽ поиска) и идёт 7–11 минут. На открытом адресе это значит три новых риска, которых
не было на ноутбуке:

1. **Корзину может исчерпать кто угодно.** Поэтому новый прогон не запускается, если
   остатка не хватает на полный прогон: отказ с числами лучше, чем прогон, который
   умрёт на середине, потратив поисковую корзину впустую.
2. **Квота.** Ограничение на сутки — общее и на один адрес. Повтор уже посчитанного
   запроса бесплатен и квоту не тратит: он отдаётся из сохранённого разбора.
3. **Зависший прогон.** Если поисковый API перестанет отвечать, задача осталась бы в
   состоянии «выполняется» навсегда. Сторож помечает её отказом по тайм-ауту.

Сервер запускается так (за ним ставится HTTPS-прокси):

    uvicorn radar.public:app --host 0.0.0.0 --port 8000

Ничего из `radar/server.py` здесь не переписывается: наш маршрут `/api/search` встаёт
перед его маршрутом, остальные эндпоинты остаются как есть.
"""
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

# Стоимость одного прогона по замеру 28.09.2026. Переопределяется окружением, если
# цены источников изменятся: держать число в коде и забыть его обновить — хуже.
RUN_COST_LLM = float(os.environ.get("RADAR_RUN_COST_LLM", "30"))
RUN_COST_SEARCH = float(os.environ.get("RADAR_RUN_COST_SEARCH", "60"))

DAILY_RUNS = int(os.environ.get("RADAR_DAILY_RUNS", "6"))
IP_DAILY_RUNS = int(os.environ.get("RADAR_IP_DAILY_RUNS", "2"))
RUN_TIMEOUT = int(os.environ.get("RADAR_RUN_TIMEOUT", "1200"))
TOKEN = os.environ.get("RADAR_PUBLIC_TOKEN", "")

QUOTA_FILE = Path(os.environ.get("RADAR_QUOTA_FILE", str(RUNS_DIR / "public-quota.json")))
_QUOTA_LOCK = threading.Lock()


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
    # За прокси настоящий адрес приходит заголовком. Первый элемент списка — клиент.
    forwarded = http.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
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
    return {"known": True, "search": left.get("search", 0.0), "llm": left.get("llm", 0.0),
            "run_cost_search": RUN_COST_SEARCH, "run_cost_llm": RUN_COST_LLM,
            "runs_left": int(min(left.get("search", 0.0) / RUN_COST_SEARCH,
                                 left.get("llm", 0.0) / RUN_COST_LLM))}


def guarded_search(request: SearchRequest, http: Request) -> dict:
    """Тот же запуск анализа, но с проверками до первой траты."""
    if TOKEN:
        given = http.headers.get("x-radar-token") or http.query_params.get("token", "")
        if given != TOKEN:
            raise HTTPException(401, "нужен токен доступа: жюри получает его вместе со ссылкой")

    query = (request.query or "").strip()
    if len(query) < 3:
        raise HTTPException(400, "запрос короче трёх символов")

    # Повтор уже посчитанного запроса ничего не стоит: ни квоты, ни корзины.
    try:
        already = server.cached_run(query, plan=request.plan,
            allow_legacy=request.demo or server.DEMO or os.environ.get("RADAR_CACHE_ONLY") == "1") is not None
    except Exception:
        already = False

    if not already and not (request.demo or server.DEMO):
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
        if money.get("known") and (money["llm"] < RUN_COST_LLM or money["search"] < RUN_COST_SEARCH):
            raise HTTPException(402, (
                f"бюджета не хватает на полный прогон: осталось поиск {money['search']:.0f} ₽ "
                f"и модель {money['llm']:.0f} ₽, а прогон стоит примерно "
                f"{RUN_COST_SEARCH:.0f} ₽ и {RUN_COST_LLM:.0f} ₽. Запускать не будем: "
                f"прогон оборвался бы на середине, потратив поиск впустую. "
                f"Сохранённые разборы доступны."))
        _charge_quota(ip)

    started = server.search(request)
    started["free"] = already
    return started


@app.get("/api/limits")
def limits(http: Request) -> dict:
    """Что осталось: бюджет, квота, состояние очереди. Интерфейс это показывает."""
    running = [j for j in server.JOBS.values() if j.get("status") == "running"]
    return {"budget": budget_state(), "quota": quota_state(_client_ip(http)),
            "running": len(running), "run_timeout_sec": RUN_TIMEOUT,
            "token_required": bool(TOKEN)}


def _age_seconds(job: dict) -> float:
    try:
        started = datetime.fromisoformat(job["started"])
    except (KeyError, ValueError):
        return 0.0
    return (datetime.now(timezone.utc) - started).total_seconds()


def sweep_stale_jobs() -> list[str]:
    """Помечает отказом задачи, которые идут дольше тайм-аута.

    Поток задачи при этом не убивается — остановить его на середине конвейера нечем.
    Смысл в другом: интерфейс перестаёт опрашивать вечно и показывает причину.
    """
    stale = []
    for job in list(server.JOBS.values()):
        if job.get("status") != "running" or _age_seconds(job) <= RUN_TIMEOUT:
            continue
        job["status"] = "failed"
        job["error"] = (f"прогон шёл дольше {RUN_TIMEOUT // 60} минут и снят по тайм-ауту. "
                        f"Обычный прогон занимает 7–11 минут; вероятная причина — "
                        f"медленный ответ источника. Попробуйте ещё раз или откройте "
                        f"сохранённый разбор.")
        job["stage"] = "снято по тайм-ауту"
        job["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
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

if os.environ.get("RADAR_NO_WATCHDOG") != "1":  # pragma: no cover
    threading.Thread(target=_watchdog, daemon=True).start()
