import { Routes, Route, Navigate } from "react-router-dom";

import Layout from "./components/Layout";
import DashboardPage from "./pages/Dashboard";
import ModelsPage from "./pages/Models";
import TrainingPage from "./pages/Training";
import HpSearchPage from "./pages/HpSearch";
import ComboSearchPage from "./pages/ComboSearch";
import ScrapingPage from "./pages/Scraping";
import PredictionsPage from "./pages/Predictions";
import FightersPage from "./pages/Fighters";
import ComparePage from "./pages/Compare";
import PublishPage from "./pages/Publish";
import RecalculationPage from "./pages/Recalculation";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/hp-search" element={<HpSearchPage />} />
        <Route path="/combo-search" element={<ComboSearchPage />} />
        <Route path="/scraping" element={<ScrapingPage />} />
        <Route path="/predictions" element={<PredictionsPage />} />
        <Route path="/fighters" element={<FightersPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/publish" element={<PublishPage />} />
        <Route path="/recalculation" element={<RecalculationPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
