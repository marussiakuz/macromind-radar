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

# Кандидат без канонического термина больше не выбрасывается, а оценивается по признакам,
# которые не требуют замера. Измерено 27.09.2026 на сохранённых прогонах: в пуле «Финтеха»
# (96 кандидатов) пригодный английский термин есть у 37, и среди десяти кандидатов, которые
# я вручную сопоставил со строками эталона, термин был у одного, а среди остальных 86 — у
# 36. То есть доля 10 % против 42 %: фильтр термина систематически отбирал ПРОТИВ эталона.
# Причина видна в материале: короткое английское имя категории дают вендорские подборки
# («AI strategy creation», «Ongoing AML Monitoring»), а фронтирный материал приходит либо
# длинной описательной фразой, либо цитатой на русском. Поэтому «нет термина» переводится
# в «не измерено», а не в «отбраковано».
SCORE_WITHOUT_TERM = True

# Органы стандартизации, консорциумы и регуляторы. Название исправлено 28.09.2026:
# функция звалась `is_standards_body`, но половина списка — регуляторы (Банк России, ФСТЭК,
# EBA, ESMA, FSB), и карточка получала пометку «назван орган стандартизации» там, где в
# источнике стоял надзорный орган. Эксперт банка заметил бы это первым, а признак от этого
# не слабее: и стандарт, и требование регулятора появляются раньше рынка — это и есть
# innovation trigger у Гартнера, на чьём цикле построена таблица заказчика. Измерено 27.09.2026 по ручной разметке двух пулов: признак
# встречается у 30 % эталонных кандидатов «Финтеха» против 3 % у остальных (lift 8,6) и
# у 10 % против 2 % на «Защите ИИ» (lift 6,5). Положительных примеров всего 10 и 20,
# поэтому величина lift неточна, но знак совпал в двух областях независимо.
RULE_SETTERS = re.compile(
    r"\b(nist|ietf|w3c|iso|iec|ieee|oasis|owasp|fido|emvco|bis|swift|linux foundation|"
    r"cen|etsi|itu|eba|esma|fsb|cpmi|iosco|cloud security alliance|mitre|oecd|"
    r"european commission|nvd|банк россии|цб рф|минцифры|фстэк|росстандарт)\b",
    re.IGNORECASE)


@dataclass
class DomainBaseline:
    """Скорость обновления области, относительно которой оценивается кандидат.

    Измерено 27.09.2026: доля работ за последний год сильно зависит от области —
    защита ИИ 53,7 %, финтех 30,5 %, 3D-печать 15,7 %, биотехнологии 14,1 %,
    робототехника 11,4 %. Разброс пятикратный. Единый порог 47 % — это фактически
    базовый уровень безопасности ИИ, и в робототехнике его не преодолел бы никто:
    мы выдали бы ноль сигналов и решили, что там нет фронтира.

    Поэтому рост кандидата считается относительно его области, а не в абсолюте.
    Кандидат с долей 34 % в биотехе растёт в 2,4 раза быстрее своей области — это
    сильный сигнал, а по абсолютному порогу он не проходил вовсе.
    """

    share: float = SHARE_MEDIAN     # доля свежих работ в области
    total: int = 0                  # объём области, для относительной громкости
    terms: list[str] = field(default_factory=list)

    @property
    def known(self) -> bool:
        return self.total > 0


FIELD_SYSTEM = """Назови область науки и техники, к которой относится запрос.

Верни только JSON: {"terms": ["...", "..."]} — два-три **широких** английских названия
области, какими её называют в научных статьях: «biotechnology», «genome editing»,
«additive manufacturing», «machine learning security».

Это должны быть названия области целиком, а не конкретные технологии и не формулировки
проблем. По ним измеряется, с какой скоростью обновляется отрасль, поэтому слишком узкий
термин даст бессмысленную базу."""


def field_terms(query: str, llm) -> list[str]:
    """Широкие названия области для замера её скорости обновления.

    Проверено 27.09.2026: попытка взять их из плана поиска дала обрывок служебной
    пометки «50 работ)», и база области получилась «5 работ». Спрашиваем явно.
    """
    import json as _json
    try:
        text, _, _ = llm.complete(FIELD_SYSTEM, {"запрос": query})
        data = _json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (ValueError, KeyError):
        return [query]
    out = [str(t).strip() for t in (data.get("terms") or []) if str(t).strip()]
    out = [t for t in out if 3 < len(t) <= 60 and len(t.split()) <= 4]
    return out[:3] or [query]


def measure_baseline(terms: list[str], probe) -> DomainBaseline:
    """Базовый уровень области по двум-трём широким терминам. Два-три вызова, бесплатно."""
    shares, totals, used = [], [], []
    for term in terms[:3]:
        if not term:
            continue
        _, total, recent = probe.probe(term)
        if total > 0:
            shares.append(recent / total)
            totals.append(total)
            used.append(term)
    if not shares:
        return DomainBaseline()
    return DomainBaseline(share=sum(shares) / len(shares),
                          total=max(totals), terms=used)


@dataclass
class Signal:
    """Замеры окна зрелости по одному кандидату.

    `status` отделяет качество наблюдения от вывода о технологии: сетевой отказ и
    успешный пустой ответ — разные вещи, и раньше они давали одинаковые (None, 0, 0).
    """

    term: str
    status: str = "ok"                 # ok | error | unmeasured | no_term
    aged_out: bool = False             # термину больше четырёх лет: «зарождающимся» не бывает
    too_loud: bool = False             # упоминаний больше порога области
    tier: str = "review"               # signal | review | rejected
    """Куда кандидат попадает в выдаче.

    Разбор 27.09.2026 на биотехе: из 82 отказов необоснованными оказались около
    тридцати. «Вне области» отбрасывало клинические испытания, хотя генные терапии
    через них и проходят; «слишком громкое» срабатывало на слишком общем извлечённом
    термине, а не на зрелости технологии. Поэтому жёсткий отказ остаётся только там,
    где проверять нечего, а спорное уходит к человеку с пометкой: ошибка фильтра не
    должна быть безвозвратной.
    """
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
    no_players: bool = False
    """В источнике не названо ни одной организации. Такая позиция не может стать
    уверенным сигналом: эксперту нечего проверить, кто это делает."""


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
        if rec is None:
            # Сбой запроса за год — это не «работ за год нет». Раньше сюда подставлялся
            # ноль, и технология выглядела затухающей из-за отказа сети.
            return (None, total, -1)
        recent = int(rec.get("meta", {}).get("count", 0))
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
    """Замер по нескольким источникам: спрашиваются все, выбирается информативный.

    Раньше возвращался первый источник с `total >= 0`, и успешный ноль научной базы
    останавливал цепочку: сообщество разработчиков не спрашивалось вообще. На
    биотехнологиях это отбраковало 84 кандидата из 84. Корпуса разные, складывать их
    числа нельзя, поэтому берётся тот, который что-то нашёл.
    """

    def __init__(self, probes: list) -> None:
        self.probes = probes
        self.source_of: dict[str, str] = {}
        self.per_source: dict[str, dict] = {}

    @property
    def calls(self) -> int:
        return sum(getattr(p, "calls", 0) for p in self.probes)

    def probe(self, term: str) -> tuple[str | None, int, int]:
        results = []
        for p in self.probes:
            first, total, recent = p.probe(term)
            results.append((type(p).__name__, first, total, recent))
        self.per_source[term] = {name: {"total": t, "recent": r, "first": f}
                                 for name, f, t, r in results}

        ok = [(n, f, t, r) for n, f, t, r in results if t >= 0 and r >= 0]
        if not ok:
            # Есть ли хотя бы частичный ответ: общее число известно, свежее — нет.
            partial = [(n, f, t, r) for n, f, t, r in results if t >= 0]
            if partial:
                name, first, total, _ = max(partial, key=lambda x: x[2])
                self.source_of[term] = f"{name} (свежее не измерено)"
                return (first, total, -1)
            return (None, -1, -1)

        # Из ответивших берём тот, где вообще что-то нашлось: ноль в одном корпусе не
        # означает отсутствия технологии, он означает, что её там не обсуждают.
        found = [x for x in ok if x[2] > 0]
        name, first, total, recent = (max(found, key=lambda x: x[2]) if found else ok[0])
        self.source_of[term] = name
        return (first, total, recent)

    def close(self) -> None:
        for p in self.probes:
            if hasattr(p, "close"):
                p.close()


def evidence_score(cand: dict, players: int, sig: "Signal") -> float:
    """Признаки, которые не требуют замера громкости: игроки, стандарт, датированное событие.

    Зачем отдельно. До этой правки у ветки «упоминаний не найдено» был фиксированный балл
    1.0, и в выдаче «Финтеха» одиннадцать позиций из пятнадцати имели ровно 1.00 — порядок
    внутри них определялся положением в файле, то есть ничем. Здесь появляется то, чем
    заказчик сам описывает строку своей таблицы: три-четыре независимые компании, хроника
    событий, участие органа стандартизации.

    Числа — веса, а не вероятности; они выставлены по знаку и устойчивости признака между
    двумя областями (см. комментарий к RULE_SETTERS), а не подогнаны под результат.
    """
    score = 0.0
    orgs = [str(o) for o in (cand.get("organizations") or []) if str(o).strip()]
    if any(is_rule_setter(o) for o in orgs):
        score += 2.0
        sig.notes.append("в источнике назван орган стандартизации или регулятор — правила появляются раньше рынка")
    if len(orgs) >= 2:
        score += 1.0
        sig.notes.append(f"названы {len(orgs)} организации")
    elif not orgs:
        # Дословно из разбора стенограммы: позиция без игроков эксперту не защищаема,
        # «пустой список игроков — главная причина не засчитать позицию». Такая запись
        # остаётся в выдаче, но не может стать уверенным сигналом.
        score -= 1.0
        sig.notes.append("игроки в источнике не названы")
        sig.no_players = True
    # Дата события приходит в трёх форматах: «2026», «2026-04», «2026-04-01». Достраиваем
    # до полной, иначе fromisoformat падает и признак теряется молча.
    #
    # Достраиваем до КОНЦА периода, а не до начала. Исправлено 28.09.2026: «2024» означает
    # «где-то в 2024», и разворот в 1 января делал событие на год старше, чем известно, —
    # событие декабря 2024 получало возраст 33 месяца и выпадало из окна 24 месяцев,
    # то есть грубая дата наказывала кандидата за то, что источник не назвал день.
    # Конец периода — это «презумпция в пользу кандидата» при той же проверке, и он
    # ограничен сегодняшним днём, чтобы будущая дата не давала отрицательный возраст.
    date = str(cand.get("event_date") or "")[:10]
    if date:
        full = date + {4: "-12-31", 7: "-28"}.get(len(date), "")
        try:
            when = datetime.fromisoformat(full).replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            months = (now - min(when, now)).days / 30.4
            if months <= 24:
                score += 1.0
                sig.notes.append(f"датированное событие {date}")
        except ValueError:
            pass
    if players >= 3:
        score += 2.0
        sig.notes.append(f"{players} независимых игроков")
    elif players == 2:
        score += 1.0
        sig.notes.append("два игрока")
    return score



def base_share_hint(baseline) -> float:
    """Доля свежего в области: с чем сравнивать рост кандидата. Нет замера — медиана эталона."""
    return getattr(baseline, "share", SHARE_MEDIAN) if baseline is not None else SHARE_MEDIAN


def has_fresh_event(cand: dict) -> bool:
    """Есть ли в извлечении датированное событие не старше 24 месяцев.

    Событие из источника сильнее, чем возраст словосочетания в индексе: первое сообщает о
    том, что произошло с технологией, второе — о том, когда кто-то впервые употребил эти
    слова в другом смысле.
    """
    raw = str(cand.get("event_date") or "")[:10]
    if not raw:
        return False
    full = raw + {4: "-12-31", 7: "-28"}.get(len(raw), "")
    try:
        when = datetime.fromisoformat(full).replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    return (now - min(when, now)).days / 30.4 <= 24


def is_rule_setter(name: str) -> bool:
    """Орган стандартизации, консорциум или регулятор. Одним местом — чтобы правку было видно."""
    return bool(RULE_SETTERS.search(name or ""))


def score_candidate(cand: dict, probe, players: int = 0,
                    baseline: DomainBaseline | None = None) -> Signal:
    """Помещает кандидата в окно зрелости и выставляет балл.

    Баллы простые и объяснимые: заказчик просит показать признак, по которому технология
    признана слабым сигналом, а не вес в модели.
    """
    term = term_of(cand)
    if not term:
        # Раньше здесь кандидат уходил с баллом 0 и выбрасывался вызывающей стороной.
        # Измерено 27.09.2026: так терялись девять из десяти кандидатов «Финтеха»,
        # сопоставимых со строками эталона, — им нечем было измерить громкость, но
        # игроки, стадия и датированное событие у них были. Отсутствие прибора — не
        # свойство технологии, поэтому считаем то, что считается без прибора.
        sig = Signal(term="", status="no_term", tier="review",
                     players=players, stage=str(cand.get("stage") or "unknown"),
                     has_evidence=bool(cand.get("evidence")),
                     verdict="громкость не измерена: нет канонического термина")
        if not sig.has_evidence:
            sig.tier, sig.verdict = "rejected", "отбраковано: нет проверенной цитаты"
            return sig
        score = evidence_score(cand, players, sig)
        if sig.stage in ("prototype", "pilot"):
            score += 1.5
            sig.notes.append(f"стадия {sig.stage}")
        elif sig.stage == "scaled":
            score -= 2.5
            sig.notes.append("извлекатель отметил стадию «scaled» — проверьте зрелость")
        sig.notes.append("громкость не измерена: канонический термин не получен")
        sig.score = round(max(score, 0.0), 2)
        return sig

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
        # Единственный безусловный отказ: без цитаты нечего показывать эксперту.
        sig.tier = "rejected"
        sig.verdict = "отбраковано: нет проверенной цитаты"
        return sig

    if total < 0:
        # Ни один источник не ответил: это состояние прибора, а не свойство технологии.
        sig.status = "unmeasured"
        sig.verdict = "зрелость не измерена"
        score = evidence_score(cand, players, sig)
        if sig.stage in ("prototype", "pilot"): score += 1.5; sig.notes.append(f"стадия {sig.stage}")
        sig.notes.append("громкость не измерена: источники не ответили по этому термину")
        sig.score = round(max(score, 0.0), 2)
        return sig

    if total >= 0 and recent < 0:
        # Общее число известно, свежее измерить не удалось. Выдавать это за отсутствие
        # роста нельзя: раньше сбой второго запроса подставлялся нулём, и технология
        # выглядела затухающей из-за отказа сети.
        sig.status = "unmeasured"
        sig.tier = "review"
        sig.verdict = "рост не измерен: источник ответил не полностью"
        sig.notes.append(f"упоминаний всего {total}, за последний год измерить не удалось")
        sig.score = round(max(evidence_score(cand, players, sig) +
                              (1.5 if sig.stage in ("prototype", "pilot") else 0.0), 0.0), 2)
        return sig

    # Возраст словосочетания может относиться к более широкой категории.
    # Возраст и громкость оставляют кандидата на проверке; зрелость требует фактов.
    if sig.age_months is not None and sig.age_months > 48:
        sig.aged_out = True
        # Возраст первого упоминания — ненадёжный признак, и это измерено 28.09.2026 на
        # «Защите ИИ»: один и тот же общий английский термин дал «62 года» трём разным
        # позициям про защиту от инъекций промптов в агентах MCP, а всего возрастной
        # отказ выбил из карточек шесть попаданий в эталонную таблицу заказчика из семи
        # («термину 62 года», «64 года», «61 год» — у понятий, которых в 1964 году не
        # существовало). Прибор меряет возраст словосочетания, а не понятия.
        #
        # Эти показания определяют приоритет проверки, а не доказанный отказ.
        share_now = (recent / total) if total > 0 else 0.0
        growing = share_now >= max(base_share_hint(baseline), 0.3)
        fresh_event = has_fresh_event(cand)
        if total > QUIET_MEDIAN * 10 and not growing and not fresh_event:
            # Возраст/громкость — признаки ранга; исключение требует maturity.decide.
            sig.tier = "review"
            sig.verdict = (f"проверить зрелость: термину {sig.age_months / 12:.0f} лет "
                           f"при {total} упоминаниях и без свежего роста")
            return sig
        sig.tier = "review"
        why = ("но доля свежих упоминаний высокая" if growing else
               "но в источнике есть свежее датированное событие" if fresh_event else
               "проверьте, не старое ли это понятие под новым применением")
        sig.verdict = f"термину {sig.age_months / 12:.0f} лет, {why}"
        sig.notes.append(f"первое упоминание {sig.first_seen} измерено по формулировке "
                         f"«{term}»: возраст словосочетания не равен возрасту понятия")

    base = baseline or DomainBaseline()
    # Громкость тоже относительна: в робототехнике 1,08 млн работ, в защите ИИ — 1933.
    # Абсолютный порог в большой области отбраковал бы всё подряд.
    loud_limit = LOUD_MAX
    if base.known:
        # Нормировка на область обязана иметь потолок. Замер 28.09.2026: при области,
        # измеренной по слишком широким терминам (1 041 032 работы), порог выходил
        # 20 820 — и всё, что громче p90 эталона в 46 раз, считалось тихим. Поднимать
        # порог области можно, но не больше чем в восемь раз от эталонного p90.
        loud_limit = max(LOUD_MAX, min(int(base.total * 0.02), LOUD_MAX * 8))
        sig.notes.append(f"область: {base.total} работ, свежих {base.share:.0%}")
    if total > loud_limit:
        # Громко может быть по двум причинам: технология зрелая или извлечён слишком
        # общий термин. Второе встречалось не реже: кандидат «прецизионная ферментация
        # с использованием инженерных микроорганизмов» мерился по «precision
        # fermentation», а «totality of evidence» и «long-term monitoring» вообще не
        # являются названиями технологий. Различить автоматически мы пока не умеем,
        # поэтому отдаём человеку с прямым указанием, что проверить.
        if sig.stage == "scaled":
            # Возраст/громкость — признаки ранга; исключение требует maturity.decide.
            sig.tier = "review"
            sig.verdict = f"проверить зрелость: масштабировано и громко ({total} упоминаний)"
            return sig
        sig.tier = "review"
        sig.too_loud = True
        sig.verdict = ("громко: технология зрелая или термин слишком общий"
                       if total > loud_limit * 10 else "громко: проверить уровень термина")
        sig.notes.append(f"{total} упоминаний при пороге {loud_limit} для этой области; "
                         f"проверьте, описывает ли «{term}» именно этого кандидата")
        sig.score = round(max(1.0 if players >= 2 else 0.5, 0.0), 2)
        return sig
    if sig.stage == "scaled" and total > loud_limit // 4:
        # Возраст/громкость — признаки ранга; исключение требует maturity.decide.
        sig.tier = "review"
        sig.verdict = (f"проверить зрелость: масштабировано и подтверждено замером "
                       f"({total} упоминаний)")
        return sig
    if total == 0:
        # Ноль при успешном ответе — не «технологии нет». Узкие механизмы вроде
        # «dCas9 binding site detection» живут в тексте статей, а не в заголовках, и
        # фразовый поиск их не находит. По правилу трёх ноль почти ничего не ограничивает.
        sig.tier = "review"
        sig.verdict = "упоминаний не найдено по этой формулировке"
        sig.notes.append("ноль находок не доказывает отсутствие технологии (правило трёх)")
        # Раньше эта ветка давала фиксированные 1.0, и в выдаче «Финтеха» одиннадцать
        # позиций из пятнадцати имели ровно 1.00: порядок внутри них задавался положением
        # в файле. Признаки из evidence_score разводят их по существу.
        score = 1.0 + evidence_score(cand, players, sig)
        if sig.stage in ("prototype", "pilot"): score += 1.0; sig.notes.append(f"стадия {sig.stage}")
        elif sig.stage == "scaled": score -= 2.5; sig.notes.append("метка стадии «scaled» без подтверждения замером")
        sig.score = round(max(score, 0.0), 2)
        return sig

    score = 0.0
    # Главная ось — рост относительно области. Кандидат сравнивается не с общим порогом,
    # а со скоростью обновления своей отрасли.
    #
    # Но доля свежего считается только при достаточном числе наблюдений. Измерено
    # 27.09.2026 на пуле «Финтеха»: у фраз, которые не являются терминами («AI strategy
    # creation», «AI credit risk assessment»), фразовый поиск находит одно-два попадания,
    # оба за последний год, и доля выходит 100 %. Такая запись получала +4.0 за рост и
    # +2.5 за тишину — 6.5 балла из воздуха, и три верхние позиции «Финтеха» были заняты
    # именно ими. При n = 2 доверительный интервал доли по биному примерно [0,16; 1,0]:
    # утверждение «растёт в 1,5 раза быстрее области» на таких числах не обосновано.
    # Порог 10 — это точка, где полуширина интервала доли становится меньше 0,3.
    RATIO_MIN_N = 10
    share = recent / total
    ratio = share / base.share if base.share > 0 else 0.0
    if total < RATIO_MIN_N:
        ratio = 0.0
        sig.notes.append(f"упоминаний всего {total} — рост по такой выборке не оценивается")
    if ratio >= 1.7:
        score += 4.0
        sig.notes.append(f"свежих упоминаний {share:.0%} — в {ratio:.1f} раза быстрее области")
    elif ratio >= 1.2:
        score += 2.5
        sig.notes.append(f"свежих упоминаний {share:.0%} при {base.share:.0%} по области")
    elif ratio >= 0.9:
        score += 1.0
        sig.notes.append(f"свежих упоминаний {share:.0%}, на уровне области")
    # Тишина. Прежний нижний порог «не меньше трёх» отсекал половину настоящих сигналов,
    # включая микроплатежи по HTTP 402 и сканеры MCP-серверов.
    if total <= QUIET_MEDIAN:
        score += 2.5
        sig.notes.append(f"очень тихо: {total} упоминаний при медиане эталона {QUIET_MEDIAN}")
    elif total <= 38:
        score += 1.5
        sig.notes.append(f"тихо: {total} упоминаний")
    score += evidence_score(cand, players, sig)
    if sig.stage in ("prototype", "pilot"):
        score += 1.5
        sig.notes.append(f"стадия {sig.stage}")
    elif sig.stage == "limited_sales":
        score += 1.0
    elif sig.stage == "scaled":
        # Метка не отбраковывает (см. выше), но и не бесплатна: замер громкости её не
        # подтвердил, значит расхождение показаний, и позиция идёт к человеку.
        score -= 2.5
        sig.notes.append("извлекатель отметил «scaled», замер этого не подтвердил")
    # Возраст термина в баллах не участвует: по эталону его медиана 69 месяцев при
    # максимуме 2263, фразовый поиск ловит те же слова в других контекстах. В карточке
    # он остаётся справочно.

    sig.score = round(max(score, 0.0), 2)
    # Позиция без названных игроков не становится уверенным сигналом ни при каком балле:
    # заказчик голосует по каждой позиции, и «кто это делает» — первый вопрос эксперта.
    # Возрастная пометка тоже не перебивается баллом: вердикт и уровень, выставленные
    # воротами, сохраняются, иначе термин 1977 года снова уйдёт в верх списка.
    if sig.aged_out:
        sig.tier = "review"
    elif sig.score >= 5 and not sig.no_players:
        sig.tier, sig.verdict = "signal", "слабый сигнал"
    else:
        sig.tier, sig.verdict = "review", "слабый кандидат"
    return sig
