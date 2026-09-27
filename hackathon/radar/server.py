"""HTTP-сервис радара: открытый запрос пользователя запускает настоящий конвейер.

Заказчик проверяет решение открытым запросом и прямо называет примеры вне таблицы —
«слабые сигналы в 3D-печати», «Микрофлюидный чип», «Гардрейл». Статическая выгрузка
результатов этого не выдерживает: что ни введи, показывается один и тот же прогон.
Поэтому здесь запрос запускает конвейер, а интерфейс опрашивает состояние.

Прогон занимает минуты и стоит денег, поэтому:
  * результат по запросу кешируется и повторный запрос отдаётся мгновенно;
  * есть демонстрационный режим: запрос отдаёт сохранённый прогон, ничего не тратя.

    .venv/bin/python -m radar.server            # 127.0.0.1:8000
    RADAR_DEMO=1 .venv/bin/python -m radar.server   # только сохранённые прогоны
"""
from __future__ import annotations

import json
import os
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import RUNS_DIR, Settings, load_env_file
from .export_ui import to_trend
from .pipeline import run_pool
from .rank import HackerNewsProbe, MaturityProbe, OpenAlexProbe, score_candidate
from .corroborate import canonical_terms, cluster_by_term
from .extract import YandexLLM
from .reference import load_reference

app = FastAPI(title="Радар слабых сигналов")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DEMO = os.environ.get("RADAR_DEMO") == "1"
JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


class SearchRequest(BaseModel):
    query: str
    plan: str = "pains"          # pains | segments
    demo: bool = False


def known_area(query: str) -> str:
    """Если запрос совпал с областью таблицы, считаем метрику покрытия заодно."""
    try:
        reference, _ = load_reference()
    except Exception:
        return ""
    q = query.lower()
    for area in {i.area for i in reference}:
        if area.lower() in q or q in area.lower():
            return area
    return ""


def cached_run(query: str) -> Path | None:
    """Последний сохранённый прогон с тем же запросом."""
    best = None
    for run in sorted(RUNS_DIR.glob("2026*"), reverse=True):
        manifest = run / "manifest.json"
        if not manifest.exists() or not (run / "candidates.jsonl").exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("query", "").strip().lower() == query.strip().lower():
            best = run
            break
    return best


def build_cards(run: Path, job: dict) -> list[dict]:
    """Кандидаты прогона → карточки: канонический термин, окно зрелости, признаки."""
    pool = [json.loads(l) for l in (run / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    job["stage"] = "термины"
    llm = YandexLLM(Settings(), max_tokens=1200)
    terms = canonical_terms(pool, llm)
    clusters = cluster_by_term(pool, terms)
    players = {id(c): cl.players for cl in clusters for c in cl.candidates}
    sources = {id(c): cl.independent_sources for cl in clusters for c in cl.candidates}

    job["stage"] = "проверка принадлежности области"
    from .relevance import filter_in_domain
    in_domain, why_domain = filter_in_domain(
        [f"{c['name_ru']}. {c['mechanism'][:140]}" for c in pool], job["query"], llm)

    job["stage"] = "окно зрелости"
    # Научная база покрывает все области, сообщество разработчиков — свою точнее.
    probe = MaturityProbe([OpenAlexProbe(), HackerNewsProbe()])
    scored, unmeasured = [], []
    for i, cand in enumerate(pool):
        term = terms.get(i)
        if not term or not in_domain.get(i, True):
            continue
        sig = score_candidate({**cand, "name_orig": term}, probe, players=players.get(id(cand), 0))
        if sources.get(id(cand), 0) >= 2:
            sig.score += 1.5
            sig.notes.append(f"подтверждено с {sources[id(cand)]} разных доменов")
        if sig.status == "unmeasured" and sig.score >= 2:
            unmeasured.append((sig, cand))
        elif sig.score >= 5:
            scored.append((sig, cand))
    probe.close()
    scored.sort(key=lambda x: -x[0].score)
    unmeasured.sort(key=lambda x: -x[0].score)
    # Неизмеренные идут после измеренных и помечены: пустая выдача из-за отказа прибора
    # хуже, чем выдача с честной пометкой.
    scored += unmeasured[: max(0, 15 - len(scored))]
    job["unmeasured"] = len(unmeasured)
    job["dropped_out_of_domain"] = sum(1 for i in range(len(pool)) if not in_domain.get(i, True))

    cards = []
    for rank, (sig, cand) in enumerate(scored[:15], 1):
        item = {"rank": rank, "name_ru": cand["name_ru"], "name_en": sig.term,
                "mechanism": cand["mechanism"], "score": sig.score, "why": sig.notes,
                "signals": {"первое упоминание": sig.first_seen, "возраст_мес": sig.age_months,
                            "упоминаний всего": sig.total, "за 12 месяцев": sig.recent,
                            "игроков": sig.players, "стадия": sig.stage},
                "evidence": cand.get("evidence"), "source_url": cand.get("source_url")}
        cards.append(to_trend(item, rank - 1))
    return cards


def worker(job_id: str, request: SearchRequest) -> None:
    job = JOBS[job_id]
    try:
        load_env_file()
        settings = Settings()
        run = cached_run(request.query)
        if run is not None:
            job["stage"] = "найден сохранённый прогон"
            job["cached"] = True
        elif request.demo or DEMO:
            raise RuntimeError("демонстрационный режим: сохранённого прогона по этому запросу нет")
        else:
            job["stage"] = "поиск и извлечение"
            run = run_pool(known_area(request.query), request.query, "live", settings,
                           plan=request.plan)
        job["run_id"] = run.name
        job["trends"] = build_cards(run, job)
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        counters = manifest.get("counters") or {}
        job["funnel"] = {"queries": counters.get("queries", 0), "hits": counters.get("hits", 0),
                         "urls": counters.get("unique_urls", 0),
                         "documents": counters.get("parsed_ok", 0),
                         "candidates": counters.get("after_merge", 0),
                         "top": len(job["trends"]), "cost": manifest.get("cost_rub", 0)}
        job["plan"] = [n.split(":", 1)[1].strip() for n in counters.get("notes", [])
                       if n.startswith("подсегменты")][:1]
        job["status"] = "completed"
        job["stage"] = "готово"
    except Exception as exc:  # отдаём причину пользователю, а не молчаливый пустой ответ
        job["status"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["trace"] = traceback.format_exc()[-1200:]
    job["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.post("/api/search")
def search(request: SearchRequest) -> dict:
    if len(request.query.strip()) < 3:
        raise HTTPException(400, "запрос короче трёх символов")
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        JOBS[job_id] = {"id": job_id, "query": request.query, "status": "running",
                        "stage": "поставлено в очередь", "cached": False,
                        "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    threading.Thread(target=worker, args=(job_id, request), daemon=True).start()
    return {"job_id": job_id, "demo": DEMO}


@app.get("/api/search/{job_id}")
def status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "задание не найдено")
    return job


@app.get("/api/runs")
def runs() -> list[dict]:
    """Сохранённые прогоны: их можно открыть мгновенно и без расходов."""
    out = []
    for run in sorted(RUNS_DIR.glob("2026*"), reverse=True)[:40]:
        manifest = run / "manifest.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append({"run_id": data.get("run_id"), "query": data.get("query"),
                    "area": data.get("area"), "finished": data.get("finished_at"),
                    "cost": data.get("cost_rub")})
    return out


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "demo": DEMO, "runs": len(list(RUNS_DIR.glob("2026*")))}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
