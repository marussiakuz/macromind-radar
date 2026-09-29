"""Набор для обучения реранкера: градуированные оценки агента-аналитика плюс числовые признаки.

Честно о происхождении меток. Человеческих оценок **ноль**. Единственные градуированные
оценки по позициям, какие у нас есть, — приговоры агента-аналитика банка, вынесенные по
критерию приёмки заказчика: «да», «спорно, скорее да», «спорно, скорее нет», «нет». Это
`agent_review`, а не gold: агент пользовался веб-поиском и рубрикой, но экспертом заказчика
не является. Любой результат обучения на этих метках — диагностика, не проверенное качество.

Признаки только числовые и только те, что сервис знает сам. Текст в признаки не идёт
намеренно: аудит датасета «300» показал, что по стилю текста происхождение набора угадывается
в 64–71 случае из 87, то есть текстовая модель выучит составителя, а не слабость сигнала.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HACK))

# Рубрика 0–3 из формулировок приговора. Порядок проверок важен: «спорно, скорее нет»
# содержит и «спорно», и «нет».
GRADES = (("спорно, скорее да", 2), ("спорно, скорее нет", 1), ("скорее да", 2),
          ("скорее нет", 1), ("спорно", 1), ("нет", 0), ("да", 3))
ROW = re.compile(r"^\|\s*(t\d+)\s*\|\s*([^|]+?)\s*\|\s*\*\*([^*]+)\*\*\s*\|", re.MULTILINE)


def grade_of(verdict: str) -> int | None:
    low = verdict.strip().lower()
    for token, value in GRADES:
        if token in low:
            return value
    return None


def parse_report(path: Path) -> list[dict]:
    """Приговоры из таблиц отчёта. Область определяется по предшествующему заголовку."""
    text = path.read_text(encoding="utf-8")
    out = []
    for match in ROW.finditer(text):
        card_id, name, verdict = match.group(1), match.group(2), match.group(3)
        grade = grade_of(verdict)
        if grade is None:
            continue
        head = text[:match.start()]
        area = "Финтех" if head.rfind("Финтех") > head.rfind("Защита") else "Защита ИИ"
        out.append({"card_id": card_id, "name": name.strip(), "verdict": verdict.strip(),
                    "grade": grade, "area": area})
    return out


def features_of(card: dict) -> dict:
    """Признаки, доступные сервису: без текста, без меток, без вердиктов."""
    feats = card.get("features") or {}
    sources = card.get("sources") or []
    players = card.get("players") or []
    rounds = card.get("rounds") or []
    chrono = card.get("chronology") or []
    roles = {p.get("role") for p in players}
    dated_rounds = [r for r in rounds if r.get("date")]
    return {
        "балл": float(card.get("signal") or 0),
        "возраст_мес": float(feats.get("age") or 0),
        "упоминаний": float(feats.get("nT") or 0),
        "доля_свежего": float(feats.get("share") or 0),
        "организаций": float(feats.get("orgs") or 0),
        "игроков": float(len(players)),
        "реализаторов": float(sum(1 for p in players
                                  if p.get("role") in ("developer", "deployer", "researcher"))),
        "ролей_разных": float(len(roles)),
        "раундов": float(len(rounds)),
        "раундов_с_датой": float(len(dated_rounds)),
        "событий_хроники": float(len(chrono)),
        "независимых_доменов": float(len(card.get("independentDomains") or [])),
        "источников": float(len(sources)),
        "источников_с_датой": float(sum(1 for s in sources if s.get("date") not in (None, "—"))),
        "первый_год": float(card.get("firstYear") or 0),
        "уверенный": 1.0 if card.get("tier") == "signal" else 0.0,
    }


def family_of(card: dict) -> str:
    """Семья технологии для разделения: одинаковые записи не должны попасть в разные части."""
    from radar.merging import modifiers_of, text_of
    blob = text_of({"name_ru": card.get("name", ""), "mechanism": card.get("definition", "")})
    mods = sorted(modifiers_of(blob))
    words = [w for w in re.findall(r"[а-яёa-z]{6,}", blob.lower())][:2]
    return "|".join(mods or words) or "прочее"


def main() -> int:
    reports = [HACK / "bench/analyst-review-3-2026-09-28.md"]
    snapshots = {"Финтех": Path("/tmp/final3-финтех.json"),
                 "Защита ИИ": Path("/tmp/final3-защита.json")}
    cards: dict[tuple[str, str], dict] = {}
    for area, path in snapshots.items():
        if not path.exists():
            print(f"нет снимка карточек для «{area}»: {path}")
            continue
        for card in json.loads(path.read_text(encoding="utf-8")).get("trends") or []:
            cards[(area, card["id"])] = card

    rows = []
    missing = 0
    for report in reports:
        for verdict in parse_report(report):
            card = cards.get((verdict["area"], verdict["card_id"]))
            if card is None:
                missing += 1
                continue
            rows.append({**verdict, "features": features_of(card), "family": family_of(card),
                         "label_source": "agent_review", "human_confirmed": False,
                         "report": report.name})
    out = HACK / "learning/rank-dataset-20260929.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    grades = {}
    for r in rows:
        grades[r["grade"]] = grades.get(r["grade"], 0) + 1
    print(f"позиций с оценкой: {len(rows)} (не сопоставлено с карточкой: {missing})")
    print("распределение оценок 0–3:", dict(sorted(grades.items())))
    print("областей:", {a: sum(1 for r in rows if r['area'] == a) for a in {r['area'] for r in rows}})
    print("семей:", len({r["family"] for r in rows}))
    print("сохранено:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
