import { BrowserRouter, Routes, Route } from "react-router-dom";
import Header from "./components/layout/Header";
import MapPage from "./pages/MapPage";
import DatabasePage from "./pages/DatabasePage";
import IncidentPage from "./pages/IncidentPage";

function Placeholder({ title }) {
  return (
    <div className="flex-1 flex items-center justify-center bg-gray-900 text-white">
      <div className="text-center">
        <h1 className="text-3xl font-bold mb-2">{title}</h1>
        <p className="text-gray-500">Coming in Phase {title === "Database" ? "3" : title === "Statistics" ? "4" : "—"}</p>
      </div>
    </div>
  );
}

function About() {
  return (
    <div className="flex-1 overflow-y-auto bg-gray-900 text-white p-8 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-4">About OSAF</h1>
      <p className="text-gray-300 mb-4">
        The <strong>Open Shark Attack File</strong> is an open-source, community-driven shark
        attack database — a transparent alternative to the restricted International Shark Attack
        File (ISAF).
      </p>
      <h2 className="text-xl font-semibold mt-6 mb-2">Why OSAF?</h2>
      <ul className="list-disc list-inside text-gray-400 space-y-1">
        <li>All incident data is public — no gatekeeping behind academic access</li>
        <li>Community-driven submissions with verification workflow</li>
        <li>Rapid documentation from verified sources</li>
        <li>Open source codebase and methodology</li>
      </ul>
      <h2 className="text-xl font-semibold mt-6 mb-2">Classification System</h2>
      <p className="text-gray-400 mb-2">
        OSAF uses the same classification methodology as the ISAF, maintained by the Florida
        Museum of Natural History. Classifications describe shark behavior in response to stimuli
        and do not diminish the experiences of victims.
      </p>
      <h2 className="text-xl font-semibold mt-6 mb-2">Disclaimer</h2>
      <p className="text-gray-500 text-sm">
        This project is not affiliated with the International Shark Attack File or the Florida
        Museum of Natural History. It is an independent open-source effort.
      </p>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="h-screen flex flex-col bg-gray-900">
        <Header />
        <Routes>
          <Route path="/" element={<MapPage />} />
          <Route path="/database" element={<DatabasePage />} />
          <Route path="/incidents/:id" element={<IncidentPage />} />
          <Route path="/stats" element={<Placeholder title="Statistics" />} />
          <Route path="/about" element={<About />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
