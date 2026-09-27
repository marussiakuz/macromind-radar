import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./Layout";
import { Cabinet } from "./pages/Cabinet";
import { Candidates } from "./pages/Candidates";
import { Compare } from "./pages/Compare";
import { Excluded } from "./pages/Excluded";
import { Home } from "./pages/Home";
import { Method } from "./pages/Method";
import { Progress } from "./pages/Progress";
import { Refine } from "./pages/Refine";
import { TrendCard } from "./pages/TrendCard";
import { Trends } from "./pages/Trends";
import { AppProvider } from "./state";

export function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Home />} />
            <Route path="/refine" element={<Refine />} />
            <Route path="/progress" element={<Progress />} />
            <Route path="/trends" element={<Trends />} />
            <Route path="/trends/:id" element={<TrendCard />} />
            <Route path="/excluded" element={<Excluded />} />
            <Route path="/candidates" element={<Candidates />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/method" element={<Method />} />
            <Route path="/cabinet" element={<Cabinet />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  );
}
