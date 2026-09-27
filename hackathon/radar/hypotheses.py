"""Путь гипотез: модель предлагает категории, поиск их подтверждает или отбрасывает.

Зачем это понадобилось. Замер 26.09.2026 показал предел конвейера, который строит
план из поисковой выдачи: оценка Чепмена по двум повторам дала N = 8,6 ± 1,0 при
шестнадцати эталонных категориях. Повторять прогоны бесполезно, пул сходится к
девяти. Решающий довод дал «Финтех»: планировщик вывел из выдачи добротную
структуру отрасли (embedded finance, open banking, real-time payments), а эталон
состоит из края отрасли — микроплатежи по HTTP 402, авторизация платежей агентов,
Know Your Agent. Вывести край из описания структуры нельзя, а модель о нём знает.

Дисциплина замера. Кандидат, пришедший этим путём, помечается origin="hypothesis".
Складывать два пути в одну метрику покрытия без указания долей нельзя: модель,
знающая рынок, частично воспроизводит ответ по памяти, и высокое покрытие по пути
гипотез не доказывает способность системы находить новое. Таблица заказчика модели
по-прежнему не передаётся — она получает только направление пользователя.

Проверка доказательств одинакова для обоих путей: цитата должна дословно находиться
в тексте загруженного документа, иначе гипотеза считается неподтверждённой.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .config import Candidate, Evidence, SearchHit, Settings
from .fetch import parse_html

HYPOTHESIS_SYSTEM = """Ты предлагаешь гипотезы о технологических категориях ранней стадии.

Верни только JSON: {"hypotheses": [{"name_ru": "...", "name_en": "...",
"mechanism": "...", "object": "...", "why_early": "...", "queries": ["...", "..."]}]}.

Категория ранней стадии — это класс решений, который уже кто-то делает, публикует
или пилотирует, но массового рынка ещё нет: первые продукты, первые стандарты,
первые препринты. Не зрелые технологии, о которых пишут пятый год.

Уровень обобщения. Имя строится как «механизм + объект + существенный контекст».
Слишком широко — направление целиком или родительский класс. Слишком узко —
отдельный приём внутри категории. Признак верного уровня: решение можно купить,
внедрить или опубликовать как отдельную вещь.

Нельзя: названия компаний и продуктов вместо категорий; названия научных задач и
типов атак сами по себе; общие слова вроде «безопасность» или «автоматизация».

Думай о крае направления, а не о его структуре. Структуру отрасли — крупные
сегменты, о которых пишут обзоры, — не предлагай: она заведомо зрелая.

Поле queries — два-три поисковых запроса на английском, по которым эту категорию
можно найти, если она существует. Запросы должны содержать термины, которыми о ней
говорят авторы, а не пересказ твоего описания.

Поле why_early — почему ты считаешь это ранней стадией. Одна фраза.

Ты можешь ошибаться: каждая гипотеза будет проверена поиском, и неподтверждённые
будут отброшены. Поэтому предлагай и рискованные, но не выдумывай несуществующее."""

VERIFY_SYSTEM = """Ты проверяешь, подтверждают ли найденные тексты гипотезу о категории.

Верни только JSON: {"confirmed": true|false, "hit_index": <номер или null>,
"quote": "<дословный фрагмент из текста этого фрагмента или null>",
"why": "<одна фраза>"}.

Подтверждение засчитывается, только если текст описывает тот же механизм и тот же
объект применения, что и гипотеза, и это конкретное утверждение, а не упоминание
темы. Обзор направления, список терминов и реклама без описания механизма
подтверждением не являются.

Цитату переписывай дословно, без перевода и без сокращений в середине. Если
дословной цитаты нет, верни confirmed=false. Выдумывать цитату нельзя: она будет
проверена на вхождение в исходный текст, и выдуманная отбросит всю гипотезу."""


@dataclass
class Hypothesis:
    name_ru: str
    name_en: str
    mechanism: str
    object_affected: str
    why_early: str
    queries: list[str] = field(default_factory=list)
    status: str = "pending"      # pending | confirmed | rejected | quote_not_found
    note: str = ""


def generate(direction: str, llm, count: int = 30, batch: int = 8,
             log: list[str] | None = None) -> tuple[list[Hypothesis], int, int]:
    """Гипотезы из знаний модели, партиями. Таблица заказчика сюда не передаётся.

    Партиями, потому что 30 гипотез в одном JSON не помещаются в лимит ответа:
    проверено 26.09.2026 — ответ обрывался на середине и разбор давал ноль. Каждая
    следующая партия получает список уже предложенных имён, чтобы не повторяться.
    """
    out: list[Hypothesis] = []
    seen: set[str] = set()
    in_tok = out_tok = 0
    while len(out) < count:
        need = min(batch, count - len(out))
        payload = {"direction": direction, "сколько_гипотез": need}
        if seen:
            payload["уже_предложено_не_повторять"] = sorted(seen)
        text, i_tok, o_tok = llm.complete(HYPOTHESIS_SYSTEM, payload)
        in_tok += i_tok
        out_tok += o_tok
        if log is not None:
            log.append(text)
        try:
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        except (json.JSONDecodeError, ValueError):
            break  # обрыв или мусор: лучше меньше гипотез, чем молчаливый ноль
        added = 0
        for row in data.get("hypotheses", []):
            if not isinstance(row, dict) or not row.get("name_ru") or not row.get("mechanism"):
                continue
            name = str(row["name_ru"]).strip()
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            added += 1
            out.append(Hypothesis(
                name_ru=name,
                name_en=str(row.get("name_en") or "").strip(),
                mechanism=str(row["mechanism"]).strip(),
                object_affected=str(row.get("object") or "").strip(),
                why_early=str(row.get("why_early") or "").strip(),
                queries=[str(q).strip() for q in (row.get("queries") or []) if str(q).strip()][:3],
            ))
        if added == 0:
            break  # модель перестала давать новое
    return out[:count], in_tok, out_tok


def verify(hyp: Hypothesis, searcher, llm, fetcher=None, hits_per_query: int = 5
           ) -> tuple[Candidate | None, int, int, int]:
    """Ищет подтверждение гипотезе и возвращает кандидата с проверенной цитатой.

    Возвращает (кандидат или None, входные токены, выходные токены, платных вызовов).
    Кандидат создаётся только если цитата дословно найдена в тексте документа.
    """
    hits: list[SearchHit] = []
    paid = 0
    for query in hyp.queries[:2] or [hyp.name_en or hyp.name_ru]:
        # research уходит в академическую базу бесплатно, product — в веб.
        for lens in ("research", "product"):
            found = searcher.search(query, "en", lens, hits_per_query)
            if lens == "product":
                paid += 1
            hits.extend(found)
        if len(hits) >= hits_per_query * 2:
            break
    if not hits:
        hyp.status, hyp.note = "rejected", "поиск не дал результатов"
        return None, 0, 0, paid

    snapshots = getattr(searcher, "snapshots", {}) or {}
    payload = {
        "гипотеза": {"название": hyp.name_ru, "механизм": hyp.mechanism,
                     "объект": hyp.object_affected},
        "фрагменты": [{"index": i, "заголовок": h.title, "текст": h.snippet[:700]}
                      for i, h in enumerate(hits[:8])],
    }
    text, in_tok, out_tok = llm.complete(VERIFY_SYSTEM, payload)
    try:
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError):
        hyp.status, hyp.note = "rejected", "ответ проверяющего не разобран"
        return None, in_tok, out_tok, paid

    idx, quote = data.get("hit_index"), (data.get("quote") or "").strip()
    if not data.get("confirmed") or not isinstance(idx, int) or not quote or idx >= len(hits):
        hyp.status = "rejected"
        hyp.note = str(data.get("why", ""))[:200]
        return None, in_tok, out_tok, paid

    hit = hits[idx]
    # Цитата проверяется по полному тексту документа, а не по сниппету выдачи.
    doc = snapshots.get(hit.url)
    if doc is None and fetcher is not None:
        result, body = fetcher.fetch(hit.url)
        if result.status == "ok" and body is not None:
            doc = parse_html(body, hit.url, result.final_url or hit.url)
    haystack = doc.text if doc is not None else hit.snippet
    if quote not in haystack:
        hyp.status = "quote_not_found"
        hyp.note = f"цитата не найдена в тексте {hit.url}"
        return None, in_tok, out_tok, paid

    hyp.status, hyp.note = "confirmed", str(data.get("why", ""))[:200]
    start = haystack.find(quote)
    return Candidate(
        name_ru=hyp.name_ru, name_orig=hyp.name_en or None, mechanism=hyp.mechanism,
        object_affected=hyp.object_affected or None, context=hyp.why_early or None,
        evidence=[Evidence(quote=quote, start=start, end=start + len(quote),
                           source_url=hit.url,
                           document_sha256=doc.text_sha256 if doc is not None else None)],
        source_url=hit.url, document_sha256=doc.text_sha256 if doc is not None else "",
        origin="hypothesis",
    ), in_tok, out_tok, paid
