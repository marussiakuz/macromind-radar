"""Провайдер OpenAlex: научные работы и препринты вместо веб-выдачи.

Зачем. Замер 26.09.2026 по 904 позициям Yandex Search показал 3,3 %
первоисточников и 13,4 % SEO-подборок, а пять эталонных категорий области
«Защита ИИ» не имеют продуктов вообще и в продуктовой выдаче появиться не могут.
Проверено живьём в тот же день: четыре пробных запроса по этим категориям вернули
из OpenAlex свежие релевантные препринты, тогда как arXiv в ответ на живой поиск
отдавал 406 (см. `radar/arxiv.py`).

Три свойства, важные для конвейера:

1. Аннотация приходит в ответе, поэтому шаг загрузки и разбора HTML не нужен —
   вместе с ним уходят потери на загрузке, robots.txt и риск SSRF.
2. Вызовы бесплатны, значит прогонов можно делать много и усреднять разброс.
3. `group_by=publication_year` даёт число работ по годам — количественную меру
   усиления сигнала, которой у нас пока нет ни одной.

Ключ не нужен. Если в .env указан OPENALEX_MAILTO, он уходит в User-Agent и запрос
попадает в вежливый пул с более стабильными задержками; OPENALEX_API_KEY включает
платный пул. Ни то ни другое не обязательно.
"""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

from .config import DocumentSnapshot, SearchHit
from .fetch import normalize_text

ENDPOINT = "https://api.openalex.org/works"
MIN_INTERVAL_S = 0.2   # OpenAlex допускает 10 запросов в секунду; берём с запасом
BACKOFF_S = (2.0, 10.0, 30.0)
SELECT = ("id,doi,title,publication_date,abstract_inverted_index,primary_location,"
          "authorships,cited_by_count,type")

# Слова, которые есть в каждой второй аннотации: сужают запрос хуже, чем термины.
_STOP = {"the", "a", "an", "of", "for", "and", "in", "on", "to", "with", "as", "at", "by",
         "based", "using", "new", "ai", "2026"}


def search_terms(phrase: str, limit: int = 4) -> str:
    """Поисковая строка из значимых слов подсегмента, в исходном порядке.

    OpenAlex ищет по названию и аннотации и сам считает релевантность, поэтому
    фразовые кавычки не нужны: достаточно убрать шум вроде «AI» и «2026».
    """
    words = [w.strip(".,()[]«»\"'").lower() for w in phrase.split()]
    words = [w for w in words if len(w) > 2 and w not in _STOP]
    return " ".join(words[:limit]) or phrase.strip()


def reconstruct_abstract(index: dict | None) -> str:
    """Собирает аннотацию из обратного индекса {слово: [позиции]}.

    OpenAlex отдаёт аннотацию именно так по лицензионным причинам. Порядок слов
    восстанавливается однозначно, знаки препинания сохранены внутри токенов.
    """
    if not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, places in index.items():
        for place in places or []:
            positions.append((int(place), word))
    positions.sort()
    return normalize_text(" ".join(word for _, word in positions))


def work_url(work: dict) -> str:
    """Ссылка, которую можно открыть и проверить: страница издателя, DOI или OpenAlex."""
    landing = ((work.get("primary_location") or {}).get("landing_page_url") or "").strip()
    if landing:
        return landing
    doi = (work.get("doi") or "").strip()
    return doi or (work.get("id") or "").strip()


def parse_works(payload: dict, query: str, lens: str, count: int,
                seen_titles: set[str] | None = None) -> tuple[list[SearchHit], dict[str, DocumentSnapshot]]:
    """Ответ OpenAlex → попадания и готовые снимки текста.

    Дедупликация по названию обязательна: Zenodo отдаёт одну и ту же работу
    дважды, это видно в трёх из четырёх пробных запросов 26.09.2026.
    """
    seen = seen_titles if seen_titles is not None else set()
    hits: list[SearchHit] = []
    snapshots: dict[str, DocumentSnapshot] = {}
    for pos, work in enumerate(payload.get("results") or [], start=1):
        title = normalize_text(work.get("title") or "")
        abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
        url = work_url(work)
        key = " ".join(sorted(title.lower().split()))
        if not title or not url or key in seen or len(abstract) < 200:
            continue
        seen.add(key)
        source = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or "?"
        authors = [normalize_text((a.get("author") or {}).get("display_name") or "")
                   for a in (work.get("authorships") or [])][:6]
        published = (work.get("publication_date") or "")[:10] or None
        text = normalize_text("\n".join([
            title,
            abstract,
            f"Научная работа, дата публикации {published or 'неизвестна'}, тип {work.get('type') or '?'}.",
            f"Источник: {source}. Цитирований на момент выгрузки: {work.get('cited_by_count', 0)}.",
            f"Авторы: {', '.join(a for a in authors if a)}." if authors else "",
        ]))
        if len(text) < 200:
            continue
        snapshots[url] = DocumentSnapshot(
            url=url, final_url=url, title=title, text=text,
            text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            lang="en", published_at=published, parser_version="openalex/0.1",
        )
        hits.append(SearchHit(url=url, title=title, snippet=abstract[:600], position=pos,
                              query=query, lang="en", lens=lens))
        if len(hits) >= count:
            break
    return hits, snapshots


class OpenAlexSearch:
    """Выборка работ по подсегменту. Вызовы бесплатны и в смету не попадают."""

    paid = False

    def __init__(self, months: int = 18, mailto: str | None = None, api_key: str | None = None):
        self.months = months
        self.mailto = mailto or os.environ.get("OPENALEX_MAILTO") or None
        self.api_key = api_key or os.environ.get("OPENALEX_API_KEY") or None
        self.calls = 0
        self.throttled = 0
        self.errors: list[str] = []
        self.snapshots: dict[str, DocumentSnapshot] = {}
        self._seen_titles: set[str] = set()
        self._last_call = 0.0
        ua = "macromind-radar/0.1 (weak-signal radar prototype"
        ua += f"; mailto:{self.mailto})" if self.mailto else ")"
        self._client = httpx.Client(timeout=httpx.Timeout(30.0), headers={"User-Agent": ua})

    def _since(self, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        return (now - timedelta(days=30 * self.months)).strftime("%Y-%m-%d")

    def _get(self, params: dict) -> dict:
        if self.api_key:
            params = {**params, "api_key": self.api_key}
        for pause in (0.0,) + BACKOFF_S:
            if pause:
                time.sleep(pause)
            wait = MIN_INTERVAL_S - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            r = self._client.get(ENDPOINT, params=params)
            self._last_call = time.monotonic()
            self.calls += 1
            if r.status_code in (429, 503):
                self.throttled += 1
                continue
            r.raise_for_status()
            return r.json()
        raise httpx.HTTPError(f"OpenAlex отвечает {r.status_code} после {len(BACKOFF_S)} выдержек")

    def _query(self, search_value: str, lens: str, count: int, label: str) -> list[SearchHit]:
        params = {
            "filter": f"title_and_abstract.search:{search_value},"
                      f"from_publication_date:{self._since()}",
            "per-page": max(count * 2, count),  # запас на дубликаты и работы без аннотации
            "select": SELECT,
        }
        try:
            payload = self._get(params)
        except httpx.HTTPError as exc:
            self.errors.append(f"{label[:40]}: {exc}")
            return []
        hits, snapshots = parse_works(payload, label, lens, count, self._seen_titles)
        self.snapshots.update(snapshots)
        return hits

    def search(self, query: str, lang: str, lens: str, count: int) -> list[SearchHit]:
        """Сначала точная фраза, потом отдельные термины на добор.

        Проверено 26.09.2026 на подсегментах «Защиты ИИ». Сортировка по дате даёт
        мусор: по запросу про идентификацию агентов приходили насекомые на траве и
        дорожное движение в Нигерии, потому что поиск OpenAlex понимает набор слов
        широко, а сортировка по дате выбрасывает релевантность. Сортировку не
        указываем вовсе — тогда работает встроенная по relevance_score. Фраза в
        кавычках дала ответ NIST NCCoE об идентификации агентов и протокол AIP для
        MCP, то есть ровно нужный уровень; термины без кавычек добирают полноту.
        """
        terms = search_terms(query, limit=4)
        words = terms.split()
        hits: list[SearchHit] = []
        if len(words) >= 2:
            hits += self._query(f'"{" ".join(words[:3])}"', lens, count, query)
        if len(hits) < count:
            hits += self._query(terms, lens, count - len(hits), query)
        return hits[:count]

    def sample_titles(self, query: str, count: int = 50) -> list[str]:
        """Названия свежих работ по широкому запросу — словарь для планировщика.

        Снимки не создаются: это не источник кандидатов, а материал для заземления.
        Нужно, чтобы планировщик видел научные формулировки, а не только рыночные:
        по замеру 26.09.2026 подсегменты из веб-выдачи давали словарь вида «AI
        posture management» и не содержали ни одной темы, которая живёт только в
        исследованиях.
        """
        try:
            payload = self._get({
                "filter": f"title_and_abstract.search:{search_terms(query, 3)},"
                          f"from_publication_date:{self._since()}",
                "per-page": min(count, 100),
                "select": "title,publication_date",
            })
        except httpx.HTTPError as exc:
            self.errors.append(f"sample {query[:30]}: {exc}")
            return []
        out = []
        for work in payload.get("results") or []:
            title = normalize_text(work.get("title") or "")
            if len(title) > 15:
                out.append(title)
        return out

    def growth(self, query: str, years: int = 6) -> dict[int, int]:
        """Число работ по годам: основа для оценки усиления сигнала.

        Данные текущего года всегда неполные, это учитывать при сравнении.
        """
        since = (datetime.now(timezone.utc) - timedelta(days=365 * years)).strftime("%Y-%m-%d")
        try:
            payload = self._get({
                "filter": f'title_and_abstract.search:"{search_terms(query, 3)}",'
                          f"from_publication_date:{since}",
                "group_by": "publication_year",
            })
        except httpx.HTTPError as exc:
            self.errors.append(f"growth {query[:30]}: {exc}")
            return {}
        out: dict[int, int] = {}
        for row in payload.get("group_by") or []:
            try:
                out[int(row["key"])] = int(row["count"])
            except (KeyError, ValueError, TypeError):
                continue
        return dict(sorted(out.items()))

    def close(self) -> None:
        self._client.close()
