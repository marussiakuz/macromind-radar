"""Настройки, лимиты и модели данных конвейера.

Все числовые лимиты — из раздела 3 файла review-sources-pipeline.md.
Менять их можно только вместе с пересчётом бюджета времени и денег.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent  # hackathon/
RUNS_DIR = ROOT / "radar-runs"
EVAL_DIR = ROOT / "radar" / "eval"
FIXTURES_DIR = ROOT / "radar" / "fixtures"
CUSTOMER_XLSX = ROOT / "Документы от заказчика" / "100_слабых_технологических_сигналов_сентябрь_2026.xlsx"

AREAS = [
    "Индустриальный ИИ",
    "Инфраструктура ИИ",
    "Роботы",
    "Финтех",
    "Защита ИИ",
    "Edge",
]


def _env_num(name: str, default, cast=int):
    """Потолок из окружения. Пусто или мусор — остаётся значение по умолчанию."""
    raw = os.getenv(name, "").strip()
    try:
        return cast(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Limits:
    """Потолки одного прогона пула кандидатов."""

    discovery_queries: int = 60        # дерево: каждый лист, затем алиасы и восстановление
    results_per_query: int = 10        # до 240 позиций до дедупликации
    # Измерено 28.09.2026 на снимке 20260927-082453-финтех: поиск дал 300 уникальных URL,
    # а до отбора доходили 64 — то есть 236 адресов не пробовали загрузить вообще. Парный
    # опыт с дозагрузкой поднял покрытие эталона с 5 из 17 до 9 из 17, и все новые
    # совпадения пришли именно из ранее не скачанных документов. Загрузка бесплатна,
    # платит только извлечение, поэтому пределы разведены.
    fetch_attempts: int = 200          # загрузки и платное извлечение ограничены отдельно
    max_per_owner: int = 4             # не больше 4 URL одного владельца
    # Читаем весь скачанный корпус, а единственный отсев — по дате публикации.
    # Порог 2024-01-01 выведен из источников заказчика 29.09.2026: скачаны все 283 ссылки
    # его таблицы, дата нашлась у 115, и это единственная граница, при которой ни одна из
    # 100 строк не теряет все свои датированные источники (при окне в 24 месяца теряются
    # три, включая «NPU внутри батарейных MCU/SoC»).
    # Цена полного чтения: ≈1 ₽ за документ, то есть 150–160 ₽ на область вместо 72.
    # Для показа потолки возвращаются окружением, код править не нужно.
    #   RADAR_EXTRACTION_PACKETS — сколько документов читает модель (≈1 ₽ за документ);
    #   RADAR_MAX_PER_SOURCE     — сколько документов берём с одного обычного сайта;
    #   RADAR_MIN_PUBLISHED      — отсечка по дате публикации, YYYY-MM-DD.
    extraction_packets: int = field(
        default_factory=lambda: _env_num("RADAR_EXTRACTION_PACKETS", 200))
    # Три документа с одного сайта — это один голос, а не три подтверждения. Репозитории
    # (arXiv, DOI, GitHub, OpenAlex) считаются по работам, ограничение бьёт по обычным сайтам.
    max_per_source: int = field(
        default_factory=lambda: _env_num("RADAR_MAX_PER_SOURCE", 999))
    # Документы старше этой даты на извлечение не идут. Пусто — фильтра нет. Документы
    # без даты остаются всегда: дата известна меньше чем у половины корпуса, и отбрасывать
    # их значило бы терять сигналы, а не старьё.
    min_published: str = field(
        default_factory=lambda: os.getenv("RADAR_MIN_PUBLISHED", "2024-01-01").strip())
    fetch_timeout_s: float = 12.0      # на DNS, robots, редиректы и тело
    max_redirects: int = 3
    max_html_bytes: int = 5 * 1024 * 1024
    max_pdf_bytes: int = 15 * 1024 * 1024
    per_origin_delay_s: float = 5.0
    concurrency: int = 8
    run_deadline_s: float = field(
        default_factory=lambda: _env_num("RADAR_RUN_DEADLINE_S", 3600.0, float))


@dataclass(frozen=True)
class Prices:
    """Тарифы из раздела 12 основного отчёта, проверены 17.09.2026."""

    search_call_rub: float = 0.488
    llm_input_rub_per_mtok: float = 200.0
    llm_output_rub_per_mtok: float = 300.0


@dataclass
class Settings:
    """Перед чтением окружения подхватываем .env, если он есть."""

    """Доступы берутся только из окружения. Ключи в файлы прогонов не попадают."""

    yandex_api_key: str | None = field(default_factory=lambda: os.getenv("YANDEX_API_KEY"))
    yandex_folder_id: str | None = field(default_factory=lambda: os.getenv("YANDEX_FOLDER_ID"))
    model_uri_template: str = os.getenv("RADAR_MODEL", "gpt://{folder}/qwen3.6-35b-a3b")
    search_endpoint: str = "https://searchapi.api.cloud.yandex.net/v2/web/search"
    llm_endpoint: str = "https://llm.api.cloud.yandex.net/v1/chat/completions"  # OpenAI-совместимый: Qwen доступна только здесь
    user_agent: str = os.getenv(
        "RADAR_UA", "MacroMindRadar/0.1 (hackathon LCT-2026; contact: team@macromind.local)"
    )
    limits: Limits = field(default_factory=Limits)
    prices: Prices = field(default_factory=Prices)

    @property
    def has_keys(self) -> bool:
        return bool(self.yandex_api_key and self.yandex_folder_id)

    @property
    def model_uri(self) -> str:
        return self.model_uri_template.format(folder=self.yandex_folder_id or "NO_FOLDER")


def load_env_file(path: Path | None = None) -> None:
    """Читает hackathon/.env в окружение. Ключи в коде и артефактах не храним."""
    env = path or (ROOT / ".env")
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- данные конвейера -------------------------------------------------------


class SearchHit(BaseModel):
    """Одна позиция поисковой выдачи. Порядок сохраняем как есть."""

    url: str
    title: str = ""
    snippet: str = ""
    position: int
    query: str
    lang: Literal["ru", "en"]
    lens: str
    retrieved_at: str = Field(default_factory=utcnow)


class FetchResult(BaseModel):
    """Результат попытки получить документ. Ошибка не превращается в пустой успех."""

    url: str
    final_url: str | None = None
    status: Literal[
        "ok", "robots_denied", "robots_unknown", "blocked_address", "too_large",
        "timeout", "http_error", "unsupported_type", "empty",
    ]
    http_status: int | None = None
    content_type: str | None = None
    redirects: list[str] = Field(default_factory=list)
    bytes_sha256: str | None = None
    elapsed_s: float = 0.0
    error: str | None = None
    raw_path: str | None = None


class DocumentSnapshot(BaseModel):
    """Неизменяемый снимок текста. Цитаты проверяются именно по полю text."""

    url: str
    final_url: str
    title: str = ""
    text: str
    text_sha256: str
    lang: str | None = None
    published_at: str | None = None
    # Дата из метаданных PDF. Держится отдельно от `published_at` и НЕ попадает в
    # промпт извлечения: возражение Codex 27.09.2026 верное — это дата вёрстки или
    # пересоздания файла, и проверка диапазона лет её датой публикации не делает.
    # Сохраняем для аудита, для свежести и возраста термина не используем.
    pdf_creation_date: str | None = None
    retrieved_at: str = Field(default_factory=utcnow)
    parser_version: str = "0.1"


class Evidence(BaseModel):
    """Цитата вместе со своим документом.

    Происхождение хранится у каждой цитаты, а не только у кандидата: при склейке
    цитаты второго кандидата переезжают к первому, и без этих полей они начинают
    ссылаться на чужой документ. Проверено 26.09.2026 независимой проверкой — в
    прогонах 091119 и 092118 нашлись цитаты, приписанные не тем страницам.
    """

    quote: str
    start: int | None = None
    end: int | None = None
    source_url: str | None = None
    document_sha256: str | None = None


class Candidate(BaseModel):
    """Технологическая категория, а не компания, продукт или событие."""

    name_ru: str
    name_orig: str | None = None
    mechanism: str
    object_affected: str | None = None
    context: str | None = None
    stage: Literal["research", "prototype", "pilot", "limited_sales", "scaled", "unknown"] = "unknown"
    organizations: list[str] = Field(default_factory=list)
    event_date: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    source_url: str = ""
    document_sha256: str = ""
    merged_sources: list[str] = Field(default_factory=list)  # документы склеенных кандидатов
    origin: Literal["discovery", "hypothesis"] = "discovery"
    """Откуда взялся кандидат. discovery — извлечён из найденного документа.
    hypothesis — предложен моделью из своих знаний и затем подтверждён документом.
    Эти два пути нельзя складывать в одну метрику покрытия без указания долей:
    модель, знающая рынок, частично воспроизводит ответ по памяти, и высокое
    покрытие по пути гипотез не доказывает способность системы находить новое."""


class ExtractionResult(BaseModel):
    candidates: list[Candidate] = Field(default_factory=list)
    no_technology_reason: str | None = None
    model: str = ""
    prompt_version: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    has_more_candidates: bool = False
    diagnostics: list[dict] = Field(default_factory=list)
    span_ids: list[str] = Field(default_factory=list)


class RunManifest(BaseModel):
    """Всё, что нужно, чтобы повторить прогон и понять, что именно измерено."""

    run_id: str
    area: str
    query: str
    mode: Literal["live", "fixtures", "dry", "hypotheses"]
    pool_signature: str = ""
    plan: str = ""
    execution_complete: bool = False  # Planned bounded work finished, not full domain recall.
    started_at: str = Field(default_factory=utcnow)
    finished_at: str | None = None
    cutoff: str = ""
    model: str = ""
    prompt_version: str = ""
    reference_sha256: str = ""
    limits: dict = Field(default_factory=dict)
    counters: dict = Field(default_factory=dict)
    cost_rub: float = 0.0
