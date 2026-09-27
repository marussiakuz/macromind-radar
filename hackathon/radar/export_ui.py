"""Выгрузка результатов прогона в интерфейс `tech-trend-searcher`.

Заказчик требует место, где пользователь задаёт запрос, и место, где выдаётся ответ;
отдельно отмечает, что список отбракованных кандидатов — плюс. Интерфейс это умеет, но
жил на выдуманных данных. Здесь настоящие прогоны превращаются в его формат.

Данные пишутся отдельным файлом `src/generated.ts`, который подключается в `data.ts`.
Так интерфейс работает и в режиме разработки, и в статической сборке, без сервера,
без запросов к сети и без ключей — это же и есть демонстрационный режим для жюри.

    python -m radar.export_ui --run radar-runs/<id> [--run ...]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

UI_SRC = Path(__file__).resolve().parents[2] / "tech-trend-searcher" / "src"

STAGE_RU = {"research": "исследование", "prototype": "прототип", "pilot": "прототип",
            "limited_sales": "продукт", "scaled": "продукт", "unknown": "исследование"}

# Доверие к источнику: без списка доверенных доменов заказчик предложил составить свой.
PRIMARY = ("arxiv.org", "github.com", "nist.gov", "ietf.org", "europa.eu", "acm.org",
           "ieee.org", "nature.com", "huggingface.co", "owasp.org", "cloudsecurityalliance.org")
MEDIA = ("techcrunch.com", "venturebeat.com", "forbes.ru", "reuters.com", "habr.com")


def host(url: str) -> str:
    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def trust_of(url: str) -> str:
    h = host(url)
    if any(h.endswith(d) for d in PRIMARY):
        return "высокий"
    if any(h.endswith(d) for d in MEDIA):
        return "средний"
    return "низкий"


def kind_of(signals: dict) -> str:
    """Ранний сигнал, хайп или «на слуху» — по тем же границам, что и окно зрелости."""
    total = signals.get("упоминаний всего") or 0
    recent = signals.get("за 12 месяцев") or 0
    if total >= 400:
        return "хайп" if recent / max(total, 1) > 0.5 else "на слуху"
    if total > 150:
        return "на слуху"
    return "ранний сигнал"


def ts(value: str) -> str:
    return value or "—"


def to_trend(item: dict, idx: int) -> dict:
    sig = item.get("signals") or {}
    sources = []
    for j, ev in enumerate(item.get("evidence") or []):
        url = ev.get("source_url") or item.get("source_url") or ""
        sources.append({
            "id": f"s{idx}-{j}", "title": host(url) or "источник",
            "date": ts(sig.get("первое упоминание")), "type": "статья", "url": url,
            "quote": ev.get("quote") or "", "language": "en",
            "trust": trust_of(url), "summaryRu": item.get("mechanism", "")[:200],
            "generated": False,
        })
    claims = [{"label": "Механизм", "text": item.get("mechanism", ""),
               "status": "supported" if sources else "unsupported",
               "sourceId": sources[0]["id"] if sources else None}]
    for note in (item.get("why") or [])[:4]:
        claims.append({"label": "Признак ранней стадии", "text": note, "status": "supported",
                       "sourceId": sources[0]["id"] if sources else None})
    first = (sig.get("первое упоминание") or "")[:4]
    return {
        "id": f"t{idx}", "name": item["name_ru"],
        "definition": item.get("mechanism", ""),
        "signal": min(99, int(round(float(item.get("score", 0)) * 8))),
        "firstYear": int(first) if first.isdigit() else datetime.now().year,
        "series": [0, 0, 0, sig.get("упоминаний всего", 0) - sig.get("за 12 месяцев", 0),
                   sig.get("за 12 месяцев", 0)],
        "stage": STAGE_RU.get(sig.get("стадия") or "unknown", "исследование"),
        "kind": kind_of(sig),
        "bank": "Требует экспертной проверки",
        "features": {
            "nT": sig.get("упоминаний всего", 0),
            "logGrowth": round((sig.get("за 12 месяцев", 0)) / max(sig.get("упоминаний всего", 1), 1), 2),
            "share": 0.0, "shareGrowth": 0.0,
            "age": sig.get("возраст_мес"), "orgs": sig.get("игроков", 0),
            "hhi": 0.0, "coverage": len(sources), "novelty": float(item.get("score", 0)),
        },
        "reasons": item.get("why") or [],
        "claims": claims, "sources": sources,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar.export_ui")
    ap.add_argument("--run", action="append", required=True)
    ap.add_argument("--out", default=str(UI_SRC / "generated.ts"))
    args = ap.parse_args(argv)

    trends, excluded, analyses, pool_total = [], [], [], 0
    funnel: dict = {}
    subsegments: list[str] = []
    for path in (Path(r) for r in args.run):
        top_file = path / "top.json"
        if not top_file.exists():
            print(f"пропущен {path.name}: нет top.json")
            continue
        data = json.loads(top_file.read_text(encoding="utf-8"))
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        pool_total += data.get("pool_size", 0)
        for item in data.get("top", []):
            trends.append(to_trend(item, len(trends)))
        for reason, count in (data.get("rejected_reasons") or {}).items():
            kind = ("зрелое" if "масштаб" in reason or "старше" in reason or "лет" in reason
                    else "хайп" if "громк" in reason else "шум")
            excluded.append({"name": f"{count} кандидатов", "reason": reason, "kind": kind})
        counters = manifest.get("counters") or {}
        if not funnel:
            funnel = {
                "queries": counters.get("queries", 0),
                "hits": counters.get("hits", 0),
                "urls": counters.get("unique_urls", 0),
                "documents": counters.get("parsed_ok", 0),
                "candidates": counters.get("after_merge", 0),
                "measured": len(data.get("top", [])) + sum((data.get("rejected_reasons") or {}).values()),
                "top": len(data.get("top", [])),
                "cost": manifest.get("cost_rub", 0),
            }
            for note in counters.get("notes") or []:
                if note.startswith("подсегменты"):
                    parts = [x.strip() for x in note.split(":", 1)[1].split(",")]
                    subsegments = [x for x in parts if len(x) > 12][:14]
        analyses.append({"id": manifest["run_id"][:14], "query": manifest["query"],
                         "year": 2026, "status": "completed", "count": len(data.get("top", [])),
                         "updated": manifest.get("finished_at", "")[:10]})

    body = f"""// Файл создан автоматически: python -m radar.export_ui
// Источник — сохранённые прогоны радара. Руками не править: перезапишется.
// Выгружено {datetime.now(timezone.utc).isoformat(timespec="seconds")}
import type {{ Trend, Analysis }} from "./data";

export const genTrends: Trend[] = {json.dumps(trends, ensure_ascii=False, indent=1)};

export const genAnalyses: Analysis[] = {json.dumps(analyses, ensure_ascii=False, indent=1)};

export const genExcluded = {json.dumps(excluded, ensure_ascii=False, indent=1)} as Array<{{
  name: string; reason: string; kind: "зрелое" | "хайп" | "шум";
}}>;

export const genPoolSize = {pool_total};

/** Воронка последнего прогона: настоящие счётчики, а не оформительские числа. */
export const genFunnel = {json.dumps(funnel, ensure_ascii=False, indent=1)};

/** План поиска: то, на что конвейер разбил направление перед поиском. */
export const genPlan: string[] = {json.dumps(subsegments, ensure_ascii=False, indent=1)};
"""
    out = Path(args.out)
    out.write_text(body, encoding="utf-8")
    print(f"трендов: {len(trends)}, отбраковок: {len(excluded)}, прогонов: {len(analyses)}")
    print(f"пул: {pool_total} кандидатов")
    print(f"файл: {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
