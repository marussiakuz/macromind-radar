"""Окно зрелости: отделяет раннее и растущее от зрелого и громкого.

Критерий заказчика, дословно: технологии отбраковывались «по уже наличию большого
количества инвестиций, либо по уже большому количеству упоминаний и компаний». Их список
построен на цикле хайпа Гартнера, то есть нас интересует точка innovation trigger.

Границы не выдуманы, а выведены из распределения 33 эталонных категорий, измеренных
27.09.2026 (см. `radar/calibrate.py` и `radar-runs/calibration.json`): медиана упоминаний
3, p90 = 423, медианная доля свежих работ 47 %. Заказчик сам предложил так делать:
«отрегулировать весовое распределение в вашей модели». Заявлять успех на этой же выборке
нельзя — она годится для выставления границ, а не для проверки качества.

Источники замера бесплатные и дополняют друг друга: научная база покрывает все области,
поиск сообщества разработчиков точнее по инструментам. Если не ответил ни один, это
состояние «не измерено», и кандидат не отбраковывается: отказ прибора не является
свойством технологии.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

HN_ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"
HN_COUNT = "https://hn.algolia.com/api/v1/search"
OPENALEX = "https://api.openalex.org/works"

# Границы из calibration.json. Держим рядом, чтобы их нельзя было менять «на глаз».
LOUD_MAX = 423          # p90 упоминаний у эталонных категорий
QUIET_MEDIAN = 3        # медиана упоминаний у эталонных категорий
SHARE_MEDIAN = 0.47     # медианная доля работ за последний год


@dataclass
class Signal:
    """Замеры окна зрелости по одному кандидату.

    `status` отделяет качество наблюдения от вывода о технологии: сетевой отказ и
    успешный пустой ответ — разные вещи, и раньше они давали одинаковые (None, 0, 0).
    """

    term: str
    status: str = "ok"                 # ok | error | unmeasured | no_term
    first_seen: str | None = None
    age_months: float | None = None
    total: int = 0
    recent: int = 0
    players: int = 0
    has_evidence: bool = False
    stage: str = "unknown"
    score: float = 0.0
    verdict: str = ""
    notes: list[str] = field(default_factory=list)


def term_of(candidate: dict) -> str:
    """Поисковая строка: авторская фраза целиком.

    Сокращать нельзя: прежний фильтр «общих» слов превращал «AI security posture
    management» в «posture», и замерялось другое понятие.
    """
    raw = (candidate.get("name_orig") or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"\s+", " ", raw).strip(" .,:;—-")
    words = raw.split()
    return " ".join(words[:6]) if len(words) > 6 else raw


class OpenAlexProbe:
    """Научная громкость: знает все области, включая те, которых нет у разработчиков.

    Проверено 27.09.2026 на запросе «Биотехнологии и генетика»: 84 осмысленных кандидата
    были отбракованы все до одного, потому что мерились по сообществу разработчиков.
    OpenAlex на тех же терминах отвечает осмысленно.

    Параметр mailto и «вежливый пул» OpenAlex отменил в феврале 2026; дневной бюджет
    привязан к ключу. Наши прежние 429 — исчерпанный бюджет, а не частота.
    """

    paid = False

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENALEX_API_KEY") or None
        self._client = httpx.Client(
            timeout=httpx.Timeout(20.0),
            headers={"User-Agent": "macromind-radar/0.1 (weak-signal radar prototype)"})
        self._last = 0.0
        self.calls = 0
        self.throttled = 0
        self._cache: dict[str, tuple] = {}

    def _get(self, params: dict) -> dict | None:
        wait = 0.4 - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        if self.api_key:
            params = {**params, "api_key": self.api_key}
        r = self._client.get(OPENALEX, params=params)
        self._last = time.monotonic()
        self.calls += 1
        if r.status_code in (429, 503):
            self.throttled += 1
            return None
        if r.status_code != 200:
            return None
        return r.json()

    def probe(self, term: str) -> tuple[str | None, int, int]:
        if term in self._cache:
            return self._cache[term]
        since = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
        base = f'title_and_abstract.search:"{term}"'
        allt = self._get({"filter": base, "per-page": 1})
        if allt is None:
            return (None, -1, -1)
        total = int(allt.get("meta", {}).get("count", 0))
        rec = self._get({"filter": f"{base},from_publication_date:{since}", "per-page": 1})
        recent = int(rec.get("meta", {}).get("count", 0)) if rec else 0
        first = None
        if total:
            oldest = self._get({"filter": base, "per-page": 1, "sort": "publication_date",
                                "select": "publication_date"})
            if oldest and oldest.get("results"):
                first = (oldest["results"][0].get("publication_date") or "")[:10] or None
        out = (first, total, recent)
        self._cache[term] = out
        return out

    def close(self) -> None:
        self._client.close()


class HackerNewsProbe:
    """Громкость у разработчиков. Бесплатно, без ключа, фразовый поиск обязателен.

    Без `advancedSyntax` и кавычек «Know Your Agent» даёт 1906 упоминаний вместо
    четырёх: многословный запрос матчится как набор частых слов.
    """

    paid = False

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=httpx.Timeout(20.0))
        self._last = 0.0
        self.calls = 0
        self._cache: dict[str, tuple] = {}

    def _get(self, url: str, params: dict) -> dict:
        wait = 0.2 - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        r = self._client.get(url, params=params)
        self._last = time.monotonic()
        self.calls += 1
        r.raise_for_status()
        return r.json()

    def probe(self, term: str) -> tuple[str | None, int, int]:
        if term in self._cache:
            return self._cache[term]
        year_ago = int((datetime.now(timezone.utc) - timedelta(days=365)).timestamp())
        phrase = f'"{term}"'
        try:
            allt = self._get(HN_COUNT, {"query": phrase, "tags": "story", "hitsPerPage": 1,
                                        "advancedSyntax": "true"})
            rec = self._get(HN_COUNT, {"query": phrase, "tags": "story", "hitsPerPage": 1,
                                       "advancedSyntax": "true",
                                       "numericFilters": f"created_at_i>{year_ago}"})
        except httpx.HTTPError:
            return (None, -1, -1)   # -1 = измерения нет, отличать от успешного нуля
        total, recent = int(allt.get("nbHits", 0)), int(rec.get("nbHits", 0))
        first = None
        if total:
            page = max(0, min((total - 1) // 20, 49))
            try:
                old = self._get(HN_ENDPOINT, {"query": phrase, "tags": "story",
                                              "advancedSyntax": "true",
                                              "hitsPerPage": 20, "page": page})
                hits = old.get("hits") or []
                if hits:
                    first = (hits[-1].get("created_at") or "")[:10] or None
            except httpx.HTTPError:
                pass
        out = (first, total, recent)
        self._cache[term] = out
        return out

    def close(self) -> None:
        self._client.close()


class MaturityProbe:
    """Замер по нескольким источникам: берётся первый, который ответил."""

    def __init__(self, probes: list) -> None:
        self.probes = probes
        self.source_of: dict[str, str] = {}

    @property
    def calls(self) -> int:
        return sum(getattr(p, "calls", 0) for p in self.probes)

    def probe(self, term: str) -> tuple[str | None, int, int]:
        for p in self.probes:
            first, total, recent = p.probe(term)
            if total >= 0:
                self.source_of[term] = type(p).__name__
                return (first, total, recent)
        return (None, -1, -1)

    def close(self) -> None:
        for p in self.probes:
            if hasattr(p, "close"):
                p.close()


def score_candidate(cand: dict, probe, players: int = 0) -> Signal:
    """Помещает кандидата в окно зрелости и выставляет балл.

    Баллы простые и объяснимые: заказчик просит показать признак, по которому технология
    признана слабым сигналом, а не вес в модели.
    """
    term = term_of(cand)
    if not term:
        return Signal(term="", status="no_term", verdict="не измерено: нет авторского термина")

    first, total, recent = probe.probe(term)
    sig = Signal(term=term, first_seen=first, total=max(total, 0), recent=max(recent, 0),
                 players=players, stage=str(cand.get("stage") or "unknown"),
                 has_evidence=bool(cand.get("evidence")))
    if first:
        try:
            born = datetime.fromisoformat(first).replace(tzinfo=timezone.utc)
            sig.age_months = round((datetime.now(timezone.utc) - born).days / 30.4, 1)
        except ValueError:
            pass

    if not sig.has_evidence:
        sig.verdict = "отбраковано: нет проверенной цитаты"
        return sig

    if total < 0:
        # Ни один источник не ответил: это состояние прибора, а не свойство технологии.
        sig.status = "unmeasured"
        sig.verdict = "зрелость не измерена"
        score = 0.0
        if players >= 3: score += 2.0; sig.notes.append(f"{players} независимых игроков")
        elif players == 2: score += 1.0; sig.notes.append("два игрока")
        if sig.stage in ("prototype", "pilot"): score += 1.5; sig.notes.append(f"стадия {sig.stage}")
        sig.notes.append("громкость не измерена: источники не ответили по этому термину")
        sig.score = round(score, 2)
        return sig

    if total > LOUD_MAX:
        sig.verdict = "отбраковано: слишком громкое"
        sig.notes.append(f"{total} упоминаний при p90 эталона {LOUD_MAX}")
        return sig
    if sig.stage == "scaled":
        sig.verdict = "отбраковано: масштабировано"
        return sig
    if total == 0:
        # Ноль при успешном ответе — не «технологии нет». По правилу трёх при нуле
        # наблюдений верхняя граница частоты остаётся высокой, но и засчитывать нечего.
        sig.verdict = "нет упоминаний по этому термину"
        sig.notes.append("ноль находок не доказывает отсутствие технологии (правило трёх)")
        return sig

    score = 0.0
    # Доля свежих работ — главная ось: у эталона медиана 47 %, у зрелых технологий вроде
    # постквантовой криптографии она в разы ниже. Абсолютное число разделяет хуже.
    share = recent / total
    if share >= 0.8:
        score += 4.0
        sig.notes.append(f"{recent} из {total} упоминаний за последний год")
    elif share >= SHARE_MEDIAN:
        score += 2.5
        sig.notes.append(f"свежих упоминаний {share:.0%} при медиане эталона {SHARE_MEDIAN:.0%}")
    elif share >= 0.25:
        score += 1.0
        sig.notes.append(f"свежих упоминаний {share:.0%}")
    # Тишина. Прежний нижний порог «не меньше трёх» отсекал половину настоящих сигналов,
    # включая микроплатежи по HTTP 402 и сканеры MCP-серверов.
    if total <= QUIET_MEDIAN:
        score += 2.5
        sig.notes.append(f"очень тихо: {total} упоминаний при медиане эталона {QUIET_MEDIAN}")
    elif total <= 38:
        score += 1.5
        sig.notes.append(f"тихо: {total} упоминаний")
    if players >= 3:
        score += 2.0
        sig.notes.append(f"{players} независимых игроков")
    elif players == 2:
        score += 1.0
        sig.notes.append("два игрока")
    if sig.stage in ("prototype", "pilot"):
        score += 1.5
        sig.notes.append(f"стадия {sig.stage}")
    elif sig.stage == "limited_sales":
        score += 1.0
    # Возраст термина в баллах не участвует: по эталону его медиана 69 месяцев при
    # максимуме 2263, фразовый поиск ловит те же слова в других контекстах. В карточке
    # он остаётся справочно.

    sig.score = round(score, 2)
    sig.verdict = "слабый сигнал" if score >= 5 else "слабый кандидат"
    return sig
