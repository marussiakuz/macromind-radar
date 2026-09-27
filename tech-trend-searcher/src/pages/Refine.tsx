import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { topicGroups } from "../data";
import { useApp } from "../state";
import { Button } from "../ui";

export function Refine() {
  const { query, selectedTopics, setSelectedTopics } = useApp();
  const navigate = useNavigate();

  useEffect(() => {
    if (selectedTopics.length === 0) {
      setSelectedTopics(topicGroups.map((item) => item.id));
    }
  }, [selectedTopics.length, setSelectedTopics]);

  function toggle(id: string) {
    setSelectedTopics(
      selectedTopics.includes(id)
        ? selectedTopics.filter((item) => item !== id)
        : [...selectedTopics, id]
    );
  }

  return (
    <>
      <p className="tiny">Уточнение направления</p>
      <h1 style={{ marginTop: 8 }}>{query}</h1>
      <p className="muted" style={{ marginTop: 12, maxWidth: 720 }}>
        Подтвердите 5–8 групп подтем. Неотмеченные фразы не пойдут в сбор корпуса.
      </p>

      <div className="topics" style={{ marginTop: 32 }}>
        {topicGroups.map((group) => (
          <label key={group.id} className="card topic">
            <input
              className="check"
              type="checkbox"
              checked={selectedTopics.includes(group.id)}
              onChange={() => toggle(group.id)}
            />
            <div>
              <h5>{group.title}</h5>
              <p className="tiny" style={{ marginTop: 8 }}>
                {group.phrases.join(" · ")}
              </p>
            </div>
          </label>
        ))}
      </div>

      <div className="actions" style={{ marginTop: 24 }}>
        <Button
          onClick={() => navigate("/progress")}
          disabled={selectedTopics.length < 5 || selectedTopics.length > 8}
        >
          Подтвердить границы
        </Button>
        <Button kind="quiet" onClick={() => navigate("/")}>
          Назад
        </Button>
      </div>
      {(selectedTopics.length < 5 || selectedTopics.length > 8) && (
        <p className="err">Нужно отметить от 5 до 8 групп.</p>
      )}
    </>
  );
}
