import { NavLink, Outlet } from "react-router-dom";
import { useApp } from "./state";
import { Button } from "./ui";

export function Layout() {
  const { theme, toggleTheme } = useApp();

  return (
    <div className="shell">
      <header className="header">
        <NavLink className="brand" to="/">
          <span className="mark" aria-hidden>
            <svg width="16" height="16" viewBox="0 0 16 16">
              <circle cx="5" cy="8" r="2" fill="#fff" />
              <circle cx="11" cy="5" r="2" fill="#fff" />
              <circle cx="11" cy="11" r="2" fill="#fff" />
              <path d="M6.6 7.2 L9.4 5.7 M6.6 8.8 L9.4 10.3" stroke="#fff" strokeWidth="1.4" />
            </svg>
          </span>
          TechTrendSearcher
        </NavLink>
        <nav className="nav">
          <NavLink to="/" end>
            Поиск
          </NavLink>
          <NavLink to="/trends">Выдача</NavLink>
          <NavLink to="/excluded">Исключённые</NavLink>
          <NavLink to="/method">Методология</NavLink>
        </nav>
        <div className="header-actions">
          <Button kind="quiet" small onClick={toggleTheme}>
            {theme === "light" ? "Тёмная" : "Светлая"}
          </Button>
        </div>
      </header>
      <main className="main">
        <Outlet />
      </main>
      <footer className="footer">
        TechTrendSearcher · открытый поиск слабых сигналов.
      </footer>
    </div>
  );
}
