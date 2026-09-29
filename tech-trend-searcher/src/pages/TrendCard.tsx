import { Link, useParams } from "react-router-dom";
import { sourceById, trendById, trendTrust } from "../data";
import { useApp } from "../state";
import { Button, Sparkline, statusBadge, trustBadge } from "../ui";

const roleRu: Record<string, string> = {
  developer: "разрабатывает",
  deployer: "внедряет",
  researcher: "исследует",
  funder: "финансирует",
  standard: "стандартизирует",
  // Организация названа прямо в источнике позиции. Роль честно отличается от найденных
  // вторым поиском реализаторов: это упоминание, а не проверенное внедрение.
  mentioned: "названа в источнике",
};

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
        <h3>
          Баллы окна зрелости: {trend.signal} из {trend.scoreMax ?? 11}
        </h3>
        <p className="tiny">
          Это сумма проверяемых признаков, а не вероятность и не процент. Границы выведены
          из распределения эталонных категорий: медиана упоминаний 3, p90 = 423, медианная
          доля свежих работ 47 %. Каждый признак перечислен ниже.
        </p>
        <p style={{ marginTop: 12 }}>
          Такая цифра потому что доля ещё мала, рост устойчивый, возраст{" "}
          {trend.features.age ?? "н/д"} {yearsWord(trend.features.age ?? undefined)}, организаций{" "}
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

      {/* Заказчик требует кейс-пример по каждой позиции. Отдельного утверждения «Кейс»
          извлекатель формирует не всегда — на замере 28.09 его не было ни на одной из
          пятнадцати карточек, и блок выводился пустым. Кейс здесь и есть дословная
          цитата источника: она показывает, кто и что уже сделал. Плюс найденные
          компании, если второй поиск их нашёл. */}
      <section className="report-block">
        <h3>Кейс-пример</h3>
        {usecase ? (
          <>
            <p>{usecase.text}</p>
            <div style={{ marginTop: 8 }}>{statusBadge(usecase.status)}</div>
          </>
        ) : trend.sources.length > 0 ? (
          <>
            <blockquote style={{ margin: 0, paddingLeft: 12, borderLeft: "3px solid var(--line)" }}>
              «{trend.sources[0].quote}»
            </blockquote>
            <p className="tiny" style={{ marginTop: 8 }}>
              Дословно из источника{" "}
              <a href={trend.sources[0].url} target="_blank" rel="noreferrer">
                {trend.sources[0].title}
              </a>
              {trend.players && trend.players.length > 0
                ? `. Реализуют: ${trend.players.slice(0, 3).map((p) => p.name).join(", ")}.`
                : "."}
            </p>
          </>
        ) : (
          <p className="tiny">Кейс не выделен: у позиции нет проверенной цитаты.</p>
        )}
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

      {/* Эксперт заказчика голосует по каждой позиции и первым спрашивает «кто это делает»:
          в его таблице к каждой строке приложены три-четыре компании. Игроки найдены
          отдельным поиском по каноническому термину, а не взяты из первой статьи, поэтому
          это независимое подтверждение, а не пересказ одного источника. */}
      {trend.players && trend.players.length > 0 && (
        <section className="report-block">
          <h3>Кто это делает ({trend.players.length})</h3>
          <table className="compare-table">
            <tbody>
              {trend.players.map((player) => (
                <tr key={player.name + player.url}>
                  <td>
                    <strong>{player.name}</strong>
                    <div className="tiny">{roleRu[player.role] ?? player.role}</div>
                  </td>
                  <td>
                    <div>{player.what}</div>
                    <div className="tiny" style={{ marginTop: 6 }}>
                      «{player.quote}»
                    </div>
                    <a className="tiny" href={player.url} target="_blank" rel="noreferrer">
                      источник
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Хроника и сделки. Эксперт заказчика отказывал позициям именно за пустоту этих
          полей: без даты он не отличает событие 2026 года от истории 2016-го, а без раунда
          со суммой и ведущим инвестором не видит, что категория формируется сейчас. */}
      {((trend.chronology && trend.chronology.length > 0) ||
        (trend.rounds && trend.rounds.length > 0)) && (
        <section className="report-block">
          <h3>Хроника и сделки</h3>
          {trend.rounds && trend.rounds.length > 0 && (
            <table className="compare-table">
              <tbody>
                {trend.rounds.map((r) => (
                  <tr key={r.org + r.date + r.amount}>
                    <td>
                      <strong>{r.org}</strong>
                      <div className="tiny">
                        {[r.stage, r.date].filter(Boolean).join(" · ") || "дата не указана"}
                      </div>
                    </td>
                    <td>
                      <div>
                        {r.amount}
                        {r.lead ? `, ведущий инвестор ${r.lead}` : ""}
                      </div>
                      <div className="tiny" style={{ marginTop: 6 }}>«{r.quote}»</div>
                      <a className="tiny" href={r.url} target="_blank" rel="noreferrer">
                        источник
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {trend.chronology && trend.chronology.length > 0 && (
            <ul className="predictors" style={{ marginTop: 16 }}>
              {trend.chronology.map((e) => (
                <li key={e.date + e.org + e.what}>
                  <strong>{e.date}</strong> — {e.org}: {e.what}
                  <div className="tiny" style={{ marginTop: 4 }}>
                    «{e.quote}»{" "}
                    <a href={e.url} target="_blank" rel="noreferrer">
                      источник
                    </a>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {trend.independentDomains && (
            <p className="tiny" style={{ marginTop: 12 }}>
              Независимых доменов в доказательствах: {trend.independentDomains.length}
              {trend.independentDomains.length < 2
                ? " — подтверждения со второго источника нет, позиция требует проверки."
                : `: ${trend.independentDomains.join(", ")}.`}
            </p>
          )}
        </section>
      )}

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
