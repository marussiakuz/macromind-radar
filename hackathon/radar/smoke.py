"""Проверка Yandex Search API тремя ступенями.

Адаптер написан по документации и живым вызовом не проверялся, поэтому первая
ступень смотрит на сырой ответ: состав JSON, декодирование Base64, разбор XML.
Каждая ступень тратит деньги, поэтому запускается отдельно и только с --confirm.

    python -m radar.smoke one     --confirm
    python -m radar.smoke queries --confirm --area "Защита ИИ"
    python -m radar.smoke load    --confirm

Ключи берутся из hackathon/.env и в артефакты прогона не попадают.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import openpyxl
from lxml import etree

from .config import CUSTOMER_XLSX, RUNS_DIR, Settings, load_env_file
from .evaluate import name_similarity
from .reference import area_items, load_reference, normalize_tokens
from .search import LENSES, parse_yandex_xml

PRICE_PER_CALL = 0.488  # ₽, дневной синхронный тариф по разделу 12 отчёта


def _out_dir() -> Path:
    d = RUNS_DIR / ("smoke-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _settings() -> Settings:
    load_env_file()
    s = Settings()
    if not s.yandex_api_key:
        raise SystemExit("нет YANDEX_API_KEY: положите ключ в hackathon/.env")
    if not s.yandex_folder_id:
        raise SystemExit("нет YANDEX_FOLDER_ID: Search API требует каталог")
    return s


def _body(s: Settings, query: str, lang: str) -> dict:
    return {
        "query": {
            "searchType": "SEARCH_TYPE_RU" if lang == "ru" else "SEARCH_TYPE_COM",
            "queryText": query,
            "page": "0",
        },
        "folderId": s.yandex_folder_id,
        "responseFormat": "FORMAT_XML",
    }


def _post(s: Settings, query: str, lang: str, timeout: float = 30.0) -> tuple[httpx.Response, float]:
    started = time.monotonic()
    r = httpx.post(
        s.search_endpoint,
        headers={"Authorization": f"Api-Key {s.yandex_api_key}"},
        json=_body(s, query, lang),
        timeout=timeout,
    )
    return r, time.monotonic() - started


def stage_one(s: Settings, out: Path) -> None:
    """Один запрос: смотрим, что реально приходит, и сходится ли адаптер."""
    query = "сканеры безопасности MCP-серверов"
    r, elapsed = _post(s, query, "ru")
    print(f"HTTP {r.status_code}, {elapsed:.2f} с, тело {len(r.content)} байт")
    if r.status_code != 200:
        print("Ответ:", r.text[:800])
        (out / "stage1-error.txt").write_text(r.text[:5000], encoding="utf-8")
        raise SystemExit("запрос не прошёл: смотрите текст ошибки выше")

    data = r.json()
    print("ключи JSON:", sorted(data.keys()))
    raw = data.get("rawData")
    if not raw:
        (out / "stage1-body.json").write_text(json.dumps(data, ensure_ascii=False)[:20000], encoding="utf-8")
        raise SystemExit("в ответе нет rawData: адаптер нужно поправить, тело сохранено")

    xml = base64.b64decode(raw)
    (out / "stage1.xml").write_bytes(xml)
    root = etree.fromstring(xml)
    docs = root.findall(".//doc")
    print(f"Base64 разобран, XML {len(xml)} байт, найдено doc: {len(docs)}")

    hits = parse_yandex_xml(xml, query, "ru", "mechanism", 10)
    print(f"адаптер вернул позиций: {len(hits)}")
    for h in hits[:3]:
        print(f"  {h.position}. {h.title[:70]} — {h.url[:80]}")
    verdict = "адаптер работает" if hits else "XML пришёл, но адаптер ничего не извлёк: проверить имена узлов"
    print("\nВывод:", verdict)
    (out / "stage1.json").write_text(json.dumps(
        {"status": r.status_code, "elapsed_s": round(elapsed, 3), "json_keys": sorted(data.keys()),
         "docs_in_xml": len(docs), "hits_parsed": len(hits), "verdict": verdict},
        ensure_ascii=False, indent=2), encoding="utf-8")


def _table_hosts() -> set[str]:
    wb = openpyxl.load_workbook(CUSTOMER_XLSX, read_only=True)
    ws = wb["Слабые сигналы"]
    hosts: set[str] = set()
    for row in ws.iter_rows(min_row=3, max_row=102, min_col=10, max_col=10, values_only=True):
        for url in re.findall(r"https?://[^\s,;)\]\"]+", str(row[0] or "")):
            host = (urlparse(url).hostname or "").lower()
            if host.startswith("www."):
                host = host[4:]
            hosts.add(host)
    wb.close()
    return hosts


def stage_queries(s: Settings, out: Path, area: str, subsegments: list[str]) -> None:
    """Шесть запросов «подсегмент × линза»: видно ли узкие категории таблицы."""
    reference, _ = load_reference()
    items = area_items(reference, area)
    table_hosts = _table_hosts()

    plan: list[tuple[str, str, str]] = []
    for sub in subsegments[:3]:
        for lens, langs in LENSES.items():
            # Язык подсегмента и язык шаблона должны совпадать: иначе получается
            # запрос-химера и проверка ничего не значит.
            lang = "en" if re.search(r"[a-zA-Z]", sub) and not re.search(r"[а-яА-Я]", sub) else "ru"
            plan.append((langs[lang].format(sub=sub), lang, lens))
    plan = plan[:6]

    rows = []
    seen_refs: dict[int, str] = {}
    all_hosts: set[str] = set()
    for query, lang, lens in plan:
        r, elapsed = _post(s, query, lang)
        if r.status_code != 200:
            rows.append({"query": query, "lang": lang, "status": r.status_code, "error": r.text[:200]})
            print(f"  [{r.status_code}] {query[:60]}")
            continue
        raw = r.json().get("rawData")
        hits = parse_yandex_xml(base64.b64decode(raw), query, lang, lens, 10) if raw else []
        hosts = set()
        for h in hits:
            host = (urlparse(h.url).hostname or "").lower()
            hosts.add(host[4:] if host.startswith("www.") else host)
            text_tokens = normalize_tokens(f"{h.title} {h.snippet}")
            for item in items:
                if name_similarity(text_tokens, item.tokens) >= 0.34:
                    seen_refs.setdefault(item.number, h.url)
        all_hosts |= hosts
        rows.append({"query": query, "lang": lang, "lens": lens, "status": 200,
                     "elapsed_s": round(elapsed, 2), "hits": len(hits),
                     "hosts": sorted(hosts), "from_table": sorted(hosts & table_hosts)})
        print(f"  {len(hits):2d} позиций, {elapsed:5.2f} с | {query[:58]}")

    overlap = all_hosts & table_hosts
    print(f"\nРазных хостов в выдаче: {len(all_hosts)}; из них есть в таблице заказчика: {len(overlap)}")
    print(f"Похоже на категории таблицы «{area}»: {len(seen_refs)} из {len(items)}")
    for number, url in sorted(seen_refs.items()):
        name = next(i.name for i in items if i.number == number)
        print(f"  №{number} {name[:60]} ← {url[:70]}")
    print("\nЭто грубая оценка по заголовкам и сниппетам, без загрузки страниц.")
    (out / "stage2.json").write_text(json.dumps(
        {"area": area, "subsegments": subsegments[:3], "queries": rows,
         "hosts_total": len(all_hosts), "hosts_from_table": sorted(overlap),
         "reference_hits": {str(k): v for k, v in seen_refs.items()},
         "reference_total": len(items)}, ensure_ascii=False, indent=2), encoding="utf-8")


def stage_load(s: Settings, out: Path, calls: int = 20, parallel: int = 8) -> None:
    """Нагрузочная: задержка и отказы при восьми параллельных вызовах."""
    queries = [f"AI security startup pilot 2026 test {i}" for i in range(calls)]

    def one(q: str) -> tuple[int, float]:
        try:
            r, elapsed = _post(s, q, "en", timeout=40.0)
            return r.status_code, elapsed
        except httpx.HTTPError:
            return 0, 0.0

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        results = list(pool.map(one, queries))
    wall = time.monotonic() - started

    ok = [e for code, e in results if code == 200]
    codes: dict[int, int] = {}
    for code, _ in results:
        codes[code] = codes.get(code, 0) + 1
    ok_sorted = sorted(ok)
    p50 = statistics.median(ok_sorted) if ok_sorted else 0.0
    p95 = ok_sorted[int(len(ok_sorted) * 0.95) - 1] if len(ok_sorted) >= 2 else (ok_sorted[0] if ok_sorted else 0.0)
    print(f"{calls} вызовов по {parallel} параллельно за {wall:.1f} с")
    print(f"коды ответов: {codes}")
    print(f"медиана {p50:.2f} с, p95 {p95:.2f} с (оценка на {len(ok)} успешных)")
    print(f"порог из плана: p95 ≤ 8 с, доля 429 ≤ 5 %")
    (out / "stage3.json").write_text(json.dumps(
        {"calls": calls, "parallel": parallel, "wall_s": round(wall, 2), "codes": codes,
         "p50_s": round(p50, 3), "p95_s": round(p95, 3)}, ensure_ascii=False, indent=2), encoding="utf-8")


def stage_llm(s: Settings, out: Path) -> None:
    """Один вызов модели: отвечает ли, держит ли структурированный ответ."""
    from .extract import YandexLLM

    llm = YandexLLM(s, max_tokens=300)
    payload = {"manifest": {"document_id": "test", "title": "Проверка"},
               "spans": [{"span_id": "s1", "heading": "Тест",
                          "text": "The scanner inspects Model Context Protocol servers and flags tool poisoning."}],
               "schema": {"type": "object", "required": ["ok", "mechanism"],
                          "properties": {"ok": {"type": "boolean"}, "mechanism": {"type": "string"}}}}
    system = ("Верни только JSON по схеме: {\"ok\": true, \"mechanism\": \"<механизм из текста spans>\"}. "
              "Ничего не добавляй от себя.")
    started = time.monotonic()
    try:
        text, tin, tout = llm.complete(system, payload)
    except httpx.HTTPStatusError as e:
        print(f"HTTP {e.response.status_code}: {e.response.text[:400]}")
        (out / "llm-error.txt").write_text(e.response.text[:4000], encoding="utf-8")
        raise SystemExit("модель не ответила: смотрите текст ошибки")
    elapsed = time.monotonic() - started
    print(f"модель ответила за {elapsed:.2f} с; токены: вход {tin}, выход {tout}")
    print("ответ:", text[:300].replace("\n", " "))
    parsed = None
    try:
        parsed = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        pass
    print("JSON разобран:", "да" if parsed else "нет")
    (out / "llm.json").write_text(json.dumps(
        {"model": s.model_uri, "elapsed_s": round(elapsed, 2), "input_tokens": tin,
         "output_tokens": tout, "json_ok": bool(parsed), "answer": text[:1000]},
        ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar.smoke", description="Проверка Yandex Search API")
    parser.add_argument("stage", choices=["one", "queries", "load", "llm"])
    parser.add_argument("--confirm", action="store_true", help="разрешить платные вызовы")
    parser.add_argument("--area", default="Защита ИИ")
    parser.add_argument("--subsegments", nargs="*", default=[
        "безопасность ИИ-агентов", "защита LLM-приложений", "проверка происхождения моделей"])
    parser.add_argument("--calls", type=int, default=20)
    args = parser.parse_args(argv)

    if args.stage == "llm":
        cost = 0.1  # ≈ по токенам, а не по вызовам
    else:
        cost = {"one": 1, "queries": 6, "load": args.calls}[args.stage] * PRICE_PER_CALL
    if not args.confirm:
        print(f"Ступень «{args.stage}» сделает платные вызовы примерно на {cost:.2f} ₽.")
        print("Запустите с --confirm, если согласны.")
        return 0

    s = _settings()
    out = _out_dir()
    print(f"Артефакты: {out}\n")
    if args.stage == "one":
        stage_one(s, out)
    elif args.stage == "queries":
        stage_queries(s, out, args.area, args.subsegments)
    elif args.stage == "llm":
        stage_llm(s, out)
    else:
        stage_load(s, out, args.calls)
    print(f"\nПотрачено ≈{cost:.2f} ₽ по тарифу {PRICE_PER_CALL} ₽ за вызов.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
