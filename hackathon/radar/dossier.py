"""Сбор дополнительных источников, событий и финансирования для карточки."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlparse

DOSSIER_SYSTEM = """Ты собираешь хронику и сделки по одной технологии.

Дан термин технологии, её механизм и фрагменты найденных документов. Верни только факты,
которые **дословно** есть в показанных фрагментах.

`events` — датированные события: запуск, пилот, выход из стелса, принятие стандарта,
требование регулятора, публикация результата. Для каждого: дата в формате YYYY-MM-DD или
YYYY-MM, организация, что именно произошло (до 12 слов), дословная цитата и номер фрагмента.

`rounds` — раунды финансирования: организация, стадия (pre-seed, seed, Series A и так
далее), сумма с единицей как в тексте, ведущий инвестор если назван, дата, дословная
цитата и номер фрагмента.

Запрещено: выводить дату из номера версии или из года публикации страницы; считать
суммарное финансирование компании отдельным раундом; приписывать событие организации,
которая в цитате не названа; пересказывать своими словами. Если в фрагменте нет даты —
события не создавай.

Верни только JSON: {"events": [{"date": "...", "org": "...", "what": "...",
"quote": "...", "hit": <номер>}], "rounds": [{"org": "...", "stage": "...",
"amount": "...", "lead": "...", "date": "...", "quote": "...", "hit": <номер>}]}."""

_MONEY = re.compile(r"(\$|€|₽|руб|млн|млрд|million|billion|bn|m\b)", re.IGNORECASE)


@dataclass
class Event:
    date: str
    org: str
    what: str
    quote: str
    url: str
    domain: str


@dataclass
class Round:
    org: str
    stage: str
    amount: str
    lead: str
    date: str
    quote: str
    url: str
    domain: str


@dataclass
class Dossier:
    """Хроника и сделки по одной позиции плюс учёт независимости источников."""

    events: list[Event] = field(default_factory=list)
    rounds: list[Round] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    paid_calls: int = 0

    @property
    def domains(self) -> set[str]:
        return {x.domain for x in (*self.events, *self.rounds) if x.domain}

    @property
    def newest(self) -> str:
        """Самая свежая дата в папке: ею проверяется, живая ли это категория."""
        dates = [x.date for x in (*self.events, *self.rounds) if x.date]
        return max(dates) if dates else ""


def domain_of(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def normalize_date(raw: str, cutoff: str) -> str:
    """Дата события: полная или год-месяц. Позже среза не принимается, день не выдумывается."""
    text = str(raw or "").strip()[:10]
    if not re.fullmatch(r"\d{4}(-\d{2}){0,2}", text):
        return ""
    probe = text + {4: "-12-31", 7: "-28"}.get(len(text), "")
    try:
        if date.fromisoformat(probe) > date.fromisoformat(cutoff):
            return ""
    except ValueError:
        return ""
    return text


def collect(term: str, mechanism: str, searcher, llm, cutoff: str,
            hits_per_query: int = 6) -> Dossier:
    """Добирает хронику и раунды по подтверждённому термину технологии."""
    out = Dossier()
    queries = [f'"{term}" raised seed OR "Series A" OR pre-seed funding',
               f'"{term}" launched OR pilot OR "out of stealth" 2026']
    hits = []
    for q in queries:
        out.queries.append(q)
        try:
            found = searcher.search(q, "en", "funding", hits_per_query)
        except Exception:
            continue
        out.paid_calls += 1
        hits.extend(found)
    if not hits:
        return out

    payload = {"термин": term, "механизм": mechanism[:200],
               "фрагменты": [{"index": i, "заголовок": h.title, "текст": h.snippet[:600]}
                             for i, h in enumerate(hits[:10])]}
    try:
        text, _, _ = llm.complete(DOSSIER_SYSTEM, payload)
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (ValueError, KeyError):
        return out

    def grounded(row: dict) -> tuple[str, str] | None:
        """Возвращает (цитата, адрес), если цитата дословно есть в показанном фрагменте."""
        quote = str(row.get("quote") or "").strip()
        idx = row.get("hit")
        if not quote or type(idx) is not int or not (0 <= idx < min(len(hits), 10)):
            return None
        hit = hits[idx]
        if quote.lower() not in (hit.snippet or "").lower():
            return None
        return quote, hit.url

    for row in data.get("events", []):
        when = normalize_date(row.get("date"), cutoff)
        org = str(row.get("org") or "").strip()
        ok = grounded(row)
        if not when or not org or ok is None:
            continue
        quote, url = ok
        if org.casefold() not in quote.casefold():
            continue
        out.events.append(Event(date=when, org=org, what=str(row.get("what") or "")[:90],
                                quote=quote[:300], url=url, domain=domain_of(url)))

    for row in data.get("rounds", []):
        amount = str(row.get("amount") or "").strip()
        org = str(row.get("org") or "").strip()
        ok = grounded(row)
        # Сумма без единицы измерения — не сумма: «16» может быть чем угодно.
        if not org or not amount or not _MONEY.search(amount) or ok is None:
            continue
        quote, url = ok
        if org.casefold() not in quote.casefold() or amount.casefold() not in quote.casefold():
            continue
        out.rounds.append(Round(org=org, stage=str(row.get("stage") or "")[:24],
                                amount=amount[:32], lead=str(row.get("lead") or "")[:60],
                                date=normalize_date(row.get("date"), cutoff),
                                quote=quote[:300], url=url, domain=domain_of(url)))

    out.events.sort(key=lambda e: e.date, reverse=True)
    out.rounds.sort(key=lambda r: r.date, reverse=True)
    return out
