import { excludedItems } from "../data";
import { useApp } from "../state";
import { Badge, Button } from "../ui";

/**
 * Список отбракованных заказчик прямо назвал плюсом: он показывает, что фильтр работает,
 * а не просто выдаёт первые пятнадцать находок. До 28.09.2026 страница жила на статичной
 * выгрузке и на живом запросе показывала прошлый прогон. Теперь при выполненном прогоне
 * берутся его собственные отказы с причиной, а сохранённые остаются запасным вариантом
 * и честно помечены.
 */
export function Excluded() {
  const { liveRejected, job } = useApp();
  const live = liveRejected.length > 0;

  return (
    <>
      <p className="tiny">{live ? `Прогон по запросу «${job?.query ?? ""}»` : "Сохранённый прогон"}</p>
      <h1 style={{ marginTop: 8 }}>Исключённые как не слабый сигнал</h1>
      <p className="muted" style={{ marginTop: 12, maxWidth: 720 }}>
        {live
          ? `Отбраковано ${job?.rejected_total ?? liveRejected.length} позиций из пула. Ниже — ` +
            `${liveRejected.length} с наибольшим баллом: они ближе всего к порогу, и именно их ` +
            `стоит проверить вручную. Причина указана дословно та, по которой отказал фильтр.`
          : "Зрелые тренды, массовое внедрение, отраслевые стандарты, хайп и шум в топ-15 не входят."}
      </p>

      {live ? (
        <table className="compare-table" style={{ marginTop: 32 }}>
          <thead>
            <tr>
              <th>Позиция</th>
              <th>Причина отказа</th>
              <th>Балл</th>
            </tr>
          </thead>
          <tbody>
            {liveRejected.map((item, index) => (
              <tr key={`${item.name}-${index}`}>
                <td>
                  <strong>{item.name}</strong>
                  {item.term && <div className="tiny">термин: {item.term}</div>}
                  {item.source_url && (
                    <a className="tiny" href={item.source_url} target="_blank" rel="noreferrer">
                      источник
                    </a>
                  )}
                </td>
                <td>
                  <div>{item.reason}</div>
                  {item.notes.length > 0 && (
                    <div className="tiny" style={{ marginTop: 6 }}>{item.notes.join("; ")}</div>
                  )}
                </td>
                <td>{item.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
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
      )}

      <div className="actions" style={{ marginTop: 24 }}>
        <Button to="/trends">К топ-15</Button>
      </div>
    </>
  );
}
