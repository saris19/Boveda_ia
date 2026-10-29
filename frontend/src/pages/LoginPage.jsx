import { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import Icon from "../components/Icon";
import { Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";

const STATUS_TEXT = {
  checking: "Verificando el servidor…",
  waking: "Despertando el servidor (puede tardar hasta 1 minuto)…",
  ok: "Servidor en línea",
  down: "No se pudo contactar el servidor",
};

// Free hosting sleeps after inactivity: ping the API on load so it is awake when the user signs in.
function useApiStatus() {
  const [status, setStatus] = useState("checking");
  useEffect(() => {
    let alive = true;
    const slow = setTimeout(() => alive && setStatus((s) => (s === "checking" ? "waking" : s)), 2500);
    api
      .health()
      .then(() => alive && setStatus("ok"))
      .catch(() => alive && setStatus("down"))
      .finally(() => clearTimeout(slow));
    return () => {
      alive = false;
      clearTimeout(slow);
    };
  }, []);
  return status;
}

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const status = useApiStatus();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={location.state?.from || "/panel"} replace />;

  const submit = async (event) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("Escribe tu usuario y tu contraseña.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await login(username.trim(), password);
      navigate(location.state?.from || "/panel", { replace: true });
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <section className="login-hero" aria-labelledby="hero-title">
        <div className="brand" style={{ padding: 0 }}>
          <span className="brand-mark"><Icon name="lock" size={17} /></span>
          Bóveda IA
        </div>
        <div>
          <div className="eyebrow">Gestión documental segura</div>
          <h1 id="hero-title">Tus documentos,<br />cifrados y entendidos.</h1>
          <p className="lead">
            Cada archivo se cifra con su propia llave. La inteligencia artificial lo clasifica, detecta datos
            sensibles y te permite buscar dentro de él sin exponer su contenido.
          </p>
          <div className="feature-list">
            <div><b>AES-256-GCM</b><span>Cifrado de sobre por documento</span></div>
            <div><b>Índice ciego</b><span>Búsqueda en contenido cifrado</span></div>
            <div><b>RBAC + IA</b><span>Roles, clasificación y riesgo</span></div>
          </div>
        </div>
        <p className="subtle" style={{ fontSize: 13 }}>Proyecto académico · Ingeniería de Software</p>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit} noValidate>
          <div>
            <h2>Iniciar sesión</h2>
            <p className="muted" style={{ marginTop: 6 }}>Accede con tu usuario de la bóveda.</p>
          </div>
          <label className="field">
            <span>Usuario</span>
            <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </label>
          <label className="field">
            <span>Contraseña</span>
            <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && (
            <p className="form-error" role="alert"><Icon name="alert" size={16} /> {error}</p>
          )}
          <button className="btn btn-primary btn-lg btn-block" disabled={busy}>
            {busy ? <Spinner label={status === "ok" ? "Verificando…" : "Esperando al servidor…"} /> : <>Entrar <Icon name="arrowRight" size={16} /></>}
          </button>
          <div className="status-line" aria-live="polite">
            <span className={`dot ${status}`} /> {STATUS_TEXT[status]}
          </div>
        </form>
      </section>
    </div>
  );
}
