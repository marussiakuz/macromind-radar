import { excludedItems } from "../data";
import { Badge, Button } from "../ui";

export function Excluded() {
  return (
    <>
      <p className="tiny">Демонстрация фильтра</p>
      <h1 style={{ marginTop: 8 }}>Исключённые как не слабый сигнал</h1>
      <p className="muted" style={{ marginTop: 12, maxWidth: 720 }}>
        Зрелые тренды, массовое внедрение, отраслевые стандарты, хайп и шум в топ-15 не входят.
      </p>
      <div className="method-list" style={{ marginTop: 32 }}>
        {excludedItems.map((item) => (
          <article key={item.name} className="card">
            <div className="badge-row">
              {item.kind === "зрелое" && <Badge tone="warn">зрелое</Badge>}
              {item.kind === "хайп" && <Badge tone="bad">хайп</Badge>}
              {item.kind === "шум" && <Badge tone="bad">шум</Badge>}
            </div>
            <h4 style={{ marginTop: 12 }}>{item.name}</h4>
            <p className="tiny" style={{ marginTop: 8 }}>
              {item.reason}
            </p>
          </article>
        ))}
      </div>
      <div className="actions" style={{ marginTop: 24 }}>
        <Button to="/trends">К топ-15</Button>
      </div>
    </>
  );
}
