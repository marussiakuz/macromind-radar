"""Второй хоп: кто на самом деле делает эту технологию.

Зачем. Эксперт, голосуя по позиции, спрашивает: кто это делает, с какого момента и
почему это ещё не мейнстрим. Наша карточка отвечала одним механизмом и одной цитатой.
В таблице заказчика к каждой строке приложены три-четыре компании и хроника событий —
именно это они считают доказательством слабого сигнала.

Конвейер находит технологию в документе и на этом останавливается. Здесь начинается
второй проход: по подтверждённому термину ищем ещё документы и вытаскиваем из них
организации, у которых связь с механизмом подтверждена дословной цитатой.

Дисциплина та же, что везде: имя, названное в обзорной статье, не доказывает
реализацию; два домена с одним пресс-релизом — одно событие, а не два независимых
игрока; организации без цитаты в карточку не попадают.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlparse

PLAYERS_SYSTEM = """Ты выписываешь организации, которые реализуют названный механизм.

Дан механизм технологии и фрагменты найденных документов. Для каждой организации,
которая **делает** это, верни запись. Организация, просто упомянутая в обзоре рядом с
темой, не считается: нужна связь именно с этим механизмом.

Роли: developer — разрабатывает или продаёт; deployer — внедрил у себя; researcher —
исследовательская группа; funder — инвестор; standard — орган стандартизации.
Инвестор и автор обзора реализацией не являются.

Для каждой записи обязательна дословная цитата из показанного фрагмента, где названы
и организация, и то, что она делает. Нет такой цитаты — организацию не включай.

Верни только JSON: {"players": [{"name": "...", "role": "...", "what": "<до 12 слов>",
"quote": "<дословно из фрагмента>", "hit": <номер фрагмента>}]}."""


@dataclass
class Player:
    name: str
    role: str
    what: str
    quote: str
    url: str
    domain: str


@dataclass
class PlayerEvidence:
    """Игроки по одной категории и оценка их независимости."""

    players: list[Player] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    paid_calls: int = 0

    @property
    def independent(self) -> int:
        """Число организаций-реализаторов; инвесторы и обзорщики не в счёт.

        Организация считается один раз независимо от числа страниц: два домена с
        перепечаткой одного сообщения — одно событие.
        """
        seen = {p.name.strip().lower() for p in self.players
                if p.role in ("developer", "deployer", "researcher")}
        return len(seen)

    @property
    def domains(self) -> int:
        return len({p.domain for p in self.players if p.domain})


def domain_of(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def find_players(term: str, mechanism: str, searcher, llm, known: list[str] | None = None,
                 hits_per_query: int = 6) -> PlayerEvidence:
    """Ищет реализаторов механизма и подтверждает каждого цитатой."""
    out = PlayerEvidence()
    known_lower = {k.strip().lower() for k in (known or [])}
    queries = [f'"{term}" startup OR company OR pilot 2026',
               f'"{term}" deployment OR launched OR partnership']
    hits = []
    for q in queries:
        out.queries.append(q)
        for lens in ("research", "product"):
            found = searcher.search(q, "en", lens, hits_per_query)
            if lens == "product":
                out.paid_calls += 1
            hits.extend(found)
        if len(hits) >= hits_per_query * 2:
            break
    if not hits:
        return out

    payload = {"механизм": mechanism[:200], "термин": term,
               "фрагменты": [{"index": i, "заголовок": h.title, "текст": h.snippet[:600]}
                             for i, h in enumerate(hits[:10])]}
    try:
        text, _, _ = llm.complete(PLAYERS_SYSTEM, payload)
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (ValueError, KeyError):
        return out

    for row in data.get("players", []):
        name = str(row.get("name") or "").strip()
        quote = str(row.get("quote") or "").strip()
        idx = row.get("hit")
        if not name or not quote or type(idx) is not int or not (0 <= idx < min(len(hits), 10)):
            continue
        hit = hits[idx]
        # Цитата обязана дословно находиться в показанном фрагменте: без этого модель
        # свободно пересказывает и приписывает компаниям то, чего в тексте нет.
        if quote.lower() not in (hit.snippet or "").lower():
            continue
        # A real quote about another organization cannot establish this one's role.
        if name.casefold() not in quote.casefold():
            continue
        role = row.get('role')
        if role not in {'developer', 'deployer', 'researcher', 'funder', 'standard'}:
            continue
        if name.lower() in known_lower:
            continue
        out.players.append(Player(name=name, role=role,
                                  what=str(row.get("what") or "")[:80], quote=quote,
                                  url=hit.url, domain=domain_of(hit.url)))
    return out
