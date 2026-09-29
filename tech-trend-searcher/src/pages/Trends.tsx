import { Link } from "react-router-dom";
import { searchStats, savedQuery } from "../data";
import { useApp } from "../state";
import { Button, TrendLine } from "../ui";

export function Trends() {
  const { liveTrends: allTrends } = useApp();
  const { job } = useApp();

  return (
    <>
      <p className="tiny">Открытый поиск · выдача</p>
      {(job?.demo || !job || job.status !== "completed") && (
        <p className="notice">Сохранённый пример от 29 сентября 2026 года.
          Это результат предыдущего запуска; источники и выводы требуют проверки.</p>
      )}
      <div className="section-head">
        <div>
          <h2>Топ-15 слабых сигналов</h2>
          <p className="muted" style={{ marginTop: 8 }}>
            Запрос: «{job?.status === "completed" ? job.query : savedQuery}». Сначала показаны кандидаты с признаками ранней стадии.
            Неподтверждённые выводы отмечены для проверки аналитиком.
          </p>
        </div>
        <div className="actions">
          <Button kind="quiet" small to="/excluded">
            Исключённые
          </Button>
        </div>
      </div>

      <div className="stats">
        <article className="card stat">
          <div className="stat-num">{job?.funnel?.candidates ?? searchStats.candidates}</div>
          <p className="tiny" style={{ marginTop: 8 }}>
            <Link to="/candidates">кандидатов на слабый сигнал</Link>
          </p>
        </article>
        <article className="card stat">
          <div className="stat-num">{(job?.funnel?.documents ?? searchStats.sources).toLocaleString("ru-RU")}</div>
          <p className="tiny" style={{ marginTop: 8 }}>
            обработанных источников
          </p>
        </article>
        <article className="card stat">
          <div className="stat-num">
            {allTrends.filter((item) => item.tier === "signal").length}
          </div>
          <p className="tiny" style={{ marginTop: 8 }}>
            позиций, где признаки сходятся; остальные требуют проверки экспертом
          </p>
        </article>
      </div>

      <div className="method-list">
        {allTrends.map((trend, index) => (
          <TrendLine key={trend.id} trend={trend} index={index} />
        ))}
      </div>
    </>
  );
}
