import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../state";
import { pollSearch } from "../api";
import { Button } from "../ui";

/**
 * Ход настоящего прогона. Раньше здесь крутилась анимация с оформительскими числами
 * («12 480 работ»), которая заканчивалась через четыре секунды независимо от того,
 * что происходит. Теперь состояние приходит от сервиса, а прогон занимает минуты.
 */
const STAGES = [
  { key: "поставлено в очередь", title: "Постановка задачи" },
  { key: "поиск и извлечение", title: "План, поиск, загрузка и извлечение" },
  { key: "термины", title: "Канонические термины из цитат" },
  { key: "окно зрелости", title: "Окно зрелости и отбор" },
  { key: "готово", title: "Карточки с доказательствами" },
];

export function Progress() {
  const { query, job, setJob } = useApp();
  const [seconds, setSeconds] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const tick = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    const timer = window.setInterval(async () => {
      try {
        const next = await pollSearch(job.id);
        setJob(next);
        if (next.status !== "running") window.clearInterval(timer);
      } catch {
        /* сервис мог перезапуститься: продолжаем опрашивать */
      }
    }, 2000);
    return () => {
      window.clearInterval(timer);
      window.clearInterval(tick);
    };
  }, [job?.id, job?.status, setJob]);

  const stageIndex = Math.max(0, STAGES.findIndex((s) => s.key === job?.stage));
  const done = job?.status === "completed";
  const failed = job?.status === "failed";

  return (
    <>
      <p className="tiny">Прогресс задачи</p>
      <h1 style={{ marginTop: 8 }}>{job?.query ?? query}</h1>
      <p className="muted" style={{ marginTop: 12 }}>
        {/* Три разных состояния, а не два. Прежняя надпись обещала «без новых расходов»
            и для случая, когда из сохранённого брался только пул документов, а оценка и
            поиск компаний считались заново: это 4–5 минут и платные вызовы модели. */}
        {job?.cards_from_cache
          ? "Показан сохранённый разбор этого прогона: ничего не пересчитывалось и не потрачено."
          : job?.cached
          ? "Найден сохранённый пул документов: поиск не повторяется, оценка и поиск компаний считаются заново, обычно 4–5 минут."
          : "Идёт живой прогон по открытым источникам. Обычно 5–12 минут."}
        {" "}Прошло {Math.floor(seconds / 60)} мин {seconds % 60} с.
      </p>

      {/* Ответ привратника. Показывается до траты денег: на запросе «Edge» 14 страниц из 17
          оказались про скачивание браузера, и без этого экрана конвейер пятнадцать минут
          искал бы технологии в карточках товара. Решение остаётся за аналитиком. */}
      {job?.status === "needs_query_fix" && job.gate && (
        <section className="report-block" style={{ marginTop: 16 }}>
          <h3>Запрос стоит уточнить</h3>
          <p>{job.gate.message}</p>
          {job.gate.senses.length > 1 && (
            <table className="compare-table" style={{ marginTop: 12 }}>
              <tbody>
                {job.gate.senses.map((sense, i) => (
                  <tr key={i}>
                    <td>
                      <strong>{Math.round(sense.share * 100)}% выдачи</strong>
                      <div className="tiny">{sense.terms.join(", ")}</div>
                    </td>
                    <td className="tiny">{sense.titles.join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {job.gate.suggestions.length > 0 && (
            <p className="tiny" style={{ marginTop: 12 }}>
              Попробуйте: {job.gate.suggestions.map((s) => `«${s}»`).join(", ")}
            </p>
          )}
          <p className="tiny" style={{ marginTop: 12 }}>
            Проверено {job.gate.hits} страниц с {job.gate.hosts} сайтов. Полный прогон стоит
            около 90 ₽ и пятнадцать минут, поэтому мы спросили заранее.
          </p>
          <div className="actions" style={{ marginTop: 16 }}>
            <Button to="/">Изменить запрос</Button>
          </div>
        </section>
      )}

      {!job && (
        <p className="err" style={{ marginTop: 16 }}>
          Задание не запущено. Вернитесь на главную и введите запрос.
        </p>
      )}

      {failed && (
        <article className="card" style={{ marginTop: 16 }}>
          <h5>Прогон не выполнен</h5>
          <p className="tiny" style={{ marginTop: 8 }}>{job?.error}</p>
        </article>
      )}

      <div className="progress-list" style={{ marginTop: 32 }}>
        {STAGES.map((step, index) => {
          const active = done || index <= stageIndex;
          const current = !done && index === stageIndex && job?.status === "running";
          return (
            <article key={step.key} className="card progress-item">
              <div>
                <h5>{step.title}</h5>
                <p className="tiny" style={{ marginTop: 6 }}>
                  {done ? "выполнено" : current ? "выполняется" : active ? "выполнено" : "ожидает"}
                </p>
              </div>
              <div className="bar">
                <span style={{ width: active ? "100%" : current ? "55%" : "12%" }} />
              </div>
            </article>
          );
        })}
      </div>

      {done && job?.funnel && (
        <article className="card" style={{ marginTop: 24 }}>
          <h5>Воронка этого прогона</h5>
          <p className="tiny" style={{ marginTop: 8 }}>
            {job.funnel.queries} запросов → {job.funnel.hits} позиций выдачи →{" "}
            {job.funnel.documents} документов → {job.funnel.candidates} кандидатов →{" "}
            {job.funnel.top} карточек в выдаче. Поисковый этап: {job.funnel.cost ?? "—"} ₽.
          </p>
        </article>
      )}

      <div className="actions" style={{ marginTop: 24 }}>
        <Button onClick={() => navigate("/trends")} disabled={!done}>
          {done ? `Открыть выдачу (${job?.trends?.length ?? 0})` : "Открыть выдачу"}
        </Button>
        <Button kind="quiet" onClick={() => navigate("/")}>
          Вернуться к поиску
        </Button>
      </div>
    </>
  );
}
