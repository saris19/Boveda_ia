import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { ROLE_LABELS } from "../utils/format";
import Icon from "./Icon";

const MAIN_NAV = [
  { to: "/panel", label: "Panel", icon: "dashboard" },
  { to: "/documentos", label: "Documentos", icon: "files" },
  { to: "/buscar", label: "Búsqueda inteligente", icon: "search" },
  { to: "/analizar", label: "Analizar con IA", icon: "sparkles" },
  { to: "/papelera", label: "Papelera", icon: "trash", uploaders: true },
];
const ADMIN_NAV = [
  { to: "/alertas", label: "Alertas de seguridad", icon: "bell", badge: true },
  { to: "/seguridad", label: "Centro de seguridad", icon: "key" },
  { to: "/usuarios", label: "Usuarios y roles", icon: "users" },
  { to: "/bitacora", label: "Bitácora", icon: "activity" },
];

// Active alerts counter for the sidebar (admins only), refreshed every minute and on navigation.
function useActiveAlerts(enabled, pathname) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled) return undefined;
    let alive = true;
    const refresh = () => api.alertSummary().then((s) => alive && setCount(s.active_total)).catch(() => {});
    refresh();
    const id = setInterval(refresh, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [enabled, pathname]);
  return count;
}

function GlobalSearch() {
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const [value, setValue] = useState("");

  useEffect(() => {
    const handler = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <form
      className="topbar-search"
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        navigate(`/buscar?q=${encodeURIComponent(value.trim())}`);
        setValue("");
        inputRef.current?.blur();
      }}
    >
      <Icon name="search" size={16} />
      <input
        ref={inputRef}
        className="input"
        placeholder="Buscar en documentos cifrados…"
        aria-label="Buscar en documentos"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <span className="kbd" aria-hidden="true">⌘K</span>
    </form>
  );
}

export default function Layout() {
  const { user, isAdmin, canUpload, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  const activeAlerts = useActiveAlerts(isAdmin, location.pathname);
  useEffect(() => setMenuOpen(false), [location.pathname]);

  const link = (item) => (
    <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
      <Icon name={item.icon} size={18} />
      {item.label}
      {item.badge && activeAlerts > 0 && (
        <span className="nav-count" aria-label={`${activeAlerts} alertas activas`}>{activeAlerts}</span>
      )}
    </NavLink>
  );

  return (
    <div className="shell">
      <aside className={`sidebar ${menuOpen ? "open" : ""}`} aria-label="Navegación principal">
        <div className="brand">
          <span className="brand-mark"><Icon name="lock" size={17} /></span>
          <div>
            Bóveda IA
            <small>Gestión documental cifrada</small>
          </div>
        </div>
        <nav>
          <div className="nav-section">Bóveda</div>
          {MAIN_NAV.filter((item) => !item.uploaders || canUpload).map(link)}
          {isAdmin && (
            <>
              <div className="nav-section">Administración</div>
              {ADMIN_NAV.map(link)}
            </>
          )}
        </nav>
        <div className="sidebar-footer">
          <div className="secure-pill"><span className="dot" /> Cifrado AES-256-GCM activo</div>
          <button className="btn btn-ghost btn-sm" style={{ justifyContent: "flex-start" }} onClick={logout}>
            <Icon name="logout" size={16} /> Cerrar sesión
          </button>
        </div>
      </aside>
      {menuOpen && <div className="overlay" style={{ zIndex: 44 }} onClick={() => setMenuOpen(false)} />}

      <div className="main">
        <header className="topbar">
          <button className="btn btn-ghost btn-icon menu-btn" onClick={() => setMenuOpen(true)} aria-label="Abrir menú">
            <Icon name="menu" />
          </button>
          <GlobalSearch />
          <div className="topbar-actions">
            <button
              className="btn btn-ghost btn-icon"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
              title={theme === "dark" ? "Tema claro" : "Tema oscuro"}
            >
              <Icon name={theme === "dark" ? "sun" : "moon"} />
            </button>
            <div className="user-chip">
              <span className="avatar" aria-hidden="true">{user.username.slice(0, 2)}</span>
              <div className="who">
                <b>{user.username}</b>
                <span>{ROLE_LABELS[user.role]}</span>
              </div>
            </div>
          </div>
        </header>
        <main className="content" id="contenido">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
