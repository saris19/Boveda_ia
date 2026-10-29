import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import { useAuth } from "./context/AuthContext";
import AlertsPage from "./pages/AlertsPage";
import AnalyzePage from "./pages/AnalyzePage";
import AuditPage from "./pages/AuditPage";
import DashboardPage from "./pages/DashboardPage";
import DocumentsPage from "./pages/DocumentsPage";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import SearchPage from "./pages/SearchPage";
import SecurityCenterPage from "./pages/SecurityCenterPage";
import TrashPage from "./pages/TrashPage";
import UsersPage from "./pages/UsersPage";

function RequireAuth({ children }) {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) {
    return <div className="empty" style={{ minHeight: "100vh", justifyContent: "center" }}><Spinner label="Verificando sesión…" /></div>;
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return children;
}

function RequireAdmin({ children }) {
  const { isAdmin } = useAuth();
  return isAdmin ? children : <NotFoundPage />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Navigate to="/panel" replace />} />
        <Route path="/panel" element={<DashboardPage />} />
        <Route path="/documentos" element={<DocumentsPage />} />
        <Route path="/buscar" element={<SearchPage />} />
        <Route path="/analizar" element={<AnalyzePage />} />
        <Route path="/papelera" element={<TrashPage />} />
        <Route path="/alertas" element={<RequireAdmin><AlertsPage /></RequireAdmin>} />
        <Route path="/seguridad" element={<RequireAdmin><SecurityCenterPage /></RequireAdmin>} />
        <Route path="/usuarios" element={<RequireAdmin><UsersPage /></RequireAdmin>} />
        <Route path="/bitacora" element={<RequireAdmin><AuditPage /></RequireAdmin>} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
