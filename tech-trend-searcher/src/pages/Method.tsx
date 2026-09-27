import { measurements } from "../data";
import { genFunnel, genPlan } from "../generated";
import { Scene } from "../ui";

/**
 * Страница методологии. Раньше здесь были формула, которой нет в коде, и ретро-проверка
 * с предсказаниями 2018–2020 годов, которых система не делала. Оба блока заменены на то,
 * что действительно реализовано и измерено: заказчик просит обосновать методологию, и
 * расхождение между страницей и кодом обнаружится на первом же вопросе.
 */
export function Method() {
  return (
    <>
      <div className="hero" style={{ alignItems: "start" }}>
        <div>
          <p className="tiny">Методология</p>
          <h1 style={{ marginTop: 8 }}>Как определяется слабый сигнал</h1>
        </div>
        <Scene variant="backtest" />
      </div>

      <div className="grid-2" style={{ marginTop: 32 }}>
        <article className="card">
          <h3>Окно зрелости: две границы, а не порог</h3>
          <p style={{ marginTop: 12 }}>
            Слабый сигнал — то, что уже существует и растёт, но ещё не стало громким.
            Поэтому кандидат отбраковывается с двух сторон.
          </p>
          <p className="tiny" style={{ marginTop: 12 }}>
            <b>Сверху:</b> более 400 упоминаний термина, стадия «масштабировано», термину
            больше четырёх лет. <b>Снизу:</b> нет дословно проверенной цитаты; термин
            автора не извлечён; до двух упоминаний — измерения недостаточно.
          </p>
          <p className="tiny" style={{ marginTop: 12 }}>
            Пороги — исследовательская эвристика, подобранная на текущем пуле, а не
            установленная граница. Это ограничение, а не свойство метода.
          </p>
        </article>

        <article className="card">
          <h3>Что складывается в балл</h3>
          <p className="tiny" style={{ marginTop: 12 }}>
            Молодость термина по дате первого упоминания; доля упоминаний за последние
            двенадцать месяцев; тишина — малое общее число упоминаний; число независимых
            организаций, названных в источниках; стадия из извлечённого описания;
            подтверждение с разных доменов.
          </p>
          <p className="tiny" style={{ marginTop: 12 }}>
            Доля свежих упоминаний не равна росту: у темы, целиком возникшей в этом году и
            уже затухающей, доля тоже стопроцентная. В карточке это названо своим именем.
          </p>
        </article>
      </div>

      <article className="card" style={{ marginTop: 24 }}>
        <h3>Доказательство обязательно</h3>
        <p className="tiny" style={{ marginTop: 12 }}>
          Каждая цитата проверяется на дословное вхождение в текст загруженного документа.
          Не нашлась дословно — кандидат не проходит, даже если по смыслу всё сходится.
          Инструкции внутри загруженных страниц не исполняются: текст документа передаётся
          модели как данные. Канонический термин берётся из цитаты автора и отбрасывается,
          если совпадает с названием компании — иначе в окно зрелости попадает торговое
          имя, а не класс решений.
        </p>
      </article>

      <div className="grid-2" style={{ marginTop: 24 }}>
        <article className="card">
          <h3>Воронка последнего прогона</h3>
          <table className="table" style={{ marginTop: 12 }}>
            <tbody>
              <tr><td>поисковых запросов</td><td>{genFunnel.queries}</td></tr>
              <tr><td>позиций выдачи</td><td>{genFunnel.hits}</td></tr>
              <tr><td>уникальных URL</td><td>{genFunnel.urls}</td></tr>
              <tr><td>разобрано документов</td><td>{genFunnel.documents}</td></tr>
              <tr><td>кандидатов</td><td>{genFunnel.candidates}</td></tr>
              <tr><td>прошло окно зрелости</td><td>{genFunnel.top}</td></tr>
              <tr><td>стоимость прогона</td><td>{genFunnel.cost} ₽</td></tr>
            </tbody>
          </table>
        </article>

        <article className="card">
          <h3>План поиска</h3>
          <p className="tiny" style={{ marginTop: 12 }}>
            Направление разбивается не на сегменты отрасли, а на её нерешённые проблемы:
            у новой категории ещё нет имени, но боль у неё конкретная.
          </p>
          <ul className="tiny" style={{ marginTop: 12, paddingLeft: 18 }}>
            {genPlan.slice(0, 8).map((item) => (
              <li key={item} style={{ marginBottom: 6 }}>{item}</li>
            ))}
          </ul>
        </article>
      </div>

      <article className="card" style={{ marginTop: 24 }}>
        <h3>Что измерено</h3>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr><th>Показатель</th><th>Значение</th><th>Чем получено</th><th>Оговорка</th></tr>
          </thead>
          <tbody>
            {measurements.map((row) => (
              <tr key={row.metric}>
                <td>{row.metric}</td>
                <td><b>{row.value}</b></td>
                <td className="tiny">{row.how}</td>
                <td className="tiny">{row.caveat}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>

      <article className="card" style={{ marginTop: 24 }}>
        <h3>Опора на литературу и границы применимости</h3>
        <p className="tiny" style={{ marginTop: 12 }}>
          Рамка зарождающихся технологий:{" "}
          <a href="https://doi.org/10.1016/j.respol.2015.06.006" target="_blank" rel="noreferrer">
            Rotolo, Hicks, Martin, «What is an emerging technology?», Research Policy, 2015
          </a>{" "}
          — новизна, быстрый рост, когерентность, влияние, неопределённость.
        </p>
        <p className="tiny" style={{ marginTop: 12 }}>
          Число упоминаний измеряется поиском по одному источнику разработчиков на дату
          среза. Оно не оценивает мировой объём рынка и не доказывает раннюю стадию само по
          себе. Источник смещён в сторону англоязычной разработки и слабо покрывает
          исследовательскую стадию. Неуспешные запросы не считаются нулевым результатом:
          у таких кандидатов показывается «не измерено».
        </p>
      </article>
    </>
  );
}
