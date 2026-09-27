import { Link, useParams } from "react-router-dom";
import { sourceById, trendById, trendTrust } from "../data";
import { useApp } from "../state";
import { Button, Sparkline, statusBadge, trustBadge } from "../ui";

function yearsWord(n?: number | null) {
  if (n == null) return "";
  const n10 = n % 10;
  const n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return "год";
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return "года";
  return "лет";
}

const featureRows = [
  ["Рост доли", "главный предиктор раннего сигнала", (n: number) => n.toFixed(2)],
  ["Новизна", "max(0; 1 − возраст / 10)", (n: number) => n.toFixed(2)],
  ["Организации", "независимые аффилиации", (n: number) => String(n)],
  ["HHI", "концентрация, чем ниже — тем лучше", (n: number) => n.toFixed(2)],
  ["n_T", "работы в год решения", (n: number) => String(n)],
] as const;

export function TrendCard() {
  const { id = "" } = useParams();
  const trend = trendById(id);
  const { query } = useApp();

  if (!trend) {
    return (
      <section className="empty card">
        <h3>Тема не найдена</h3>
        <Button to="/trends">К выдаче</Button>
      </section>
    );
  }

  const problem = trend.claims.find((item) => item.label === "Проблема");
  const advantage = trend.claims.find((item) => item.label === "Преимущество");
  const usecase = trend.claims.find((item) => item.label === "Кейс");
  const values = [
    trend.features.shareGrowth,
    trend.features.novelty,
    trend.features.orgs,
    trend.features.hhi,
    trend.features.nT,
  ];

  return (
    <article className="report">
      <p className="tiny">
        <Link to="/trends">Выдача</Link> · отчёт по сигналу
      </p>
      <header className="report-head">
        <p className="tiny">Запрос: «{query}»</p>
        <h1 style={{ marginTop: 8 }}>{trend.name}</h1>
        <p className="muted" style={{ marginTop: 12 }}>
          {trend.definition}
        </p>
        <div className="badge-row" style={{ marginTop: 16 }}>
          {trustBadge(trendTrust(trend))}
        </div>
      </header>

      <section className="report-block">
        <h3>Уверенность модели {trend.signal}%</h3>
        <p className="tiny">
          Вероятность слабого сигнала по модели. Не прогноз рыночного успеха. Ранг среди
          направления: {trend.signal} из 100.
        </p>
        <p style={{ marginTop: 12 }}>
          Такая цифра потому что доля ещё мала, рост устойчивый, возраст{" "}
          {trend.features.age ?? "н/д"} {yearsWord(trend.features.age)}, организаций{" "}
          {trend.features.orgs}, обзорной зрелости нет.
        </p>
        <div style={{ marginTop: 16 }}>
          <Sparkline values={trend.series} />
        </div>
        <p className="tiny" style={{ marginTop: 8 }}>
          Первое найденное упоминание: {trend.firstYear}. Ряд по полным годам.
        </p>
      </section>

      <section className="report-block">
        <h3>Описание технологии</h3>
        <p>{trend.definition}</p>
        {problem && <p style={{ marginTop: 12 }}>{problem.text}</p>}
      </section>

      <section className="report-block">
        <h3>Потенциальное преимущество</h3>
        <p>{advantage?.text}</p>
        {advantage && <div style={{ marginTop: 8 }}>{statusBadge(advantage.status)}</div>}
      </section>

      <section className="report-block">
        <h3>Кейс-пример</h3>
        <p>{usecase?.text}</p>
        {usecase && <div style={{ marginTop: 8 }}>{statusBadge(usecase.status)}</div>}
      </section>

      <section className="report-block">
        <h3>Почему это слабый сигнал</h3>
        <ul className="predictors" style={{ marginTop: 0 }}>
          {trend.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
        <table className="compare-table" style={{ marginTop: 16 }}>
          <tbody>
            {featureRows.map((row, index) => (
              <tr key={row[0]}>
                <td>
                  <strong>{row[0]}</strong>
                  <div className="tiny">{row[1]}</div>
                </td>
                <td>{row[2](values[index])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="report-block">
        <h3>Источники</h3>
        <table className="compare-table">
          <thead>
            <tr>
              <th>Название</th>
              <th>Дата</th>
              <th>Тип</th>
              <th>Язык</th>
              <th>Доверие</th>
            </tr>
          </thead>
          <tbody>
            {trend.sources.map((source) => (
              <tr key={source.id}>
                <td>
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.title}
                  </a>
                  <p className="tiny" style={{ marginTop: 8 }}>
                    {source.summaryRu}
                    {source.generated ? " · сгенерированное резюме" : ""}
                  </p>
                </td>
                <td>{source.date}</td>
                <td>{source.type}</td>
                <td className="lang">{source.language}</td>
                <td>{source.trust}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {trend.claims
        .filter((claim) => claim.status === "supported")
        .map((claim) => {
          const source = sourceById(trend, claim.sourceId);
          if (!source) return null;
          return (
            <section className="report-block" key={claim.label}>
              <h5>{claim.label}: цитата</h5>
              <div className="quote">
                <p>«{source.quote}»</p>
                <p className="tiny" style={{ marginTop: 8 }}>
                  {source.language === "en" ? "Язык оригинала: en" : "Язык оригинала: ru"} ·{" "}
                  <a href={source.url} target="_blank" rel="noreferrer">
                    первоисточник
                  </a>
                </p>
              </div>
            </section>
          );
        })}
    </article>
  );
}
