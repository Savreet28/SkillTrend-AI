import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import About from "./pages/About";
import Decide from "./pages/Decide";
import Forecast from "./pages/Forecast";
import Roles from "./pages/Roles";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Decide />} />
          <Route path="forecast" element={<Forecast />} />
          {/* Old paths kept as redirects so existing links do not 404. */}
          <Route path="skills" element={<Navigate to="/" replace />} />
          <Route path="compare" element={<Navigate to="/" replace />} />
          <Route path="roles" element={<Roles />} />
          <Route path="about" element={<About />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
