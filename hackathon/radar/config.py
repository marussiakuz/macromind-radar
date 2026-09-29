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
    extraction_packets: int = 72       # пакетов извлечения (отбор по разнообразию)
    fetch_timeout_s: float = 12.0      # на DNS, robots, редиректы и тело
    max_redirects: int = 3
    max_html_bytes: int = 5 * 1024 * 1024
    max_pdf_bytes: int = 15 * 1024 * 1024
    per_origin_delay_s: float = 5.0
    concurrency: int = 8
    run_deadline_s: float = 1200.0


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


class RunManifest(BaseModel):
    """Всё, что нужно, чтобы повторить прогон и понять, что именно измерено."""

    run_id: str
    area: str
    query: str
    mode: Literal["live", "fixtures", "dry", "hypotheses"]
    started_at: str = Field(default_factory=utcnow)
    finished_at: str | None = None
    cutoff: str = ""
    model: str = ""
    prompt_version: str = ""
    reference_sha256: str = ""
    limits: dict = Field(default_factory=dict)
    counters: dict = Field(default_factory=dict)
    cost_rub: float = 0.0
