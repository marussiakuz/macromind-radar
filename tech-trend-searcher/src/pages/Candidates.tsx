import { Link } from "react-router-dom";
import { allTrends, excludedItems, searchStats, thresholdRejects } from "../data";
import { Button } from "../ui";

export function Candidates() {
  return (
    <>
      <p className="tiny">
        <Link to="/trends">Выдача</Link> · все кандидаты
      </p>
      <h1 style={{ marginTop: 8 }}>{searchStats.candidates} кандидатов</h1>
      <p className="muted" style={{ marginTop: 12 }}>
        Сначала отбор, потом топ-15. Ниже — что прошло порог, что отсечено и что не дотянуло.
      </p>

      <h3 style={{ marginTop: 32 }}>В топ-15</h3>
      <div className="method-list" style={{ marginTop: 12 }}>
        {allTrends.map((trend, index) => (
          <p key={trend.id}>
            {String(index + 1).padStart(2, "0")}.{" "}
            <Link to={`/trends/${trend.id}`}>{trend.name}</Link>
            <span className="tiny"> · {trend.signal}%</span>
          </p>
        ))}
      </div>

      <h3 style={{ marginTop: 32 }}>Исключены как зрелое, хайп или шум</h3>
      <div className="method-list" style={{ marginTop: 12 }}>
        {excludedItems.map((item) => (
          <p key={item.name} className="tiny">
            {item.name} — {item.reason}
          </p>
        ))}
      </div>

      <h3 style={{ marginTop: 32 }}>Не прошли порог допустимости</h3>
      <div className="method-list" style={{ marginTop: 12 }}>
        {thresholdRejects.map((item) => (
          <p key={item} className="tiny">
            {item}
          </p>
        ))}
      </div>

      <div className="actions" style={{ marginTop: 24 }}>
        <Button to="/trends">К топ-15</Button>
      </div>
    </>
  );
}
