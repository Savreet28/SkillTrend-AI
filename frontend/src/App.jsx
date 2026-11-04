import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import About from "./pages/About";
import Compare from "./pages/Compare";
import Dashboard from "./pages/Dashboard";
import Forecast from "./pages/Forecast";
import Roles from "./pages/Roles";
import SkillExplorer from "./pages/SkillExplorer";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="skills" element={<SkillExplorer />} />
          <Route path="compare" element={<Compare />} />
          <Route path="forecast" element={<Forecast />} />
          <Route path="roles" element={<Roles />} />
          <Route path="about" element={<About />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
