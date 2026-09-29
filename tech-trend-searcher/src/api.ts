/** HTTP-клиент сервиса анализа. */
import type { Trend } from "./data";

// Три случая:
//   «same-origin» — интерфейс раздаётся тем же сервером, что и API (так работает
//     публичный MVP). Обращаемся по относительному пути, поэтому адрес сервиса можно
//     менять — временное имя, потом домен — не пересобирая страницу.
//   заданный адрес — страница лежит отдельно (GitHub Pages) и ходит на сервис по сети.
//   пусто — сборка без переменной: остаётся локальный сервис, и если его нет,
//     страница честно скажет об этом вместо запроса в пустоту.
const RAW_API = import.meta.env.VITE_RADAR_API ?? "";
const BASE = RAW_API === "same-origin" ? "" : RAW_API || "http://127.0.0.1:8000";

export interface RejectedItem {
  name: string;
  term: string;
  reason: string;
  score: number;
  notes: string[];
  source_url: string;
}

export interface GateVerdict {
  /** ok | wrong_sense | ambiguous | no_material */
  status: string;
  message: string;
  direction: string;
  suggestions: string[];
  senses: { terms: string[]; titles: string[]; share: number }[];
  hits: number;
  hosts: number;
}

export interface JobState {
  id: string;
  query: string;
  status: "running" | "completed" | "failed" | "needs_query_fix";
  stage: string;
  cached: boolean;
  /** Разбор запроса до траты денег: пригоден ли он вообще. */
  gate?: GateVerdict;
  /** Разбор показан из сохранённого: повтор не пересчитывался и ничего не стоил. */
  cards_from_cache?: boolean;
  run_id?: string;
  trends?: Trend[];
  /** Отбракованные позиции с причиной: заказчик назвал такой список плюсом. */
  rejected?: RejectedItem[];
  rejected_total?: number;
  direction?: string;
  confident?: number;
  needs_review?: number;
  funnel?: Record<string, number>;
  plan?: string[];
  error?: string;
  timeout_notice?: string;
  demo?: boolean;
}

export async function apiAvailable(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/api/health`, { signal: AbortSignal.timeout(4000) });
    return res.ok;
  } catch {
    return false;
  }
}

/** `force` — аналитик увидел замечание привратника и всё равно решил запускать. */
export async function startSearch(query: string, force = false): Promise<string> {
  const res = await fetch(`${BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json",
      ...(sessionStorage.getItem("radar-token") ? { "x-radar-token": sessionStorage.getItem("radar-token")! } : {}) },
    body: JSON.stringify({ query, plan: "tree", force }),
  });
  if (!res.ok) {
    // Публичный сервис отказывает по делу: исчерпана квота (429) или бюджета не хватает
    // на полный прогон (402). Причина приходит в `detail`, и аналитик обязан её увидеть —
    // «сервис ответил 429» не объясняет ничего.
    let reason = `сервис ответил ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string" && body.detail) reason = body.detail;
    } catch {
      /* тело без JSON: остаётся код ответа */
    }
    throw new Error(reason);
  }
  const data = await res.json();
  return data.job_id as string;
}

/** Остаток бюджета и квоты публичного сервиса: показывается аналитику до запуска. */
export interface Limits {
  demo: boolean;
  budget: { known: boolean; search?: number; llm?: number; runs_left?: number };
  quota: {
    runs_today: number;
    daily_limit: number;
    ip_runs_today: number;
    ip_daily_limit: number;
  };
  running: number;
  token_required: boolean;
}

export async function fetchLimits(): Promise<Limits | null> {
  try {
    const res = await fetch(`${BASE}/api/limits`, { signal: AbortSignal.timeout(2500) });
    if (!res.ok) return null;
    return (await res.json()) as Limits;
  } catch {
    return null;
  }
}

export async function pollSearch(jobId: string): Promise<JobState> {
  const res = await fetch(`${BASE}/api/search/${jobId}`);
  if (!res.ok) throw new Error(`сервис ответил ${res.status}`);
  return (await res.json()) as JobState;
}
