import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { allTrends, savedQuery, type Trend } from "./data";
import type { JobState, RejectedItem } from "./api";

type Theme = "light" | "dark";

interface AppState {
  theme: Theme;
  toggleTheme: () => void;
  signedIn: boolean;
  signIn: () => void;
  signOut: () => void;
  query: string;
  setQuery: (value: string) => void;
  selectedTopics: string[];
  setSelectedTopics: (ids: string[]) => void;
  compareIds: string[];
  toggleCompare: (id: string) => void;
  shortlist: string[];
  notes: Record<string, string>;
  toggleShortlist: (id: string) => void;
  setNote: (id: string, note: string) => void;
  savedQueries: string[];
  saveQuery: (value: string) => void;
  comparedTrends: Trend[];
  shortlistedTrends: Trend[];
  job: JobState | null;
  setJob: (job: JobState | null) => void;
  liveTrends: Trend[];
  /** Отказы текущего прогона; пусто — значит показываем сохранённые. */
  liveRejected: RejectedItem[];
}

const Ctx = createContext<AppState | null>(null);

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("tts-theme");
    return saved === "dark" ? "dark" : "light";
  });
  const [signedIn, setSignedIn] = useState(() => localStorage.getItem("tts-auth") === "1");
  const [query, setQuery] = useState(() => localStorage.getItem("tts-query") || savedQuery);
  const [selectedTopics, setSelectedTopics] = useState<string[]>([]);
  const [compareIds, setCompareIds] = useState<string[]>(() => readJson("tts-compare", []));
  const [shortlist, setShortlist] = useState<string[]>(() => readJson("tts-short", []));
  const [notes, setNotes] = useState<Record<string, string>>(() => readJson("tts-notes", {}));
  const [savedQueries, setSavedQueries] = useState<string[]>(() =>
    readJson("tts-queries", [savedQuery])
  );
  // Результат живого прогона. Пока его нет, интерфейс показывает сохранённую выгрузку
  // и помечает это, чтобы никто не принял прошлый прогон за ответ на свой запрос.
  const [job, setJob] = useState<JobState | null>(null);
  const liveTrends = job?.status === "completed" ? job.trends ?? [] : allTrends;
  const liveRejected = job?.status === "completed" ? job.rejected ?? [] : [];

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("tts-theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("tts-query", query);
  }, [query]);

  useEffect(() => {
    localStorage.setItem("tts-auth", signedIn ? "1" : "0");
  }, [signedIn]);

  useEffect(() => {
    localStorage.setItem("tts-compare", JSON.stringify(compareIds));
  }, [compareIds]);

  useEffect(() => {
    localStorage.setItem("tts-short", JSON.stringify(shortlist));
  }, [shortlist]);

  useEffect(() => {
    localStorage.setItem("tts-notes", JSON.stringify(notes));
  }, [notes]);

  useEffect(() => {
    localStorage.setItem("tts-queries", JSON.stringify(savedQueries));
  }, [savedQueries]);

  const value = useMemo<AppState>(
    () => ({
      theme,
      toggleTheme: () => setTheme((t) => (t === "light" ? "dark" : "light")),
      signedIn,
      signIn: () => setSignedIn(true),
      signOut: () => setSignedIn(false),
      query,
      setQuery,
      selectedTopics,
      setSelectedTopics,
      compareIds,
      toggleCompare: (id) =>
        setCompareIds((current) => {
          if (current.includes(id)) return current.filter((item) => item !== id);
          if (current.length >= 3) return current;
          return [...current, id];
        }),
      shortlist,
      notes,
      toggleShortlist: (id) =>
        setShortlist((current) =>
          current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
        ),
      setNote: (id, note) => setNotes((current) => ({ ...current, [id]: note })),
      savedQueries,
      saveQuery: (value) =>
        setSavedQueries((current) => (current.includes(value) ? current : [value, ...current])),
      job,
      setJob,
      liveTrends,
      liveRejected,
      comparedTrends: compareIds
        .map((id) => liveTrends.find((item) => item.id === id))
        .filter((item): item is Trend => Boolean(item)),
      shortlistedTrends: shortlist
        .map((id) => liveTrends.find((item) => item.id === id))
        .filter((item): item is Trend => Boolean(item)),
    }),
    [theme, signedIn, query, selectedTopics, compareIds, shortlist, notes, savedQueries, job, liveTrends, liveRejected]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp outside provider");
  return ctx;
}
