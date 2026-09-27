import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../state";
import { apiAvailable, startSearch } from "../api";
import { Button, Scene } from "../ui";

const chips = [
  "технологии в ИИ",
  "перспективные решения в финтехе",
  "слабые сигналы в области кибербезопасности",
];

export function Home() {
  const { query, setQuery, saveQuery, setJob } = useApp();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function start(value = query) {
    const next = value.trim();
    if (next.length < 3) {
      setError("Введите направление, не короче трёх символов.");
      return;
    }
    setError("");
    setQuery(next);
    saveQuery(next);
    setBusy(true);
    // Прогон настоящий: заказчик проверяет систему открытым запросом, поэтому показывать
    // сохранённый результат под чужой запрос нельзя.
    if (!(await apiAvailable())) {
      setBusy(false);
      setError(
        "Сервис радара не запущен. Включите его командой " +
          "«.venv/bin/python -m radar.server» в каталоге hackathon — без него показывается " +
          "только последний сохранённый прогон."
      );
      return;
    }
    try {
      const jobId = await startSearch(next);
      setJob({ id: jobId, query: next, status: "running", stage: "поставлено в очередь", cached: false });
      navigate("/progress");
    } catch (e) {
      setError(`Не удалось запустить поиск: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <h1>Слабые сигналы по направлению</h1>
          <p className="tiny">Введите запрос в свободной форме.</p>
          <div className="search-row">
            <input
              className="field"
              value={query}
              placeholder="технологии в ИИ"
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && start()}
            />
            <Button onClick={() => void start()} disabled={busy}>
              {busy ? "Запускаю…" : "Найти сигналы"}
            </Button>
          </div>
          {error && <p className="err">{error}</p>}
          <div className="chips">
            {chips.map((item) => (
              <button key={item} className="chip" onClick={() => void start(item)}>
                {item}
              </button>
            ))}
          </div>
        </div>
        <Scene variant="search" />
      </section>

      <section className="section">
        <div className="grid-3">
          <article className="card">
            <h5>Уверенность модели</h5>
            <p className="tiny" style={{ marginTop: 8 }}>
              В топе — оценка слабого сигнала в процентах и вклад признаков.
            </p>
          </article>
          <article className="card">
            <h5>Зрелое отсекается</h5>
            <p className="tiny" style={{ marginTop: 8 }}>
              Массовые технологии, стандарты и хайп не входят в топ-15.
            </p>
          </article>
          <article className="card">
            <h5>Источники с доверием</h5>
            <p className="tiny" style={{ marginTop: 8 }}>
              У каждой ссылки есть тип, язык, дата и уровень доверия.
            </p>
          </article>
        </div>
      </section>
    </>
  );
}
