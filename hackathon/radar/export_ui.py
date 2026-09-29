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


def to_trend(item: dict, idx: int, doc_dates: dict[str, str] | None = None) -> dict:
    """Карточка для интерфейса. `doc_dates` — дата публикации по адресу документа.

    Разбор аналитика 28.09.2026: во всех 43 источниках тридцати позиций стояло «—», хотя
    у 33 документов из 47 дата публикации в прогоне есть. Причина: здесь бралась только
    дата события из извлечения, а дата документа игнорировалась. Эксперт заказчика без
    даты не отличает сигнал 2026 года от пересказа истории 2016-го, а в таблице заказчика
    к каждой строке приложена хроника событий. Это была самая дешёвая из потерь.
    """
    sig = item.get("signals") or {}
    sources = []
    for j, ev in enumerate(item.get("evidence") or []):
        url = ev.get("source_url") or item.get("source_url") or ""
        sources.append({
            "id": f"s{idx}-{j}", "title": host(url) or "источник",
            # Дата документа, а не first_seen из индекса упоминаний: это разные вещи,
            # и подставлять одну вместо другой — приписывать источнику чужую дату.
            # Порядок: дата публикации документа, затем дата события из извлечения.
            # Обе — разные вещи, поэтому вторая помечается словом «событие».
            "date": ts((doc_dates or {}).get(url) or (doc_dates or {}).get(url.rstrip("/"))),
            "eventDate": ts(ev.get("event_date") or item.get("event_date")),
            "type": "статья", "url": url,
            "quote": ev.get("quote") or "", "language": "en",
            "trust": trust_of(url), "summaryRu": item.get("mechanism", "")[:200],
            "generated": False,
        })
    claims = [{"label": "Механизм", "text": item.get("mechanism", ""),
               "status": "supported" if sources else "unsupported",
               "sourceId": sources[0]["id"] if sources else None}]
    # Признаки ранней стадии выведены из замера упоминаний, а не из документа. Вешать
    # на них ссылку на первый источник — приписывать ему то, чего в нём нет.
    # Аналитик 28.09.2026: у 18 позиций из 30 список реализаторов пуст, а в признаках
    # написано «названы 3 организации» и «3 независимых игроков». Это разные величины:
    # первая — организации, упомянутые в документах пула, вторая — результат второго
    # поиска. Расхождение обещания и содержимого карточки подрывает доверие ко всем
    # остальным признакам, поэтому формулировки разводим по существу.
    # Организации, названные прямо в источнике, раньше в карточку не попадали: в `players`
    # шёл только результат второго поиска. Замер ML-инженера 28.09.2026: у 14 позиций из 15
    # в каждом прогоне организации в кандидате есть (Google и FIDO Alliance, JFrog и
    # Hugging Face, Visa, Palo Alto, IBM), а на экране стояло «игроки не найдены» — при том
    # что в признаках было написано «названы 3 организации». Роль указываем честно: это не
    # проверенный реализатор, а организация, упомянутая в тексте источника.
    players = list(item.get("players") or [])
    known = {(p.get("name") or "").strip().lower() for p in players}
    for org in (item.get("organizations") or []):
        name = str(org).strip()
        if name and name.lower() not in known and len(players) < 8:
            known.add(name.lower())
            players.append({"name": name, "role": "mentioned",
                            "what": "названа в источнике этой позиции",
                            "quote": "", "url": item.get("source_url", "")})
    found = len(players)
    for note in (item.get("why") or [])[:4]:
        low = note.lower()
        if not found and ("независимых игроков" in low or "два игрока" in low
                          or low.startswith("названы")):
            note = (note.replace("независимых игроков", "организаций упомянуто в источниках пула")
                        .replace("два игрока", "две организации упомянуты в источниках пула")
                        .replace("названы", "в источниках пула упомянуты"))
            note += " — реализаторы вторым поиском не найдены"
        claims.append({"label": "Признак ранней стадии", "text": note,
                       "status": "hypothesis", "sourceId": None})
    # Балл — это сумма признаков, а не вероятность. Умножать его на 8 и подписывать
    # «уверенность модели 80 %» нельзя: калибровки вероятностей у нас нет, и такая
    # подпись — выдуманная точность. Показываем сам балл и словесный уровень.
    score = float(item.get("score", 0))
    first = (sig.get("первое упоминание") or "")[:4]
    total = sig.get("упоминаний всего") or 0
    recent = sig.get("за 12 месяцев") or 0
    # Ряд строим, только если есть что показать: два сопоставимых интервала.
    # Раньше здесь стояли три нуля подряд, и график выглядел взрывным ростом на
    # пустом месте.
    series = [total - recent, recent] if total > 0 else []
    return {
        "id": f"t{idx}", "name": item["name_ru"],
        # Канонический термин нужен метрике и своду дублей по механизму:
        # без него две карточки про трансграничные стейблкоины считались
        # разными механизмами (замер ML-инженера 28.09.2026).
        "nameEn": item.get("name_en"),
        "definition": item.get("mechanism", ""),
        "signal": round(score, 1),
        # Окно зрелости даёт до 11 баллов, но сверху идут надбавки: подтверждение с разных
        # доменов и найденные вторым поиском реализаторы. Поэтому потолок не константа —
        # при 11,5 из 11,0 жюри справедливо спросит, что мы считаем. Исправлено 28.09.2026.
        "scoreMax": max(11.0, round(score, 1)),
        "firstYear": int(first) if first.isdigit() else None,
        "series": series,
        "stage": STAGE_RU.get(sig.get("стадия") or "unknown", "исследование"),
        "kind": ("ранний сигнал" if item['assessment'].get('stage') == 'early'
                 else "стадия не подтверждена") if item.get('assessment') else kind_of(sig),
        "assessment": item.get('assessment') or {},
        "bank": "Требует экспертной проверки",
        "features": {
            "nT": sig.get("упоминаний всего", 0),
            "logGrowth": round((sig.get("за 12 месяцев", 0)) / max(sig.get("упоминаний всего", 1), 1), 2),
            "share": 0.0, "shareGrowth": 0.0,
            "age": sig.get("возраст_мес"), "orgs": sig.get("игроков", 0),
            "hhi": 0.0, "coverage": len(sources), "novelty": float(item.get("score", 0)),
        },
        "reasons": item.get("why") or [],
        "players": players,
        # Хроника и сделки — то, чем таблица заказчика описывает каждую строку. Пустые поля
        # были главной причиной отказа эксперта, поэтому они выведены отдельно и с цитатой.
        "chronology": item.get("chronology") or [],
        "rounds": item.get("rounds") or [],
        "independentDomains": item.get("independent_domains") or [],
        "tier": item.get("tier", "review"),
        "verdict": item.get("verdict", ""),
        "claims": claims, "sources": sources,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar.export_ui")
    ap.add_argument("--run", action="append", default=[])
    # Готовые карточки сервиса. `top.json` пишет только CLI `radar.top`, а сервис
    # складывает разбор в `cards.json` — без этого пути статическая демонстрация
    # обновлялась пустой выгрузкой (найдено при подготовке сдачи 29.09.2026).
    ap.add_argument("--cards", action="append", default=[],
                    help="cards.json прогона: разбор, собранный сервисом")
    ap.add_argument("--out", default=str(UI_SRC / "generated.ts"))
    args = ap.parse_args(argv)

    if not args.run and not args.cards:
        ap.error("нужен хотя бы один --run или --cards")
    trends, excluded, analyses, pool_total = [], [], [], 0
    funnel: dict = {}
    subsegments: list[str] = []

    for raw in args.cards:
        path = Path(raw)
        data = json.loads(path.read_text(encoding="utf-8"))
        # Карточки уже в формате интерфейса: переносим как есть, только перенумеровав.
        for card in data.get("trends") or []:
            trends.append({**card, "id": f"t{len(trends)}"})
        for item in (data.get("rejected") or [])[:12]:
            reason = str(item.get("reason") or "")
            kind = ("зрелое" if "зрел" in reason or "масштаб" in reason or "лет" in reason
                    else "хайп" if "громк" in reason else "шум")
            excluded.append({"name": item.get("name", "")[:90], "reason": reason, "kind": kind})
        if not funnel:
            funnel = data.get("funnel") or {}
        run_dir = path.parent
        manifest_file = run_dir / "manifest.json"
        if manifest_file.exists():
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            pool_total += (manifest.get("counters") or {}).get("after_merge", 0)
            analyses.append({"id": run_dir.name, "query": manifest.get("query", ""),
                             "year": 2026, "status": "completed",
                             "count": len(data.get("trends") or []),
                             "cost": manifest.get("cost_rub", 0),
                             "updated": (manifest.get("finished_at")
                                         or manifest.get("started_at") or "")[:10]})
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
