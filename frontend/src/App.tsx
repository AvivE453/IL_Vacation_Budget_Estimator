import { Route, Routes } from "react-router";

import Layout from "./Layout";
import DataQualityPage from "./pages/DataQualityPage";
import HistoryPage from "./pages/HistoryPage";
import NotFoundPage from "./pages/NotFoundPage";
import SearchPage from "./pages/SearchPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<SearchPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="data-quality" element={<DataQualityPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
