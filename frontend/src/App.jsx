import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./api/useAuth";
import Header from "./components/layout/Header";
import ProtectedRoute from "./components/auth/ProtectedRoute";
import MapPage from "./pages/MapPage";
import DatabasePage from "./pages/DatabasePage";
import IncidentPage from "./pages/IncidentPage";
import StatsPage from "./pages/StatsPage";
import LoginPage from "./pages/LoginPage";
import SubmitPage from "./pages/SubmitPage";
import AboutPage from "./pages/AboutPage";
import AdminPage from "./pages/AdminPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="h-screen flex flex-col bg-gray-900">
          <Header />
          <Routes>
            <Route path="/" element={<MapPage />} />
            <Route path="/database" element={<DatabasePage />} />
            <Route path="/incidents/:id" element={<IncidentPage />} />
            <Route path="/stats" element={<StatsPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/submit"
              element={
                <ProtectedRoute>
                  <SubmitPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin"
              element={
                <ProtectedRoute requiredRole="admin">
                  <AdminPage />
                </ProtectedRoute>
              }
            />
          </Routes>
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}
