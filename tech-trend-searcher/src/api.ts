/**
 * Связь с сервисом радара. Заказчик проверяет решение открытым запросом, поэтому
 * интерфейс обязан запускать настоящий конвейер, а не показывать выгруженный файл.
 *
 * Если сервис не запущен, интерфейс продолжает работать на сохранённой выгрузке и
 * честно об этом сообщает: на защите лучше показать прошлый прогон с пометкой, чем
 * пустой экран.
 */
import type { Trend } from "./data";

const BASE = import.meta.env.VITE_RADAR_API ?? "http://127.0.0.1:8000";

export interface JobState {
  id: string;
  query: string;
  status: "running" | "completed" | "failed";
  stage: string;
  cached: boolean;
  run_id?: string;
  trends?: Trend[];
  funnel?: Record<string, number>;
  plan?: string[];
  error?: string;
}

export async function apiAvailable(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/api/health`, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function startSearch(query: string): Promise<string> {
  const res = await fetch(`${BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, plan: "pains" }),
  });
  if (!res.ok) throw new Error(`сервис ответил ${res.status}`);
  const data = await res.json();
  return data.job_id as string;
}

export async function pollSearch(jobId: string): Promise<JobState> {
  const res = await fetch(`${BASE}/api/search/${jobId}`);
  if (!res.ok) throw new Error(`сервис ответил ${res.status}`);
  return (await res.json()) as JobState;
}
