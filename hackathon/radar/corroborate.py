"""Канонический термин и независимое подтверждение.

Две поломки, измеренные 26.09, лечатся здесь.

Первая: окно зрелости искало по нашему русскому пересказу («защита времени выполнения
от»), а индексы англоязычные — 126 кандидатов из 180 получили ноль находок, и это была
ошибка измерения, а не свойство технологии. При этом канонический термин лежит прямо в
цитате: «The Agent Control Standard (ACS) has been donated to the OWASP GenAI Security
Project». Берём термин у авторов, а не у себя.

Вторая: по одному упоминанию нельзя отличить тихий сигнал от неверного запроса. Нужен
независимый источник подтверждения, и он уже есть в пуле: если один и тот же механизм
описан в документах с разных доменов и с разными компаниями — это конвергенция
независимых игроков, то самое, из чего эксперты заказчика собирали свои категории
(в их таблице по три-четыре компании на строку).

Подсчёт игроков по пулу не требует ни одного нового запроса.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Юридические суффиксы и обвязка: «Acme», «ACME» и «Acme Inc.» это один игрок, а не три.
_LEGAL = re.compile(r"\b(inc|llc|ltd|limited|corp|corporation|gmbh|s\.?a\.?|b\.?v\.?|"
                    r"plc|co|company|labs?|technologies|technology|ai|group|holdings?)\b\.?",
                    re.IGNORECASE)


def normalize_org(name: str) -> str:
    """Ключ организации: без регистра, пунктуации и юридических суффиксов.

    Найдено GPT 27.09: подсчёт независимых игроков считал три написания одного имени
    тремя компаниями и завышал главный признак конвергенции.
    """
    s = re.sub(r"[^0-9A-Za-zА-Яа-яёЁ\s-]", " ", (name or "").lower())
    s = _LEGAL.sub(" ", s)
    return " ".join(s.split())

TERM_SYSTEM = """Ты выписываешь канонический англоязычный термин технологии.

Для каждой записи дано наше описание и дословная цитата из источника. Верни термин,
которым **авторы источника** называют эту вещь: так, как он написан в цитате, без
перевода и без наших формулировок.

Термин — это **класс решений**, а не конкретный продукт и не компания. Это то, что
можно набрать в поиске и найти **разных** производителей одного и того же:
«prompt injection defense», «confidential inference», «AI security posture management».

Названия продуктов и компаний брать нельзя, даже если они стоят в цитате. «Firewall for
AI» — продукт Cloudflare, правильный термин «LLM firewall». «Foundry Local» — продукт
Microsoft, правильный термин «local model runtime». «Azure Local» — продукт, правильный
термин «private cloud with disconnected operation». «General Analysis» — компания, а не
технология.

Проверено 27.09.2026: без этого правила фильтр систематически предпочитал продукты
категориям, потому что у торгового имени по определению мало упоминаний, и продукт
выглядел ранним сигналом.

Если в цитате есть только продукт, назови класс, к которому он относится, теми же
английскими словами, какими его называют в отрасли. От одного до четырёх слов.

Если в цитате нет устоявшегося термина, а есть только пересказ — верни null. Не
придумывай термин сам: пустой ответ полезнее выдуманного, потому что по выдуманному
мы посчитаем громкость несуществующей вещи.

Верни только JSON: {"terms": [{"index": <номер>, "term": "<термин или null>"}]}."""


@dataclass
class Cluster:
    """Группа кандидатов об одном механизме, собранная из разных документов."""

    term: str
    candidates: list[dict] = field(default_factory=list)
    organizations: set[str] = field(default_factory=set)
    domains: set[str] = field(default_factory=set)

    @property
    def players(self) -> int:
        """Организации, упомянутые в источниках с разных доменов."""
        return len(self.organizations)

    @property
    def independent_sources(self) -> int:
        return len(self.domains)


def canonical_terms(candidates: list[dict], llm, batch: int = 12) -> dict[int, str | None]:
    """Термин из цитаты для каждого кандидата. Индекс — позиция в переданном списке."""
    out: dict[int, str | None] = {}
    for start in range(0, len(candidates), batch):
        chunk = candidates[start:start + batch]
        payload = {"записи": [
            {"index": start + j,
             "наше_описание": c["name_ru"][:90],
             "наше_английское": c.get("name_orig"),
             "цитаты": [(e.get("quote") or "")[:260] for e in (c.get("evidence") or [])][:3]}
            for j, c in enumerate(chunk)]}
        try:
            text, _, _ = llm.complete(TERM_SYSTEM, payload)
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        except (ValueError, KeyError):
            continue
        for row in data.get("terms", []):
            idx = row.get("index")
            if not isinstance(idx, int) or not (start <= idx < start + len(chunk)):
                continue  # индекс обязан принадлежать текущей пачке, в том числе не -1
            term = row.get("term")
            term = str(term).strip() if term else None
            if not term or not (2 < len(term) <= 60):
                out[idx] = None
                continue
            # Термин не должен совпадать с названием организации из того же кандидата:
            # иначе в окно зрелости уходит торговое имя, а не класс решений.
            orgs = {normalize_org(str(o)) for o in (candidates[idx].get("organizations") or [])}
            if normalize_org(term) in orgs:
                out[idx] = None
                continue
            out[idx] = term
    return out


def domain_of(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def cluster_by_term(candidates: list[dict], terms: dict[int, str | None]) -> list[Cluster]:
    """Собирает кандидатов с одинаковым термином и считает независимость подтверждений."""
    by_term: dict[str, Cluster] = {}
    for i, cand in enumerate(candidates):
        term = terms.get(i)
        if not term:
            continue
        key = term.lower()
        cluster = by_term.setdefault(key, Cluster(term=term))
        cluster.candidates.append(cand)
        for org in cand.get("organizations") or []:
            key = normalize_org(str(org))
            if key and len(key) > 1:
                cluster.organizations.add(key)
        cluster.domains.add(domain_of(cand.get("source_url", "")))
        for ev in cand.get("evidence") or []:
            if ev.get("source_url"):
                cluster.domains.add(domain_of(ev["source_url"]))
    return sorted(by_term.values(), key=lambda c: (-c.players, -c.independent_sources))
