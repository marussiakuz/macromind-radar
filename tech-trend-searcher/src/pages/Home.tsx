import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../state";
import { savedQuery } from "../data";
import { apiAvailable, fetchLimits, startSearch, type Limits } from "../api";
import { Button, Scene } from "../ui";

const chips = [
  "Edge",
  "Роботы",
  "Защита ИИ",
  "Финтех",
  "Индустриальный ИИ",
];

export function Home() {
  const { query, setQuery, saveQuery, setJob } = useApp();
  const [error, setError] = useState("");
  // Демонстрационная выгрузка без сервиса: об этом говорим прямо, чтобы сохранённый
  // прогон не приняли за ответ на введённый запрос.
  const [offline, setOffline] = useState(false);
  // Остаток бюджета и квоты публичного сервиса. Аналитик видит их до запуска: живой
  // прогон стоит денег, и отказ после десяти минут ожидания хуже отказа сразу.
  const [limits, setLimits] = useState<Limits | null>(null);

  useEffect(() => {
    void fetchLimits().then(setLimits);
  }, []);
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
      setOffline(true);
      setError("");
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
          {limits && limits.budget.known && (
            <p className="tiny">
              {(limits.budget.runs_left ?? 0) > 0 ? (
                <>
                  Живой прогон доступен: сегодня запущено {limits.quota.runs_today} из{" "}
                  {limits.quota.daily_limit}, бюджета хватает ещё на{" "}
                  {limits.budget.runs_left} прогон(ов). Прогон занимает 7–11 минут; повтор
                  уже посчитанного запроса бесплатен и отвечает за секунду.
                </>
              ) : (
                <>
                  Живые прогоны сейчас недоступны: бюджета не хватает на полный прогон
                  (поиск {Math.round(limits.budget.search ?? 0)} ₽, модель{" "}
                  {Math.round(limits.budget.llm ?? 0)} ₽). Сохранённые разборы открыты и
                  бесплатны — направления ниже.
                </>
              )}
              {limits.running > 0 && " Сейчас считается другой запрос: очередь на один анализ."}
            </p>
          )}
          {offline && (
            <div className="notice">
              <p>
                <b>Сервис радара недоступен.</b> Новый запрос «{query}» посчитать нельзя:
                живой прогон обращается к платным поиску и модели. В эту страницу вшит
                сохранённый разбор по запросу «{savedQuery}» — его можно открыть целиком,
                с цитатами, компаниями и списком отбракованного.
              </p>
              <div className="row">
                <Button onClick={() => navigate("/trends")}>Открыть сохранённый разбор</Button>
                <Button kind="quiet" onClick={() => navigate("/method")}>
                  Как это считается
                </Button>
              </div>
              <p className="hint">
                Свой запрос считается на локальной копии: <code>cd hackathon</code> →{" "}
                <code>.venv/bin/python -m radar.server</code>, затем{" "}
                <code>npm run dev</code> в <code>tech-trend-searcher</code>. Опубликованная
                страница к локальному сервису обратиться не может: браузер блокирует
                http-запрос со https-страницы. Инструкция — в README репозитория.
              </p>
            </div>
          )}
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
            <h5>Проверяемые признаки</h5>
            <p className="tiny" style={{ marginTop: 8 }}>
              Карточки содержат цитаты и балл для приоритизации. Реализаторы и даты
              показаны там, где удалось найти подтверждение. Балл не является вероятностью.
            </p>
          </article>
          <article className="card">
            <h5>Исключение по доказательствам</h5>
            <p className="tiny" style={{ marginTop: 8 }}>
              Зрелость и опровержение проверяются отдельно. Непроверенное остаётся
              кандидатом; отсутствие отказа не подтверждает слабость сигнала.
            </p>
          </article>
          <article className="card">
            <h5>Источники с доверием</h5>
            <p className="tiny" style={{ marginTop: 8 }}>
              Можно открыть источник и проверить цитату. Неустановленные даты
              отмечены; доверие к домену само по себе не доказывает утверждение.
            </p>
          </article>
        </div>
      </section>
    </>
  );
}
