"""Адресный поиск фактов применения для проверки зрелости.

Используются дословные фрагменты поисковых сниппетов. Факты, доступные только
в полном тексте, могут быть пропущены."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

# Слова, вокруг которых в тексте лежат факты эксплуатации. Окно берётся дословно: аудит
# всё равно проверяет фрагмент по цитате, и выдуманное окно не пройдёт.
USAGE_MARKER = re.compile(
    r"(in production|production use|deployed|deployment|customers|clients|"
    r"organizations|since 20\d\d|migrated|adopted|operates|running|"
    r"внедрил|эксплуатац|в продакшен|заказчик|клиент|организаци|с 20\d\d года)",
    re.IGNORECASE)
WINDOW_BEFORE, WINDOW_AFTER, MAX_WINDOWS = 350, 650, 3

# Хвосты запроса. Английский — если у кандидата есть англоязычный термин: факты эксплуатации
# формулируются на языке источника, и русский хвост к английскому термину даёт мусор.
TAILS_EN = ("adoption survey production organizations report",
            "production deployments customers case study since",
            "vendors commercially deployed customer engineering")
TAILS_RU = ("исследование распространения промышленное использование организации",
            "промышленное применение заказчики внедрение",
            "поставщики эксплуатация опыт использования технология")


def _owner(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def windows(text: str, limit: int = MAX_WINDOWS) -> list[str]:
    """Дословные окна вокруг слов об эксплуатации. Не пересказ и не извлечённые факты."""
    out: list[str] = []
    used: list[tuple[int, int]] = []
    for match in USAGE_MARKER.finditer(text or ""):
        start = max(0, match.start() - WINDOW_BEFORE)
        end = min(len(text), match.end() + WINDOW_AFTER)
        if any(start < b and a < end for a, b in used):      # окна не должны перекрываться
            continue
        used.append((start, end))
        out.append(text[start:end].strip())
        if len(out) >= limit:
            break
    return out


def gather(candidate: dict, searcher, per_query: int = 6, keep: int = 2,
           fetcher=None) -> list[dict]:
    """Дополнительные дословные доказательства применения. Возвращает записи для пакета.

    С `fetcher` берём окна из полного текста, без него — только сниппеты. Разница
    измерена 29.09.2026: на сниппетах фильтр зрелости не исключил даже Kubernetes, MQTT и
    TLS 1.3, потому что составной маршрут требует названного покупателя, даты и года
    эксплуатации, а в сниппете этого не бывает.
    """
    term = (candidate.get("name_orig") or "").strip()
    base = (term or candidate.get("name_ru", "")).strip()[:160]
    if not base:
        return []
    tails = TAILS_EN if term else TAILS_RU
    lang = "en" if term else "ru"
    out: list[dict] = []
    selected = []
    seen_owner: dict[str, int] = {}
    for tail in tails:
        try:
            # Long generated category names rarely occur verbatim on a page.
            phrase = f'"{base}"' if len(base.split()) <= 4 else ' '.join(base.split()[:10])
            hits = searcher.search(f'{phrase} {tail}', lang, "operator_evidence", per_query)
        except Exception:
            continue
        from .hoststats import layer_of, host_of
        hits = sorted(hits, key=lambda h: {'первоисточник': 0, 'прочее': 1,
                                          'СМИ': 2, 'SEO-подборки': 3,
                                          'видео/соцсети': 4}.get(layer_of(host_of(h.url)), 2))
        taken = 0
        for hit in hits:
            if taken >= keep:
                break
            owner = _owner(hit.url)
            # Не больше двух фрагментов с одного владельца: перепечатка одного сообщения
            # двумя страницами одного сайта не добавляет независимости.
            if seen_owner.get(owner, 0) >= 2:
                continue
            snippet = (hit.snippet or "").strip()
            if len(snippet) < 40:
                continue
            seen_owner[owner] = seen_owner.get(owner, 0) + 1
            taken += 1
            selected.append(hit)
    def document_windows(hit):
        full = []
        if fetcher is not None:
            try:
                from .fetch import parse_document
                result, body = fetcher.fetch(hit.url)
                if result.status == 'ok' and body is not None:
                    doc = parse_document(body, hit.url, result.final_url or hit.url, result.content_type)
                    if doc is not None: full = windows(doc.text)
            except Exception:
                pass
        return [{'quote': text[:900], 'url': hit.url, 'owner': _owner(hit.url),
                 'kind': 'факт применения' if full else 'факт применения (сниппет)',
                 'title': hit.title[:160]} for text in (full or [hit.snippet])]
    # Fetcher retains per-origin locks, robots and SSRF checks across these workers.
    with ThreadPoolExecutor(max_workers=4) as workers:
        for spans in workers.map(document_windows, selected): out.extend(spans)
    return out
