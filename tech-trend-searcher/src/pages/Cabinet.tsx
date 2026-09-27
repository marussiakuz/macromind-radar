import { useNavigate } from "react-router-dom";
import { useApp } from "../state";
import { Button, Scene, TrendLine } from "../ui";

export function Cabinet() {
  const { signedIn, signIn, shortlistedTrends, savedQueries, setQuery, notes } = useApp();
  const navigate = useNavigate();

  if (!signedIn) {
    return (
      <section className="empty card">
        <Scene variant="cabinet" />
        <h3>Кабинет после входа</h3>
        <p className="muted">Сохранённые запросы, шорт-лист и выгрузка отчёта.</p>
        <Button onClick={signIn}>Войти</Button>
      </section>
    );
  }

  return (
    <>
      <p className="tiny">Кабинет · шорт-лист и выгрузка</p>
      <div className="section-head">
        <h1>Кабинет</h1>
        <div className="actions">
          <Button kind="dark" small onClick={() => window.print()}>
            Печатный отчёт
          </Button>
        </div>
      </div>

      <section className="section" style={{ marginTop: 40 }}>
        <h3>Сохранённые запросы</h3>
        <div className="chips" style={{ marginTop: 16 }}>
          {savedQueries.map((item) => (
            <button
              key={item}
              className="chip"
              onClick={() => {
                setQuery(item);
                navigate("/trends");
              }}
            >
              {item}
            </button>
          ))}
        </div>
      </section>

      <section className="section">
        <h3>Шорт-лист</h3>
        {shortlistedTrends.length === 0 ? (
          <article className="empty card" style={{ marginTop: 16 }}>
            <Scene variant="cabinet" />
            <p className="muted">Пока пусто. Найдите первый тренд и добавьте заметку.</p>
            <Button to="/">Найти первый тренд</Button>
          </article>
        ) : (
          <div className="method-list" style={{ marginTop: 16 }}>
            {shortlistedTrends.map((trend, index) => (
              <div key={trend.id}>
                <TrendLine trend={trend} index={index} />
                {notes[trend.id] && (
                  <p className="tiny" style={{ margin: "8px 0 0 104px" }}>
                    Почему рассмотреть: {notes[trend.id]}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
