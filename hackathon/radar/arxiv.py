"""Поиск препринтов через API arXiv и преобразование результатов в документы."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from lxml import etree

from .config import DocumentSnapshot, SearchHit
from .fetch import normalize_text

ENDPOINT = "https://export.arxiv.org/api/query"
USER_AGENT = "macromind-radar/0.1 (weak-signal radar prototype; contact via repository)"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
MIN_INTERVAL_S = 3.0   # требование arXiv к частоте запросов
BACKOFF_S = (10.0, 30.0, 60.0)  # проверено 26.09.2026: на пачку запросов arXiv
# отвечает 406, затем 429, и синтаксис запроса тут ни при чём — это троттлинг.
# Тот же запрос после выдержки проходит, поэтому ошибку нельзя считать «нет статей».

# Стоп-слова запроса: в arXiv они ничего не сужают, но ломают фразовый поиск.
_QUERY_STOP = {"the", "a", "an", "of", "for", "and", "in", "on", "to", "with", "as", "at", "by",
               "based", "using", "new", "ai", "2026"}

# Слова, которые есть в каждой второй аннотации: берём их только если больше нечего
# взять. Иначе запрос про дифференциальную приватность вырождается в «generation».
_GENERIC = {"models", "model", "systems", "system", "management", "generation", "data",
            "learning", "framework", "frameworks", "approach", "method", "methods",
            "security", "secure", "safety", "control", "controls", "detection",
            "protection", "monitoring", "analysis", "evaluation", "large", "language"}


def significant_terms(phrase: str, limit: int = 3) -> list[str]:
    """Самые различающие слова подсегмента, в исходном порядке.

    Длинные слова информативнее: в «AI agent identity management» полезны
    «identity» и «management», а «AI» встречается в каждой второй статье.
    """
    words = [w.strip(".,()[]«»\"'").lower() for w in phrase.split()]
    words = [w for w in words if len(w) > 2 and w not in _QUERY_STOP]
    if not words:
        return [phrase.strip()]
    chosen = sorted(words, key=lambda w: (w not in _GENERIC, len(w)), reverse=True)[:limit]
    return [w for w in words if w in chosen]


def _window(months: int, now: datetime | None) -> str:
    """Окно по дате подачи: слабый сигнал ищем среди свежего, но 12 месяцев мало —
    препринт обычно старше первого продукта примерно на год."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=30 * months)).strftime("%Y%m%d0000")
    return f"submittedDate:[{since} TO {now.strftime('%Y%m%d2359')}]"


def build_search_query(phrase: str, months: int = 18, now: datetime | None = None,
                       terms: int = 3) -> str:
    """Конъюнкция значимых слов по аннотации и названию плюс окно по дате.

    Фразовый поиск по всему подсегменту не годится: «AI agent identity management»
    как точная фраза в arXiv почти не встречается, а по отдельным словам статьи
    находятся. Поэтому запрос строится из слов, а точность добирается тем, что слов
    несколько и все обязательны.
    """
    words = significant_terms(phrase, terms)
    body = " AND ".join(f'(abs:"{w}" OR ti:"{w}")' for w in words)
    return f"({body}) AND {_window(months, now)}"


def build_fallback_query(phrase: str, months: int = 18, now: datetime | None = None) -> str:
    """Запасной запрос: два самых длинных слова вместо трёх."""
    return build_search_query(phrase, months, now, terms=2)


def parse_atom(xml: bytes, query: str, lens: str, count: int) -> tuple[list[SearchHit], dict[str, DocumentSnapshot]]:
    """Atom-ответ → попадания и готовые снимки текста из аннотаций."""
    root = etree.fromstring(xml)
    hits: list[SearchHit] = []
    snapshots: dict[str, DocumentSnapshot] = {}
    for pos, entry in enumerate(root.findall("a:entry", NS), start=1):
        url_node = entry.find("a:id", NS)
        title_node = entry.find("a:title", NS)
        summary_node = entry.find("a:summary", NS)
        if url_node is None or title_node is None or summary_node is None:
            continue
        url = (url_node.text or "").strip()
        title = normalize_text(title_node.text or "")
        summary = normalize_text(summary_node.text or "")
        if not url or len(summary) < 120:
            continue
        published = (entry.findtext("a:published", default="", namespaces=NS) or "")[:10] or None
        cats = [c.get("term", "") for c in entry.findall("a:category", NS) if c.get("term")]
        authors = [normalize_text(a.findtext("a:name", default="", namespaces=NS))
                   for a in entry.findall("a:author", NS)][:6]
        # Текст снимка: заголовок, аннотация и метаданные. Цитаты проверяются как
        # подстроки этого текста, поэтому ничего не переводим и не сокращаем.
        text = normalize_text("\n".join([
            title,
            summary,
            f"Препринт arXiv, дата подачи {published or 'неизвестна'}.",
            f"Разделы arXiv: {', '.join(cats)}." if cats else "",
            f"Авторы: {', '.join(authors)}." if authors else "",
        ]))
        if len(text) < 200:
            continue
        snapshots[url] = DocumentSnapshot(
            url=url, final_url=url, title=title, text=text,
            text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            lang="en", published_at=published, parser_version="arxiv/0.1",
        )
        hits.append(SearchHit(url=url, title=title, snippet=summary[:600], position=pos,
                              query=query, lang="en", lens=lens))
        if len(hits) >= count:
            break
    return hits, snapshots


class ArxivSearch:
    """Выборка препринтов. Вызовы бесплатны, поэтому в смету не попадают."""

    paid = False

    def __init__(self, cache_dir: Path | None = None, months: int = 18):
        self.cache_dir = cache_dir
        self.months = months
        self.calls = 0
        self.throttled = 0
        self.errors: list[str] = []
        self.snapshots: dict[str, DocumentSnapshot] = {}
        self._last_call = 0.0
        self._client = httpx.Client(timeout=httpx.Timeout(30.0),
                                    headers={"User-Agent": USER_AGENT})

    def _get(self, search_query: str, count: int) -> bytes:
        """Один запрос с соблюдением интервала и выдержкой при троттлинге."""
        params = {"search_query": search_query, "start": 0, "max_results": count,
                  "sortBy": "submittedDate", "sortOrder": "descending"}
        for attempt, pause in enumerate((0.0,) + BACKOFF_S):
            if pause:
                time.sleep(pause)
            wait = MIN_INTERVAL_S - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            r = self._client.get(ENDPOINT, params=params)
            self._last_call = time.monotonic()
            self.calls += 1
            if r.status_code in (406, 429, 503):
                self.throttled += 1
                continue
            r.raise_for_status()
            return r.content
        raise httpx.HTTPError(f"arXiv отвечает {r.status_code} после {len(BACKOFF_S)} выдержек")

    def search(self, query: str, lang: str, lens: str, count: int) -> list[SearchHit]:
        """Фразовый запрос, при нуле результатов — конъюнкция слов."""
        for make in (build_search_query, build_fallback_query):
            try:
                xml = self._get(make(query, self.months), count)
            except httpx.HTTPError as exc:
                # Пустой список и отказ сети — разные вещи; отказ идёт в отчёт прогона.
                self.errors.append(f"{query[:40]}: {exc}")
                return []
            if self.cache_dir:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                safe = "".join(ch if ch.isalnum() else "_" for ch in query)[:60]
                (self.cache_dir / f"arxiv_{safe}.xml").write_bytes(xml)
            hits, snapshots = parse_atom(xml, query, lens, count)
            if hits:
                self.snapshots.update(snapshots)
                return hits
        return []

    def close(self) -> None:
        self._client.close()
