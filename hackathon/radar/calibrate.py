"""Калибровка окна зрелости по эталонным примерам заказчика.

Заказчик прямо предлагает так делать: «на основе того, что все технологии из данного
файла являются слабыми сигналами, отрегулировать весовое распределение в вашей модели».
Сто строк таблицы — это сто положительных примеров, размеченных экспертами отрасли.

Что здесь считается. Для каждой эталонной технологии берётся её термин, замеряются
возраст, общее число упоминаний, доля свежих. Затем по распределению этих величин
выбираются границы окна: не из головы, а там, где реально лежат настоящие слабые сигналы.

Важно, чем это НЕ является. Это калибровка порогов, а не обучение классификатора и не
проверка качества. Пороги, выведенные на этих ста примерах, нельзя потом предъявлять как
успех на них же: заявлять улучшение можно только на другой выборке.

    python -m radar.calibrate --area "Защита ИИ" --area "Финтех"
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

from .config import RUNS_DIR
from .rank import HackerNewsProbe, MaturityProbe, OpenAlexProbe
from .reference import area_items, load_reference

# Эталон записан по-русски с английскими вставками в скобках: «Know Your Agent (KYA) —
# верифицируемая идентификация». Для замера нужен именно английский термин.
_EN = re.compile(r"[A-Za-z][A-Za-z0-9\- ]{3,}")


REF_TERM_SYSTEM = """Ты выписываешь общепринятый английский термин технологии.

Для каждой строки дана формулировка на русском с английскими вставками. Верни термин,
которым эту технологию называют в англоязычных статьях и документации: 1–4 слова.

Это должен быть термин технологии целиком, а не вырванный фрагмент. Для «Машинные
микроплатежи по HTTP 402» правильный ответ — «HTTP 402 micropayments», а не «HTTP 402»:
сам по себе HTTP 402 это код состояния протокола из 1997 года, и по нему измерится не
та вещь. Для «Переиспользуемые ZK-верифицируемые credentials» — «reusable verifiable
credentials», а не «credentials».

Не бери общие слова («credentials», «receipts»), названия законов и организаций, если
технология не называется их именем.

Верни только JSON: {"terms": [{"index": <номер>, "term": "<термин>"}]}."""


def term_of_reference(name: str) -> str | None:
    """Запасной путь без модели: самый длинный фрагмент латиницей.

    Проверено 27.09.2026: регулярка выдаёт обрывки — «credentials», «receipts»,
    «HTTP 402», — и калибровка по ним даёт бессмысленное распределение (медианный
    «возраст слабого сигнала» 112 месяцев). Основной путь — спросить модель.
    """
    parts = [p.strip(" -—,.()«»") for p in _EN.findall(name)]
    parts = [p for p in parts if len(p.split()) <= 6 and len(p) > 4]
    return max(parts, key=len) if parts else None


def terms_by_model(rows, llm, batch: int = 12) -> dict[int, str]:
    """Канонические термины эталонных строк одним-двумя вызовами модели."""
    out: dict[int, str] = {}
    for start in range(0, len(rows), batch):
        chunk = rows[start:start + batch]
        payload = {"строки": [{"index": start + j, "формулировка": r.name}
                              for j, r in enumerate(chunk)]}
        try:
            text, _, _ = llm.complete(REF_TERM_SYSTEM, payload)
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        except (ValueError, KeyError):
            continue
        for row in data.get("terms", []):
            idx, term = row.get("index"), row.get("term")
            if isinstance(idx, int) and start <= idx < start + len(chunk) and term:
                term = str(term).strip()
                if 3 < len(term) <= 60:
                    out[idx] = term
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar.calibrate")
    ap.add_argument("--area", action="append", required=True)
    ap.add_argument("--out", default=str(RUNS_DIR / "calibration.json"))
    args = ap.parse_args(argv)

    reference, _ = load_reference()
    rows = []
    for area in args.area:
        rows.extend(area_items(reference, area))
    print(f"эталонных строк: {len(rows)}")

    from .config import Settings, load_env_file
    from .extract import YandexLLM
    load_env_file()
    model_terms = terms_by_model(rows, YandexLLM(Settings(), max_tokens=1200))
    print(f"термин от модели получен для {len(model_terms)} из {len(rows)} строк\n")

    probe = MaturityProbe([OpenAlexProbe(), HackerNewsProbe()])
    measured, skipped = [], []
    for i, item in enumerate(rows):
        term = model_terms.get(i) or term_of_reference(item.name)
        if not term:
            skipped.append((item.number, item.name, "нет английского термина"))
            continue
        first, total, recent = probe.probe(term)
        if total < 0:
            skipped.append((item.number, term, "источники не ответили"))
            continue
        age = None
        if first:
            try:
                y, m, _ = (first.split("-") + ["1", "1"])[:3]
                age = round((2026 - int(y)) * 12 + (9 - int(m)), 1)
            except ValueError:
                age = None
        measured.append({"number": item.number, "term": term, "first": first, "age": age,
                         "total": total, "recent": recent,
                         "share": round(recent / total, 3) if total else 0.0,
                         "source": probe.source_of.get(term, "?")})
        print(f"  №{item.number:3d} {term[:34]:34s} всего {total:6d} за год {recent:5d} "
              f"возраст {age if age is not None else '—'}")
    probe.close()

    def pct(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        k = max(0, min(len(values) - 1, int(round(p * (len(values) - 1)))))
        return round(values[k], 2)

    totals = [m["total"] for m in measured]
    ages = [m["age"] for m in measured if m["age"] is not None]
    shares = [m["share"] for m in measured]
    report = {
        "измерено": len(measured), "пропущено": len(skipped),
        "упоминаний всего": {"медиана": pct(totals, 0.5), "p75": pct(totals, 0.75),
                             "p90": pct(totals, 0.90), "максимум": max(totals) if totals else 0},
        "возраст термина, мес": {"медиана": pct(ages, 0.5), "p75": pct(ages, 0.75),
                                 "p90": pct(ages, 0.90), "максимум": max(ages) if ages else 0},
        "доля свежих": {"медиана": pct(shares, 0.5), "p25": pct(shares, 0.25)},
        "предлагаемые границы": {
            "громкость, верх": pct(totals, 0.90),
            "возраст, верх (мес)": pct(ages, 0.90),
            "доля свежих, низ": pct(shares, 0.25),
        },
        "строки": measured, "пропуски": skipped,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nизмерено {len(measured)}, пропущено {len(skipped)}")
    for key in ("упоминаний всего", "возраст термина, мес", "доля свежих"):
        print(f"  {key}: {report[key]}")
    print(f"\nграницы по распределению эталона: {report['предлагаемые границы']}")
    print(f"вызовов к источникам: {probe.calls} (бесплатно)")
    print(f"файл: {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
