"""HTTP-сервис радара: открытый запрос пользователя запускает настоящий конвейер.

Заказчик проверяет решение открытым запросом и прямо называет примеры вне таблицы —
«слабые сигналы в 3D-печати», «Микрофлюидный чип», «Гардрейл». Статическая выгрузка
результатов этого не выдерживает: что ни введи, показывается один и тот же прогон.
Поэтому здесь запрос запускает конвейер, а интерфейс опрашивает состояние.

Прогон занимает минуты и стоит денег, поэтому:
  * результат по запросу кешируется и повторный запрос отдаётся мгновенно;
  * есть демонстрационный режим: запрос отдаёт сохранённый прогон, ничего не тратя.

    .venv/bin/python -m radar.server            # 127.0.0.1:8000
    RADAR_DEMO=1 .venv/bin/python -m radar.server   # только сохранённые прогоны
"""
from __future__ import annotations

import json
import os
import re
import threading
import traceback
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import RUNS_DIR, Settings, load_env_file
from .export_ui import to_trend
from .gate import assess as assess_query
from .merging import merge as merge_equivalents
from .sequential import run_filters
from .maturity import VERSION as maturity_version_value
from .feasibility import VERSION as refutation_version_value
from .dossier import collect as collect_dossier
from .players import find_players
from .pipeline import run_pool
from .rank import (SCORE_WITHOUT_TERM, HackerNewsProbe, MaturityProbe, OpenAlexProbe,
                   field_terms, measure_baseline, score_candidate)
from .corroborate import (canonical_terms, cluster_by_term, domain_of,
                          normalize_org, saved_texts)
from .extract import YandexLLM
from .reference import load_reference
from .search import MultiSearch, YandexSearch

app = FastAPI(title="Радар слабых сигналов")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def maturity_version() -> str:
    return maturity_version_value


def refutation_version() -> str:
    return refutation_version_value


def cutoff_of(run: Path) -> str:
    """Срез прогона: дата, на которую собраны документы. Из имени каталога прогона."""
    stamp = run.name.split("-")[0]
    if len(stamp) == 8 and stamp.isdigit():
        return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
    return datetime.now(timezone.utc).date().isoformat()


def recent_event(raw: str, cutoff: str, max_days: int = 760) -> bool:
    from .maturity import date_bounds
    bounds = date_bounds(raw)
    as_of = date.fromisoformat(cutoff)
    return bool(bounds and bounds[1] <= as_of and 0 <= (as_of - bounds[0]).days <= max_days)


def proof_candidates(pairs):
    """Retain the full pool, prioritizing positive maturity evidence for investigation."""
    return [c for _, c in sorted(pairs, key=lambda pair: (
        pair[1]['_assessment']['domain'] != 'no',
        pair[1]['_assessment']['stage'] == 'mature_hint'), reverse=True)]


DEMO = os.environ.get("RADAR_DEMO") == "1"
# Версия сборки карточек. Кеш готовых карточек действителен только для той версии,
# которой он собран: при правке оценки версию поднять, иначе демонстрация покажет
# старый результат как новый.
CARDS_VERSION = "cards/2026-09-29-tree2"
JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_WORK_LOCK = threading.Lock()


class SearchRequest(BaseModel):
    query: str
    plan: str = "tree"          # tree | mixed | pains | segments
    demo: bool = False
    # Аналитик может ввести что угодно, и на непригодном запросе прогон стоит около 90 ₽ и
    # пятнадцать минут. Привратник проверяет запрос двумя поисковыми вызовами и отвечает
    # человеку, если запрос понят как товар, распадается на два смысла или не даёт материала.
    # `force` — «я понимаю, запускай»: решение остаётся за аналитиком, а не за нами.
    force: bool = False


def known_area(query: str) -> str:
    """Если запрос совпал с областью таблицы, считаем метрику покрытия заодно."""
    try:
        reference, _ = load_reference()
    except Exception:
        return ""
    q = query.lower()
    for area in {i.area for i in reference}:
        if area.lower() in q or q in area.lower():
            return area
    return ""


def cached_run(query: str) -> Path | None:
    """Последний сохранённый прогон с тем же запросом."""
    best = None
    for run in sorted(RUNS_DIR.glob("2026*"), reverse=True):
        manifest = run / "manifest.json"
        if not manifest.exists() or not (run / "candidates.jsonl").exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get('mode') != 'live':
            continue
        if (data.get("query", "").strip().lower() == query.strip().lower()
                or data.get('area', '').strip().lower() == query.strip().lower()):
            best = run
            break
    return best


def build_cards(run: Path, job: dict, searcher) -> list[dict]:
    """Кандидаты прогона → карточки: канонический термин, окно зрелости, признаки."""
    pool = [json.loads(l) for l in (run / "candidates.jsonl").read_text(encoding="utf-8").split('\n') if l.strip()]
    # Дата публикации документа по адресу: без неё в карточке стояло «—» у всех источников,
    # хотя в прогоне дата есть у двух третей документов (разбор аналитика 28.09.2026).
    doc_dates: dict[str, str] = {}
    if (run / "documents.jsonl").exists():
        for line in (run / "documents.jsonl").read_text(encoding="utf-8").split('\n'):
            if not line.strip(): continue
            d = json.loads(line)
            when = (d.get("published_at") or "")[:10]
            if not when:
                continue
            for key in (d.get("final_url"), d.get("url")):
                if key:
                    doc_dates.setdefault(key, when)
                    doc_dates.setdefault(key.rstrip("/"), when)
    job["stage"] = "термины"
    llm = YandexLLM(Settings(), max_tokens=1200)
    search_cost_before = getattr(searcher, 'spent_rub', 0.0)
    # Тексты прогона нужны для расшифровки аббревиатур: по одним цитатам определение
    # почти никогда не находится (измерено — 0 из 1), а по тексту документа находится.
    terms = canonical_terms(pool, llm, texts=saved_texts(run))
    clusters = cluster_by_term(pool, terms)
    players = {id(c): cl.players for cl in clusters for c in cl.candidates}
    sources = {id(c): cl.independent_sources for cl in clusters for c in cl.candidates}

    job["stage"] = "проверка принадлежности области"
    from .relevance import direction_of, filter_in_domain
    # Направление спрашиваем без слов нашей задачи: с ними модель браковала финтех
    # как «не слабые сигналы» — 81 кандидат из 96 (замер 28.09.2026).
    direction = direction_of(job["query"])
    job["direction"] = direction
    in_domain, why_domain = filter_in_domain(
        [f"{c['name_ru']}. {c['mechanism'][:140]}" for c in pool], direction, llm)

    job["stage"] = "скорость области"
    # Рост кандидата считается относительно его отрасли: разброс базовой скорости
    # обновления между областями пятикратный, и единый порог отбраковал бы медленные.
    # Optional enrichment: hundreds of sequential bibliometric requests dominated
    # latency, and term age/volume cannot prove maturity of a narrow mechanism.
    bibliometrics = os.environ.get('RADAR_BIBLIOMETRICS', '0') == '1'
    probe = MaturityProbe([OpenAlexProbe(), HackerNewsProbe()] if bibliometrics else [])
    # Та же ошибка, что была у проверки области: с запросом «слабые сигналы в защите ИИ»
    # модель вернула область ["artificial intelligence", "cybersecurity",
    # "signal processing"] — последнее прямо из наших слов задачи — и объём области
    # вышел 1 041 032 работы вместо ~2 000. Порог громкости считается от объёма
    # области, поэтому он раздулся в 50 раз, и термины 1964 года с 19 560
    # упоминаниями проходили как ранний сигнал. Спрашиваем область без слов задачи.
    broad = field_terms(direction, llm) if bibliometrics else []
    baseline = measure_baseline(broad, probe)
    job["baseline"] = {"доля свежего в области": round(baseline.share, 3),
                       "объём области": baseline.total, "по термину": baseline.terms}
    job['bibliometrics'] = 'measured' if bibliometrics else 'not_requested'

    job["stage"] = "окно зрелости"
    scored, review, rejected = [], [], []
    for i, cand in enumerate(pool):
        term = terms.get(i)
        if not term and not SCORE_WITHOUT_TERM:
            continue
        # Кандидат без канонического термина больше не выбрасывается. Измерено 27.09.2026
        # на сохранённых пулах: на «Финтехе» пригодный термин был у 1 из 10 кандидатов,
        # которые я вручную сопоставил со строками эталона, и у 36 из 86 остальных — то
        # есть отсев по термину работал против эталона. Балл такого кандидата считается по
        # признакам, не требующим замера (см. rank.evidence_score), и он остаётся в tier
        # «review» с честной пометкой «громкость не измерена».
        sig = score_candidate({**cand, "name_orig": term or ""}, probe,
                              players=players.get(id(cand), 0), baseline=baseline)
        if not bibliometrics:
            sig.notes = [('громкость не измерена: библиометрическое обогащение отключено'
                          if n.startswith('громкость не измерена:') else n) for n in sig.notes]
        if sources.get(id(cand), 0) >= 2:
            sig.score += 1.5
            sig.notes.append(f"подтверждено с {sources[id(cand)]} разных доменов")
        # Принадлежность области не отбрасывает, а понижает: разбор 27.09 показал, что
        # фильтр выкинул цифровые двойники клинических испытаний как «не биотех», а на
        # другом прогоне пропустил платежи ИИ-агентов. Он несогласован, и доверять ему
        # безвозвратное решение нельзя.
        if sig.has_evidence and not in_domain.get(i, True):
            sig.tier = "review"
            sig.score = round(max(0.0, sig.score - 3.0), 2)
            sig.notes.append(f"сомнение в принадлежности области: {why_domain.get(i, '')}")
        if sig.tier == "signal":
            scored.append((sig, cand))
        elif sig.tier == "review":
            review.append((sig, cand))
        else:
            # Список отбракованных заказчик прямо назвал плюсом, а до 28.09.2026 страница
            # «Исключённые» жила на статичной выгрузке и на живом запросе показывала
            # прошлый прогон. Причина отказа берётся та же, что видел фильтр.
            rejected.append({
                "name": cand.get("name_ru", ""),
                "term": sig.term,
                "reason": sig.verdict or "признаков раннего сигнала не набралось",
                "score": sig.score,
                "notes": sig.notes[:3],
                "source_url": cand.get("source_url", ""),
            })
    probe.close()
    scored.sort(key=lambda x: -x[0].score)
    review.sort(key=lambda x: -x[0].score)
    # Спорное идёт после уверенного и помечено. Пустая выдача из-за ошибки фильтра хуже,
    # чем выдача с честной пометкой: решение всё равно за экспертом.
    job["confident"] = len(scored)
    job["needs_review"] = len(review)

    # Последовательные фильтры: доказанно зрелое и доказанно опровергнутое. Без модели
    # применяются только ранее сохранённые решения — это бесплатно и честно: непроверенные
    # кандидаты помечаются как непроверенные, а не как оставленные.
    # Порядок обязателен по заданию: пул → зрелость → фантастика → объединение.
    job["stage"] = "доказательные фильтры"
    # Фильтры смотрят весь рассматриваемый пул, а не только уверенные позиции: замер
    # 29.09.2026 показал, что при передаче одного уровня они видели одного кандидата из
    # ста тридцати пяти и отчёт выглядел пустым.
    under_review = scored + review
    from .assessment import assess, priority, dated_assessment
    from .sequential import candidate_key
    job['stage'] = 'проверка предмета и ранних проявлений по цитатам'
    assessments = assess([c for _, c in under_review], direction, llm, run)
    for sig, cand in under_review:
        source_date = doc_dates.get(cand.get('source_url',''))
        a = dated_assessment(assessments[id(cand)], source_date, cand.get('event_date'), cutoff_of(run))
        assessments[id(cand)] = a
        cand['_assessment'] = a
        sig.notes.append('Оценка по цитатам: ' + a['stage'] + '. ' + a['delta'])
    under_review.sort(key=lambda pair: priority(assessments[id(pair[1])], pair[0].score), reverse=True)
    # Budgeted proof checks on leading candidates; all unchecked candidates remain visible.
    from .fetch import Fetcher
    filter_limit = int(os.environ.get('RADAR_FILTER_LIMIT', '15'))
    # Under a bounded proof budget, inspect likely mature in-domain items first.
    # This affects only investigation order, never the decision to exclude.
    with Fetcher(Settings(), raw_dir=run / 'usage-raw') as usage_fetcher:
        verdicts = run_filters(proof_candidates(under_review), run, cutoff_of(run),
                               llm=llm if filter_limit else None, limit=filter_limit,
                               searcher=searcher, fetcher=usage_fetcher)
    excluded_keys = {candidate_key(c) for c in verdicts.mature + verdicts.refuted}
    if excluded_keys:
        for item in verdicts.mature:
            rejected.append({"name": item["name_ru"], "term": "",
                             "reason": "исключено как доказанно зрелое: "
                                       + str(item["_decision"].get("route")),
                             "score": 0.0, "notes": [], "source_url": item.get("source_url", "")})
        for item in verdicts.refuted:
            rejected.append({"name": item["name_ru"], "term": "",
                             "reason": "исключено как доказанно опровергнутое: "
                                       + str(item["_decision"].get("route")),
                             "score": 0.0, "notes": [], "source_url": item.get("source_url", "")})
        under_review = [(sig, cand) for sig, cand in under_review if candidate_key(cand) not in excluded_keys]
    job["filters"] = {**verdicts.summary,
                      "правила": [maturity_version(), refutation_version()],
                      "заметки": verdicts.notes[:3]}

    # Объединение эквивалентных записей до отбора пятнадцати: иначе склейка оставляет
    # пустые слоты, и проверенные позиции не доходят (замер 28.09.2026 — карточек выходило
    # 10 вместо 15). Прежняя склейка шла по пересечению слов длиннее пяти знаков и
    # объединяла разное; теперь векторы предлагают пары, а решают проверка объекта и
    # признаков семьи технологии, и узкие категории не поглощаются.
    # Сортировку по метке «вне области» я пробовал и откатил 29.09.2026 — измерение
    # остановило. На Edge проверка области помечает 9 позиций из 15, и среди них законные
    # темы области: проектирование IoT-чипов на основе чиплетов и оркестрация нейроморфных
    # ускорителей. Наверх при такой сортировке поднималось «федеративное обучение для
    # клинической диагностики», то есть выдача становилась хуже. Порядок остаётся по баллу,
    # а метка живёт в признаках позиции для эксперта.
    order = under_review
    # Save the whole residual queue before top-15 truncation, including uncertainty.
    (run / 'working-candidates.json').write_text(json.dumps([
        {**cand, '_score': sig.score, '_tier': sig.tier} for sig, cand in order], ensure_ascii=False, indent=2))
    job['assessment'] = {'early_with_citation': sum(c['_assessment']['stage'] == 'early' for _, c in order),
                         'unknown': sum(c['_assessment']['stage'] == 'unknown' for _, c in order),
                         'out_of_domain': sum(c['_assessment']['domain'] == 'no' for _, c in order),
                         'human_validated': False}
    for sig, cand in order:
        if cand['_assessment']['domain'] == 'no':
            rejected.append({'name': cand.get('name_ru', ''), 'term': sig.term,
                'reason': 'вне запроса по оценке модели; сохранена в полном пуле для проверки',
                'score': sig.score, 'notes': [cand['_assessment']['domain_reason']],
                'source_url': cand.get('source_url', '')})
    order = [(sig, cand) for sig, cand in order if cand['_assessment']['domain'] != 'no']
    groups = merge_equivalents([c for _, c in order])
    lead_of = {id(g.leader): g for g in groups}
    absorbed = {id(m) for g in groups for m in g.members}
    picked: list = []
    chosen_names = set()
    merged = len(absorbed)
    for sig, cand in order:
        if len(picked) >= 15:
            break
        if id(cand) in absorbed:
            continue
        chosen_names.add(id(cand))
        group = lead_of.get(id(cand))
        if group is not None and group.aliases:
            sig.notes.append("объединено эквивалентных записей: " + "; ".join(group.aliases[:3])[:160])
            cand = {**cand, "merged_aliases": group.aliases[:6]}
        picked.append((sig, cand))
    job["merged_duplicates"] = merged
    # Всё, что не попало в пятнадцать, идёт в список отбракованного с причиной: у
    # заказчика этот список отдельный плюс, а беззвучное выбытие лишало нас проверенных
    # позиций и скрывало ошибку.
    for sig, cand in order:
        if id(cand) in chosen_names or id(cand) in absorbed:
            continue
        rejected.append({"name": cand.get("name_ru", ""), "term": sig.term,
                         "reason": "не попала в пятнадцать: ниже по релевантности, доказательствам стадии и баллу",
                         "score": sig.score, "notes": sig.notes[:3],
                         "source_url": cand.get("source_url", "")})
    scored = picked
    # Учёт закрывается здесь, после свода дублей и добора: до правки счётчик считался
    # раньше этого блока, и позиции, не попавшие в пятнадцать, в него не входили —
    # 34 кандидата из 85 оставались вне и карточек, и списка отбракованного.
    rejected.sort(key=lambda r: -r["score"])
    job["rejected"] = rejected[:60]
    job["rejected_total"] = len(rejected)
    job["accounted"] = len(scored) + len(rejected) + merged
    job["out_of_domain_flagged"] = sum(1 for i in range(len(pool)) if not in_domain.get(i, True))

    # Второй хоп только по верхним карточкам: эксперт спрашивает «кто это делает»,
    # и пустой список игроков — главная причина не засчитать позицию. Ограничиваем
    # восемью, чтобы уложиться в бюджет времени и денег.
    job["stage"] = "поиск реализаторов"
    # Второй поиск идёт по всем пятнадцати позициям, а не по верхним восьми. Замер
    # 28.09.2026: игроки нашлись у 5 карточек из 15 на «Защите ИИ» и у 7 из 15 на
    # «Финтехе», а позиция без названных реализаторов не может стать уверенной — это
    # первый вопрос эксперта. Цена вопроса около трёх запросов на карточку.
    top_for_hop = scored[:15]
    for sig, cand in top_for_hop:
        try:
            ev = find_players(sig.term, cand.get("mechanism", ""), searcher, llm,
                              known=cand.get("organizations") or [])
        except Exception as exc:
            # Молчаливый пропуск уже прятал NameError: второй хоп «работал» и ничего
            # не находил на всех карточках подряд. Отказ должен быть виден.
            job.setdefault("player_errors", []).append(f"{sig.term[:30]}: {type(exc).__name__}")
            continue
        if not ev.players:
            continue
        cand["players_found"] = [
            {"name": p.name, "role": p.role, "what": p.what, "quote": p.quote, "url": p.url}
            for p in ev.players]
        # Независимые реализаторы — сильнейший признак того, что категория названа
        # верно: три команды, делающие одно и то же, и есть определение категории.
        # Число компаний — признак с двумя концами, и заказчик сказал это дословно:
        # технологии отбраковывались «по уже большому количеству упоминаний и компаний».
        # В таблице у строки три-четыре компании — это формирующаяся категория. Проверка
        # аналитика 28.09.2026 показала обратную ошибку у нас: AP2 с шестьюдесятью
        # партнёрами и трансграничные стейблкоины с девяноста процентами организаций в
        # пилотах получали прибавку за число игроков и уходили в верх списка.
        if ev.independent >= 8:
            sig.too_loud = True
            sig.notes.append(f"{ev.independent} реализаторов найдено вторым поиском — "
                             f"для зарождающейся категории это много, проверьте зрелость")
        elif ev.independent >= 3:
            sig.score += 2.5
            sig.notes.append(f"{ev.independent} независимых реализатора найдено вторым поиском")
        elif ev.independent == 2:
            sig.score += 1.5
            sig.notes.append("два независимых реализатора найдено вторым поиском")
        # Повышение до «уверенного» по баллу допустимо только там, где замер состоялся
        # и не поднял флагов. Иначе балл, набранный признаками из источника, перекрывал
        # пометки «громко» и «термин старше четырёх лет», и такие позиции уходили в
        # верх списка как ранние сигналы (замер 28.09.2026: первое упоминание 1964 года).
        if (sig.tier == "review" and sig.score >= 5 and sig.status == "ok"
                and not sig.aged_out and not sig.too_loud):
            sig.tier = "signal"
    # Доказательная папка: хроника и раунды. Аналитик банка отказывал позициям за пустые
    # поля — «ни одной даты», «ни одного раунда, хотя суммы и лид-инвесторы лежат в
    # источниках», «все источники с одного домена». Поля добираются адресно по термину.
    job["stage"] = "хроника и сделки"
    cutoff = cutoff_of(run)
    for sig, cand in scored[:15]:
        if not sig.term:
            continue
        try:
            dos = collect_dossier(sig.term, cand.get("mechanism", ""), searcher, llm, cutoff)
        except Exception as exc:
            job.setdefault("dossier_errors", []).append(f"{sig.term[:30]}: {type(exc).__name__}")
            continue
        cand["chronology"] = [{"date": e.date, "org": e.org, "what": e.what,
                               "quote": e.quote, "url": e.url} for e in dos.events[:6]]
        # Раунд принимается только если он связан именно с этой позицией: организация уже
        # названа среди её игроков или в источнике, либо в цитате раунда стоит значимое
        # слово термина. Измерено 28.09.2026: без этой проверки 4 раунда из 31 привязались
        # к двум разным позициям — это была общая новость о финансировании, а не
        # доказательство технологии. Ошибка привязки для эксперта хуже пустого поля.
        related = {normalize_org(p["name"]) for p in (cand.get("players_found") or [])}
        related |= {normalize_org(str(o)) for o in (cand.get("organizations") or [])}
        term_words = {w for w in re.split(r"[^0-9A-Za-zА-Яа-яёЁ]+", sig.term.lower())
                      if len(w) > 4}
        kept_rounds = []
        for r in dos.rounds:
            quote_low = r.quote.lower()
            if normalize_org(r.org) in related or any(w in quote_low for w in term_words):
                kept_rounds.append(r)
        dropped = len(dos.rounds) - len(kept_rounds)
        if dropped:
            sig.notes.append(f"отброшено {dropped} сделок без связи с этой позицией")
        cand["rounds"] = [{"org": r.org, "stage": r.stage, "amount": r.amount,
                           "lead": r.lead, "date": r.date, "quote": r.quote, "url": r.url}
                          for r in kept_rounds[:4]]
        own = {d for d in (domain_of(cand.get("source_url", "")),) if d}
        cand["independent_domains"] = sorted(dos.domains | own)
        # В заголовок признаков раунд идёт только если у организации есть роль среди
        # игроков позиции, есть дата и раунд не старше 24 месяцев. Аналитик проверил
        # 16 раундов по открытым источникам: 8 верны, но в заголовке в 4 случаях из 8
        # стоял чужой или семилетний — такое опровергается за минуту на защите, то есть
        # хуже пустого блока. Остальные раунды остаются в карточке, но не в заголовке.
        role_orgs = {normalize_org(p["name"]) for p in (cand.get("players_found") or [])}
        headline = next((r for r in kept_rounds
                         if normalize_org(r.org) in role_orgs and r.date
                         and recent_event(r.date, cutoff)),
                        None)
        if kept_rounds:
            sig.score += 1.0
        if headline is not None:
            sig.notes.append(f"раунд подтверждён: {headline.org} {headline.stage} "
                             f"{headline.amount}"
                             + (f", ведущий {headline.lead}" if headline.lead else "")
                             + f", {headline.date}")
        elif kept_rounds:
            sig.notes.append(f"сделки по теме найдены ({len(kept_rounds)}), но ни одна не "
                             f"привязана к названному реализатору с датой — см. карточку")
        if len(dos.events) >= 2:
            sig.score += 0.5
            sig.notes.append(f"хроника из {len(dos.events)} датированных событий, "
                             f"свежайшее {dos.newest}")
        # Независимость: одна позиция на одном домене — это один голос источника, а не
        # подтверждение. Без второго домена уверенным сигналом позиция не становится.
        if len(cand["independent_domains"]) < 2:
            sig.notes.append("все доказательства с одного домена — независимого "
                             "подтверждения нет")
            if sig.tier == "signal":
                sig.tier = "review"
                sig.verdict = "нужен второй независимый источник"

    scored.sort(key=lambda pair: priority(pair[1].get('_assessment', {}), pair[0].score), reverse=True)
    for sig, cand in scored:
        if cand.get('_assessment', {}).get('stage') != 'early':
            sig.tier = 'review'
            sig.verdict = 'ранняя стадия категории не подтверждена источниками'
    job["players_searched"] = len(top_for_hop)
    # Счётчик считался до поиска компаний и до повышения уровня, поэтому в отчёте
    # стояло «уверенных 4», когда на экране их было шесть. Пересчитываем по факту.
    job["confident"] = sum(1 for sig, _ in scored[:15] if sig.tier == "signal")
    job["needs_review"] = sum(1 for sig, _ in scored[:15] if sig.tier == "review")

    cards = []
    for rank, (sig, cand) in enumerate(scored[:15], 1):
        item = {"rank": rank, "name_ru": cand["name_ru"], "name_en": sig.term,
                "tier": sig.tier, "verdict": sig.verdict,
                "assessment": cand.get('_assessment', {}),
                "mechanism": cand["mechanism"], "score": sig.score, "why": sig.notes,
                "signals": {"первое упоминание": sig.first_seen, "возраст_мес": sig.age_months,
                            "упоминаний всего": sig.total, "за 12 месяцев": sig.recent,
                            "игроков": sig.players, "стадия": sig.stage},
                "evidence": cand.get("evidence"), "source_url": cand.get("source_url"),
                # Организации из источника и канонический термин: без термина в карточке
                # свод дублей по механизму невозможен (замер ML-инженера 28.09.2026).
                "organizations": cand.get("organizations") or [],
                "chronology": cand.get("chronology") or [],
                "rounds": cand.get("rounds") or [],
                "independent_domains": cand.get("independent_domains") or [],
                "players": cand.get("players_found") or []}
        cards.append(to_trend(item, rank - 1, doc_dates))
    job['card_stage_cost'] = {'search': round(getattr(searcher, 'spent_rub', 0.0) - search_cost_before, 4),
                              'llm': round(getattr(llm, 'spent_rub', 0.0), 4)}
    return cards


def worker(job_id: str, request: SearchRequest) -> None:
    job = JOBS[job_id]
    try:
        load_env_file()
        settings = Settings()
        run = cached_run(request.query)
        if run is not None:
            job["stage"] = "найден сохранённый прогон"
            job["cached"] = True
        elif request.demo or DEMO:
            raise RuntimeError("демонстрационный режим: сохранённого прогона по этому запросу нет")
        else:
            # Привратник до расходов. Два поисковых вызова против девяноста рублей прогона.
            if not request.force:
                job["stage"] = "проверка запроса"
                searcher_probe = MultiSearch(YandexSearch(settings, cache_dir=RUNS_DIR / "gate-cache"))
                verdict = assess_query(request.query, searcher_probe)
                job["gate"] = {"status": verdict.status, "message": verdict.message,
                               "direction": verdict.direction,
                               "suggestions": verdict.suggestions,
                               "senses": [{"terms": sn.terms, "titles": sn.titles,
                                           "share": sn.share} for sn in verdict.senses],
                               "hits": verdict.hits, "hosts": verdict.hosts}
                if verdict.status != "ok":
                    job["status"] = "needs_query_fix"
                    job["stage"] = "запрос требует уточнения"
                    job["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    return
            job["stage"] = "поиск и извлечение"
            run = run_pool(known_area(request.query), request.query, "live", settings,
                           plan=request.plan)
        job["run_id"] = run.name
        # Повторный запрос раньше заново собирал карточки: 4–5 минут и платные вызовы
        # модели на уже посчитанном пуле. Для живого показа это плохо — жюри ждёт и
        # каждый повтор стоит денег. Готовые карточки складываем рядом с прогоном.
        cards_file = run / "cards.json"
        if cards_file.exists():
            try:
                saved = json.loads(cards_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                saved = {}
            if saved.get("version") == CARDS_VERSION and isinstance(saved.get("trends"), list):
                job.update({k: v for k, v in saved.items() if k != "version"})
                job["cards_from_cache"] = True
                job["stage"] = "показан сохранённый разбор этого прогона"
                job["funnel"] = saved.get("funnel") or {}
                job["status"] = "completed"
                job["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                return
        # Поисковик для второго хопа создаётся здесь, а не внутри run_pool: по
        # сохранённому прогону конвейер не запускается, а игроков искать всё равно нужно.
        # Кеш кладём в тот же прогон, поэтому повторный запрос не платит за те же запросы.
        searcher = MultiSearch(YandexSearch(settings, cache_dir=run / "search"))
        try:
            job["trends"] = build_cards(run, job, searcher)
        finally:
            searcher.close()
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        counters = manifest.get("counters") or {}
        job["funnel"] = {"queries": counters.get("queries", 0), "hits": counters.get("hits", 0),
                         "urls": counters.get("unique_urls", 0),
                         "documents": counters.get("parsed_ok", 0),
                         "candidates": counters.get("after_merge", 0),
                         "top": len(job["trends"]), "cost": manifest.get("cost_rub", 0)}
        job["plan"] = [n.split(":", 1)[1].strip() for n in counters.get("notes", [])
                       if n.startswith("подсегменты")][:1]
        job["status"] = "completed"
        job["stage"] = "готово"
        job["cards_from_cache"] = False
        # В кеш разбора обязаны попадать все поля, которые показывает интерфейс: без
        # «filters» и «merged_duplicates» повторный запрос показывал пустую сводку фильтров
        # (найдено финальной проверкой 29.09.2026).
        keep = ("trends", "funnel", "confident", "needs_review", "rejected", "rejected_total",
                "out_of_domain_flagged", "baseline", "direction", "players_searched", "plan", "assessment",
                "filters", "merged_duplicates", "accounted", "dossier_errors", "player_errors", "card_stage_cost")
        (run / "cards.json").write_text(json.dumps(
            {"version": CARDS_VERSION, **{k: job[k] for k in keep if k in job}},
            ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # отдаём причину пользователю, а не молчаливый пустой ответ
        job["status"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["trace"] = traceback.format_exc()[-1200:]
    job["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def queued_worker(job_id: str, request: SearchRequest) -> None:
    # One active analysis per service process; duplicate clicks reuse the queued job.
    with _WORK_LOCK:
        worker(job_id, request)


@app.post("/api/search")
def search(request: SearchRequest) -> dict:
    if len(request.query.strip()) < 3:
        raise HTTPException(400, "запрос короче трёх символов")
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        request_key = (request.query.strip().casefold(), request.plan, request.demo, request.force)
        for previous_id, previous in JOBS.items():
            if previous.get('status') == 'running' and previous.get('_request_key') == request_key:
                return {'job_id': previous_id, 'demo': DEMO, 'reused': True}
        JOBS[job_id] = {"id": job_id, "query": request.query, "status": "running",
                        "_request_key": request_key,
                        "stage": "поставлено в очередь", "cached": False,
                        "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    threading.Thread(target=queued_worker, args=(job_id, request), daemon=True).start()
    return {"job_id": job_id, "demo": DEMO}


@app.get("/api/search/{job_id}")
def status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "задание не найдено")
    return job


@app.get("/api/runs")
def runs() -> list[dict]:
    """Сохранённые прогоны: их можно открыть мгновенно и без расходов."""
    out = []
    for run in sorted(RUNS_DIR.glob("2026*"), reverse=True)[:40]:
        manifest = run / "manifest.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append({"run_id": data.get("run_id"), "query": data.get("query"),
                    "area": data.get("area"), "finished": data.get("finished_at"),
                    "cost": data.get("cost_rub")})
    return out


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "demo": DEMO, "runs": len(list(RUNS_DIR.glob("2026*")))}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
