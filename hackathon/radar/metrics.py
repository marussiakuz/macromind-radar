"""Диагностические показатели качества карточек и привязки доказательств.

Эти показатели не заменяют экспертную оценку точности выдачи."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from .corroborate import normalize_org

# Цитата короче этого порога не считается проверяемой: строка из пяти символов найдётся
# в любом документе, и проверка выродится в тавтологию. Замер 28.09.2026 на двух
# сохранённых прогонах: самая короткая цитата в карточках — 42 символа, так что порог
# никого из них не отсекает и служит защитой от вырожденного случая.
MIN_QUOTE = 20

# Окно свежести события из определения.
FRESH_MONTHS = 24

R_NO_QUOTE = "нет цитаты длиннее 20 символов"
R_QUOTE_UNVERIFIED = "цитата не найдена в тексте документа"
R_NO_DOCS = "текст документа не сохранён — проверить цитату нечем"
R_NO_PLAYER = "не назван ни один игрок-организация"
R_NO_DATE_NO_INDEX = "нет ни датированного события, ни замера в индексе"


def _norm_space(text: str) -> str:
    """Схлопывание пробелов: в сохранённом тексте переносы строк стоят иначе, чем в цитате.

    Регистр и символы не меняются — «дословно» проверяется дословно.
    """
    return " ".join((text or "").split())


def _norm_name(name: str) -> str:
    """Ключ названия позиции: без регистра, пунктуации и лишних пробелов."""
    s = re.sub(r"[^0-9A-Za-zА-Яа-яёЁ\s-]", " ", (name or "").lower())
    return " ".join(s.split())


def _parse_date(value: object) -> date | None:
    """Дата события из карточки. «—», пустая строка и мусор дают None, а не сегодня."""
    text = str(value or "").strip()
    if not text or text in {"—", "-", "null", "none"}:
        return None
    text = text[:10]
    for fmt, pad in (("%Y-%m-%d", None), ("%Y-%m", "-01"), ("%Y", "-01-01")):
        try:
            return datetime.strptime(text if pad is None else text[:7 if pad == "-01" else 4] + pad,
                                     "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def _months_between(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


@dataclass
class PositionCheck:
    """Разбор одной позиции по трём критериям определения."""

    id: str
    name: str
    term: str | None
    quote_ok: bool
    quote_checked: int          # сколько цитат удалось сверить с сохранённым текстом
    players: int                # уникальных названных организаций
    dated_ok: bool
    measured_ok: bool
    reasons: list[str] = field(default_factory=list)
    key: str = ""               # ключ механизма для склейки дублей

    @property
    def grounded(self) -> bool:
        return self.quote_ok and self.players >= 1 and (self.dated_ok or self.measured_ok)


@dataclass
class Report:
    positions: int
    grounded_positions: int
    grounded_mechanisms: int
    unique_mechanisms: int
    two_players: int
    reasons: Counter
    rows: list[PositionCheck]
    # Диагностика, а не часть метрики: у скольких позиций организация названа в кандидате
    # пула, но не доехала до карточки. Эксперт голосует по карточке, поэтому в метрику это
    # не входит; но разница между «игрока нет» и «игрок есть, но его не показали» — это
    # разные задачи, и смешивать их в одной цифре нельзя.
    players_in_pool: int | None = None

    def as_dict(self) -> dict:
        return {
            "позиций": self.positions,
            "обоснованных позиций": self.grounded_positions,
            "обоснованных механизмов": self.grounded_mechanisms,
            "уникальных механизмов": self.unique_mechanisms,
            "позиций с 2+ независимыми игроками": self.two_players,
            "диагностика: организация есть в пуле, но не в карточке": self.players_in_pool,
            "причины непрохождения": dict(self.reasons),
            "позиции": [
                {"id": r.id, "название": r.name, "термин": r.term,
                 "цитата подтверждена": r.quote_ok, "игроков": r.players,
                 "датировано": r.dated_ok, "измерено в индексе": r.measured_ok,
                 "обоснован": r.grounded, "причины": r.reasons}
                for r in self.rows],
        }


def _sources_of(pos: dict) -> list[dict]:
    """Карточки интерфейса хранят источники в `sources`, сырые позиции — в `evidence`."""
    if pos.get("sources"):
        return list(pos["sources"])
    out = []
    for ev in pos.get("evidence") or []:
        out.append({"quote": ev.get("quote"), "url": ev.get("source_url") or pos.get("source_url"),
                    "date": ev.get("event_date") or pos.get("event_date")})
    return out


def _players_of(pos: dict) -> int:
    """Названные организации, склеенные по нормализованному имени.

    Считаются только имена: число `features.orgs` — это счётчик из кластера пула, по нему
    эксперт не может проверить, кто именно это делает, а определение требует названного
    игрока.
    """
    keys = set()
    for p in pos.get("players") or []:
        name = p.get("name") if isinstance(p, dict) else p
        key = normalize_org(str(name or ""))
        if len(key) > 1:
            keys.add(key)
    return len(keys)


def _measured(pos: dict) -> bool:
    """Термин измерен в индексе: есть первое упоминание и упоминаний всего > 0.

    Формат карточки интерфейса (`firstYear`, `features.nT`) и сырой формат (`signals`)
    описывают один и тот же замер разными полями — принимаются оба.
    """
    sig = pos.get("signals") or {}
    if sig:
        first = str(sig.get("первое упоминание") or "").strip()
        total = sig.get("упоминаний всего") or 0
        return bool(first) and isinstance(total, (int, float)) and total > 0
    first_year = pos.get("firstYear")
    total = (pos.get("features") or {}).get("nT") or 0
    return bool(first_year) and isinstance(total, (int, float)) and total > 0


def check_position(pos: dict, texts: dict[str, str], cutoff: date,
                   any_text: str = "") -> PositionCheck:
    """Разбор одной позиции. `texts` — сохранённые тексты по адресу, `any_text` — их склейка."""
    reasons: list[str] = []
    sources = _sources_of(pos)
    quotes = [_norm_space(s.get("quote")) for s in sources]
    quotes = [q for q in quotes if len(q) >= MIN_QUOTE]

    checked = 0
    quote_ok = False
    for src, quote in zip([s for s in sources if len(_norm_space(s.get("quote"))) >= MIN_QUOTE],
                          quotes):
        # Сначала текст того документа, на который ссылается карточка: совпадение в чужом
        # документе не подтверждает ссылку. Если адрес не сохранён — ищем по всему пулу,
        # потому что второй хоп приносит цитаты из документов, которых в пуле нет.
        target = texts.get(_url_key(src.get("url")))
        if target is not None:
            checked += 1
            if quote in target:
                quote_ok = True
                break
        elif any_text and quote in any_text:
            checked += 1
            quote_ok = True
            break
    if not quotes:
        reasons.append(R_NO_QUOTE)
    elif not quote_ok:
        reasons.append(R_QUOTE_UNVERIFIED if checked or any_text else R_NO_DOCS)

    players = _players_of(pos)
    if players < 1:
        reasons.append(R_NO_PLAYER)

    dated_ok = False
    for src in sources:
        when = _parse_date(src.get("date"))
        if when and 0 <= _months_between(cutoff, when) <= FRESH_MONTHS:
            dated_ok = True
            break
    measured_ok = _measured(pos)
    if not dated_ok and not measured_ok:
        reasons.append(R_NO_DATE_NO_INDEX)

    term = pos.get("name_en") or pos.get("term") or None
    return PositionCheck(
        id=str(pos.get("id") or pos.get("rank") or ""),
        name=str(pos.get("name") or pos.get("name_ru") or ""),
        term=str(term) if term else None,
        quote_ok=quote_ok, quote_checked=checked, players=players,
        dated_ok=dated_ok, measured_ok=measured_ok, reasons=reasons)


def _url_key(url: object) -> str:
    """Адрес без хвоста запроса: один документ приходит с разными utm-метками."""
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return f"{host}{parsed.path.rstrip('/')}" if host else ""


def _group_mechanisms(rows: list[PositionCheck]) -> None:
    """Склейка позиций об одном механизме: совпал термин ЛИБО нормализованное название.

    Это два разных признака одного и того же, поэтому объединение транзитивно: если A и B
    совпали по термину, а B и C по названию, все три — один механизм.
    """
    parent: dict[int, int] = {i: i for i in range(len(rows))}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)

    by_term: dict[str, int] = {}
    by_name: dict[str, int] = {}
    for i, row in enumerate(rows):
        term_key = _norm_name(row.term or "")
        name_key = _norm_name(row.name)
        if term_key:
            union(i, by_term.setdefault(term_key, i))
        if name_key:
            union(i, by_name.setdefault(name_key, i))
    for i, row in enumerate(rows):
        root = find(i)
        row.key = _norm_name(rows[root].term or "") or _norm_name(rows[root].name) or f"#{root}"


def evaluate(cards: dict | list, texts: Iterable[str] = (), cutoff: date | None = None,
             urls: dict[str, str] | None = None) -> Report:
    """Считает метрику по карточкам. `urls` — сохранённый текст по адресу документа."""
    positions = cards.get("trends") if isinstance(cards, dict) else list(cards)
    positions = positions or []
    cutoff = cutoff or date.today()
    by_url = dict(urls or {})
    joined = " • ".join(dict.fromkeys(list(texts) + list(by_url.values())))

    rows = [check_position(p, by_url, cutoff, joined) for p in positions]
    _group_mechanisms(rows)

    reasons: Counter = Counter()
    for row in rows:
        for reason in row.reasons:
            reasons[reason] += 1
    grounded_keys = {r.key for r in rows if r.grounded}
    return Report(
        positions=len(rows),
        grounded_positions=sum(1 for r in rows if r.grounded),
        grounded_mechanisms=len(grounded_keys),
        unique_mechanisms=len({r.key for r in rows}),
        two_players=sum(1 for r in rows if r.players >= 2),
        reasons=reasons, rows=rows)


def load_texts(run: Path) -> dict[str, str]:
    """Сохранённые тексты прогона: ключ — адрес без хвоста запроса, значение — текст."""
    out: dict[str, str] = {}
    path = run / "documents.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = _norm_space(doc.get("text") or "")
        for url in (doc.get("url"), doc.get("final_url")):
            key = _url_key(url)
            if key and text:
                out[key] = text
    return out


def pool_organizations(run: Path) -> dict[str, list[str]]:
    """Организации из кандидатов пула, доступные по нормализованной цитате.

    Нужно только для диагностической строки: карточка интерфейса кладёт в `players`
    результат второго поиска и теряет `organizations`, извлечённые из документа.
    """
    out: dict[str, list[str]] = {}
    path = run / "candidates.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            cand = json.loads(line)
        except json.JSONDecodeError:
            continue
        orgs = [str(o) for o in (cand.get("organizations") or []) if str(o).strip()]
        if not orgs:
            continue
        for ev in cand.get("evidence") or []:
            key = _norm_space(ev.get("quote"))
            if len(key) >= MIN_QUOTE:
                out.setdefault(key, orgs)
    return out


def cutoff_of(run: Path) -> date | None:
    """Срез прогона из manifest.json: считать свежесть события от сегодня — подмена."""
    path = run / "manifest.json"
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return _parse_date(manifest.get("cutoff"))


def evaluate_run(run: Path, cards_file: Path | None = None) -> Report:
    """Метрика по сохранённому прогону: карточки, тексты и срез берутся из его папки."""
    cards_file = cards_file or (run / "cards.json")
    cards = json.loads(cards_file.read_text(encoding="utf-8"))
    report = evaluate(cards, urls=load_texts(run), cutoff=cutoff_of(run))
    pool = pool_organizations(run)
    if pool:
        positions = cards.get("trends") if isinstance(cards, dict) else list(cards)
        extra = 0
        for row, pos in zip(report.rows, positions or []):
            if row.players >= 1:
                continue
            quotes = [_norm_space(s.get("quote")) for s in _sources_of(pos)]
            if any(pool.get(q) for q in quotes):
                extra += 1
        report.players_in_pool = extra
    return report


def format_report(report: Report, title: str = "") -> str:
    lines = []
    if title:
        lines.append(title)
    lines.append(f"позиций: {report.positions}")
    lines.append(f"обоснованных механизмов: {report.grounded_mechanisms}"
                 f" (позиций {report.grounded_positions})")
    lines.append(f"уникальных механизмов среди позиций: {report.unique_mechanisms}")
    lines.append(f"позиций с 2+ независимыми игроками: {report.two_players}")
    if report.players_in_pool:
        lines.append(f"диагностика: ещё у {report.players_in_pool} позиций организация названа "
                     f"в кандидате пула, но в карточку не попала")
    if report.reasons:
        lines.append("не прошли по причинам:")
        for reason, count in report.reasons.most_common():
            lines.append(f"  {count:3d}  {reason}")
    else:
        lines.append("не прошедших нет")
    lines.append("")
    for row in report.rows:
        mark = "+" if row.grounded else " "
        flags = (f"цитата={'да' if row.quote_ok else 'нет'} игроков={row.players} "
                 f"дата={'да' if row.dated_ok else 'нет'} замер={'да' if row.measured_ok else 'нет'}")
        lines.append(f" {mark} {row.id:>4}  {flags}  {row.name[:58]}")
        if row.reasons:
            lines.append(f"        причины: {'; '.join(row.reasons)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar.metrics", description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="append", default=[], help="папка прогона radar-runs/<id>")
    ap.add_argument("--cards", action="append", default=[], help="отдельный cards.json")
    ap.add_argument("--json", action="store_true", help="машинный вывод")
    args = ap.parse_args(argv)
    if not args.run and not args.cards:
        ap.error("нужен --run или --cards")

    out: dict[str, dict] = {}
    for raw in args.run:
        run = Path(raw)
        if not (run / "cards.json").exists():
            # Молчаливый обход хуже отказа: без карточек метрику считать не из чего.
            print(f"пропущен {run.name}: нет cards.json")
            continue
        report = evaluate_run(run)
        out[run.name] = report.as_dict()
        if not args.json:
            print(format_report(report, f"=== {run.name} ==="), end="\n\n")
    for raw in args.cards:
        cards_file = Path(raw)
        run = cards_file.parent
        report = evaluate(json.loads(cards_file.read_text(encoding="utf-8")),
                          urls=load_texts(run), cutoff=cutoff_of(run))
        out[str(cards_file)] = report.as_dict()
        if not args.json:
            print(format_report(report, f"=== {cards_file} ==="), end="\n\n")
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
