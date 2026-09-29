import { Link } from "react-router-dom";
import { searchStats } from "../data";
import { useApp } from "../state";
import { Button, TrendLine } from "../ui";

export function Trends() {
  const { liveTrends: allTrends } = useApp();
  const { query, job } = useApp();

  return (
    <>
      <p className="tiny">Открытый поиск · выдача</p>
      <div className="section-head">
        <div>
          <h2>Топ-15 слабых сигналов</h2>
          <p className="muted" style={{ marginTop: 8 }}>
            Запрос: «{query}». Сначала показаны кандидаты с признаками ранней стадии.
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
