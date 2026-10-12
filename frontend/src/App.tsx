import { Route, Routes } from "react-router";

import Layout from "./Layout";
import DataQualityPage from "./pages/DataQualityPage";
import DestinationPage from "./pages/DestinationPage";
import HistoryPage from "./pages/HistoryPage";
import NotFoundPage from "./pages/NotFoundPage";
import SavedSearchPage from "./pages/SavedSearchPage";
import SearchPage from "./pages/SearchPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<SearchPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="history/:searchId" element={<SavedSearchPage />} />
        <Route path="destinations/:destinationId" element={<DestinationPage />} />
        <Route path="data-quality" element={<DataQualityPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
