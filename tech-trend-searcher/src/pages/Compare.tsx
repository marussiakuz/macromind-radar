import { useApp } from "../state";
import { Button, Scene } from "../ui";

const rows = [
  { key: "signal", label: "Индекс сигнала", pick: (n: number) => n },
  { key: "year", label: "Первое упоминание", pick: (n: number) => -n },
  { key: "growth", label: "Рост доли", pick: (n: number) => n },
  { key: "hhi", label: "Концентрация HHI", pick: (n: number) => -n },
  { key: "orgs", label: "Организации", pick: (n: number) => n },
] as const;

export function Compare() {
  const { comparedTrends } = useApp();

  if (comparedTrends.length === 0) {
    return (
      <section className="empty card">
        <Scene variant="compare" />
        <h3>Выберите до трёх тем</h3>
        <p className="muted">Отметьте карточки в топ-15 и вернитесь сюда.</p>
        <Button to="/trends">Выбрать из списка</Button>
      </section>
    );
  }

  const values = comparedTrends.map((trend) => ({
    signal: trend.signal,
    year: trend.firstYear,
    growth: trend.features.shareGrowth,
    hhi: trend.features.hhi,
    orgs: trend.features.orgs,
  }));

  return (
    <>
      <p className="tiny">Сравнение</p>
      <h1 style={{ marginTop: 8 }}>Рядом до трёх тем</h1>
      <p className="muted" style={{ marginTop: 12 }}>
        Лучшее значение в строке подсвечено. Это не новый рейтинг, а разбор уже найденного.
      </p>
      <table className="compare-table" style={{ marginTop: 32 }}>
        <thead>
          <tr>
            <th>Признак</th>
            {comparedTrends.map((trend) => (
              <th key={trend.id}>{trend.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const nums = values.map((item) => item[row.key]);
            // Возраст термина может быть неизвестен: сравниваем только измеренные.
            const best = Math.max(...nums.filter((n): n is number => n != null).map(row.pick));
            return (
              <tr key={row.key}>
                <td>{row.label}</td>
                {nums.map((num, index) => (
                  <td
                    key={comparedTrends[index].id}
                    className={num != null && row.pick(num) === best ? "win" : ""}
                  >
                    {/* Неизмеренное показываем как «нет данных», а не как ноль. */}
                    {num == null
                      ? "нет данных"
                      : row.key === "growth" || row.key === "hhi"
                        ? num.toFixed(2)
                        : num}
                  </td>
                ))}
              </tr>
            );
          })}
          <tr>
            <td>Стадия</td>
            {comparedTrends.map((trend) => (
              <td key={trend.id}>{trend.stage}</td>
            ))}
          </tr>
          <tr>
            <td>Кейс</td>
            {comparedTrends.map((trend) => (
              <td key={trend.id}>{trend.claims.find((c) => c.label === "Кейс")?.text}</td>
            ))}
          </tr>
        </tbody>
      </table>
    </>
  );
}
