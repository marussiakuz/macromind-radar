"""Выбор канонического термина из цитат и нормализация участников.

Число документов, доменов и независимых организаций учитывается раздельно."""
from __future__ import annotations

import json
import re
import sys as _sys
from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import abbrev

# Юридические суффиксы и обвязка: «Acme», «ACME» и «Acme Inc.» это один игрок, а не три.
_LEGAL = re.compile(r"\b(inc|llc|ltd|limited|corp|corporation|gmbh|s\.?a\.?|b\.?v\.?|"
                    r"plc|co|company|labs?|technologies|technology|ai|group|holdings?)\b\.?",
                    re.IGNORECASE)


def normalize_org(name: str) -> str:
    """Ключ организации: без регистра, пунктуации и юридических суффиксов.

     подсчёт независимых игроков считал три написания одного имени
    тремя компаниями и завышал главный признак конвергенции.
    """
    s = re.sub(r"[^0-9A-Za-zА-Яа-яёЁ\s-]", " ", (name or "").lower())
    s = _LEGAL.sub(" ", s)
    return " ".join(s.split())

# Сокращение как термин: 2–6 символов, без пробелов, преимущественно заглавные.
# Границы взяты из постановки задачи, а не из данных: «ABAC», «MCP», «ACS» проходят,
# «AI governance» — нет (внутри аббревиатура, но меряется словосочетание, и оно осмысленно).
ABBREV_MAX_LEN = 6   # граница из постановки задачи; «AI-SBOM» (7 знаков) в неё не попадает
_ABBREV_SHAPE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z./-]{1,%d}$" % (ABBREV_MAX_LEN - 1))


def is_abbrev_term(term: str) -> bool:
    """Термин целиком выглядит аббревиатурой и потому непригоден для замера громкости."""
    text = (term or "").strip()
    if not _ABBREV_SHAPE.match(text):
        return False
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 2:
        return False
    return sum(1 for c in letters if c.isupper()) >= max(2, (len(letters) + 1) // 2)


def source_text_of(cand: dict, texts: dict[str, str] | None = None) -> str:
    """Текст, по которому ищется расшифровка: цитаты кандидата плюс сохранённый документ.

    Замер 28.09.2026 на прогоне «Защита ИИ»: по цитатам «ABAC» не раскрывается (пара
    «Attribute-Based Access Control (ABAC)» стоит в документе выше вырезанного отрывка),
    по тексту документа — раскрывается. Поэтому документ подмешивается, когда он передан;
    без него работает прежний путь по цитатам.
    """
    parts = [(e.get("quote") or "") for e in (cand.get("evidence") or [])]
    if texts:
        keys = [cand.get("document_sha256")]
        keys += [e.get("document_sha256") for e in (cand.get("evidence") or [])]
        for key in dict.fromkeys(k for k in keys if k):
            if texts.get(key):
                parts.append(texts[key])
    return "\n".join(parts)


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

Если цитата на русском, термин всё равно верни по-английски: индексы, по которым мы
считаем громкость, англоязычные. Русская цитата — не причина отказаться от термина.

Если в цитате нет устоявшегося термина, а есть только пересказ — верни null. Не
придумывай термин сам: пустой ответ полезнее выдуманного, потому что по выдуманному
мы посчитаем громкость несуществующей вещи.

Вместе с термином верни `quote_fragment` — **дословный** отрывок из приведённой цитаты
(на её языке, 2–12 слов), на котором основан термин. По нему мы проверяем, что термин
взят из источника, а не придуман.

Верни только JSON:
{"terms": [{"index": <номер>, "term": "<термин или null>", "quote_fragment": "<отрывок>"}]}."""


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


def canonical_terms(candidates: list[dict], llm, batch: int = 12,
                    texts: dict[str, str] | None = None) -> dict[int, str | None]:
    """Термин из цитаты для каждого кандидата. Индекс — позиция в переданном списке.

    `texts` — необязательное отображение «sha256 документа → сохранённый текст». Нужно
    только для расшифровки аббревиатур: без него термин-сокращение раскрывается лишь по
    цитатам, а это удаётся редко (замер ниже, в месте вызова abbrev.expand).
    """
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
        except (ValueError, KeyError) as exc:
            # Сбой разбора одной пачки оставлял без термина сразу двенадцать кандидатов,
            # и раньше это было равносильно их выбрасыванию — молча. Теперь отказ виден
            # в логе, а сами кандидаты доходят до оценки без замера громкости.
            print(f"корроборация: пачка {start}–{start + len(chunk) - 1} без термина "
                  f"({type(exc).__name__})", file=_sys.stderr)
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
            # Модель иногда пишет отсутствие значения строкой. Проверено 27.09.2026:
            # термин «null» прошёл дальше и был измерен как 524 965 упоминаний.
            if term.strip().lower() in {"null", "none", "n/a", "нет", "-", "—"}:
                out[idx] = None
                continue
            # Привязка к источнику проверяется по отрывку цитаты, а не по английскому
            # термину. Прежнее правило «термин обязан дословно встречаться в цитате»
            # противоречило этому же промпту: он требует назвать КЛАСС решений, когда в
            # цитате стоит имя продукта, — а класс по определению другими словами, и
            # проверка его тут же отбрасывала. Измерено 27.09.2026 на сохранённых пулах:
            # у 18 из 96 кандидатов «Финтеха» и у 8 из 85 «Защиты ИИ» цитата вообще
            # русская, и ни один английский термин пройти такую проверку не мог — среди
            # них были рублёвые стейблкоины Банка России и аудит MCP от PWN AI.
            # Смысл проверки (не пропускать выдуманное) сохранён: модель обязана указать
            # дословный отрывок, и проверяется он.
            quotes = " ".join((e.get("quote") or "") for e in (candidates[idx].get("evidence") or []))
            fragment = str(row.get("quote_fragment") or "").strip()
            if quotes:
                norm_q = " ".join(quotes.lower().split())
                grounded = (" ".join(term.lower().split()) in norm_q
                            or (len(fragment) >= 8 and " ".join(fragment.lower().split()) in norm_q))
                if not grounded:
                    out[idx] = None
                    continue
            # Термин не должен совпадать с названием организации из того же кандидата:
            # иначе в окно зрелости уходит торговое имя, а не класс решений.
            orgs = {normalize_org(str(o)) for o in (candidates[idx].get("organizations") or [])}
            if normalize_org(term) in orgs:
                out[idx] = None
                continue
            # Термин-аббревиатура меряется не как технология, а как строка из трёх букв.
            # Замер 28.09.2026 по сохранённым прогонам: в отбраковке «Защиты ИИ» стоит
            # термин «ABAC» с приговором «термину 133 лет при 2404 упоминаниях», хотя его
            # документ прямо содержит «Open Policy Agent (OPA) has become the standard for
            # implementing ABAC» и выше — «Attribute-Based Access Control (ABAC)». Из 76
            # сохранённых канонических терминов сокращением целиком был ровно один, так что
            # срабатывает это редко, но там, где срабатывает, замер был заведомо ложным.
            # Расшифровка берётся только из текста самого источника (алгоритм Шварца и
            # Хёрст, radar/abbrev.py): выдумать полную форму — значит измерить то, чего нет.
            if is_abbrev_term(term):
                full, note = abbrev.expand(term, source_text_of(candidates[idx], texts))
                # Раскрытая форма проходит те же проверки, что и термин от модели: длина
                # и несовпадение с названием организации из того же кандидата.
                if full != term and 2 < len(full) <= 60 and normalize_org(full) not in orgs:
                    print(f"корроборация: {note}", file=_sys.stderr)
                    term = full
            # Те же требования, что и к запасному пути: не оборот речи, не название
            # целой области, не описание в восемь слов. Проверено 27.09.2026: модель
            # выдавала «federated learning» для антиотмывочного применения, «Gini index»
            # для кредитного скоринга и восьмисловное описание вместо термина.
            out[idx] = term
    return out


def saved_texts(run) -> dict[str, str]:
    """Сохранённые тексты прогона по sha256 — аргумент `texts` для canonical_terms.

    Отдельная функция, чтобы подключение расшифровки в вызывающем коде было одной строкой:
    `canonical_terms(pool, llm, texts=saved_texts(run))`. Ни одного сетевого запроса.
    """
    from pathlib import Path
    out: dict[str, str] = {}
    path = Path(run) / "documents.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            continue
        key, text = doc.get("text_sha256"), doc.get("text")
        if key and text:
            out[key] = text
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
