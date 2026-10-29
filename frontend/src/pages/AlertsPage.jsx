import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import ColumnChart from "../components/charts/ColumnChart";
import Icon from "../components/Icon";
import { EmptyState, ErrorState, PageHeader, SeverityBadge, SkeletonRows, Spinner, StatCard } from "../components/ui";
import { useToast } from "../context/ToastContext";
import { ALERT_STATUS, SEVERITY, SEVERITY_ORDER, formatDateTime, timeAgo } from "../utils/format";

const STATUS_FILTERS = [
  ["activas", "Activas"],
  ["", "Todas"],
  ["resuelta", "Resueltas"],
  ["falso_positivo", "Falsos positivos"],
];
const RULE_NAMES = {
  brute_force: "Fuerza bruta",
  credential_stuffing: "Ataque desde una IP",
  mass_download: "Descarga masiva",
  access_denied: "Accesos denegados",
  off_hours: "Fuera de horario",
  new_ip: "IP nueva",
  enumeration: "Exploración masiva",
  ml_anomaly: "IA · Isolation Forest",
};

function AlertItem({ alert, onChange }) {
  const [busy, setBusy] = useState("");
  const done = alert.status === "resuelta" || alert.status === "falso_positivo";
  const set = async (status) => {
    setBusy(status);
    await onChange(alert, status);
    setBusy("");
  };
  return (
    <article className={`alert-item ${done ? "resolved" : ""}`}>
      <span className="alert-bar" style={{ background: SEVERITY[alert.severity]?.color }} aria-hidden="true" />
      <div style={{ minWidth: 0 }}>
        <h3>
          <SeverityBadge level={alert.severity} />
          {alert.title}
        </h3>
        <p className="muted" style={{ fontSize: 14, marginTop: 6 }}>{alert.description}</p>
        {alert.response && (
          <span className="alert-response"><Icon name="shield" size={14} /> Respuesta automática: {alert.response}</span>
        )}
        <div className="alert-meta">
          <span>{RULE_NAMES[alert.rule] || alert.rule}</span>
          {alert.score > 0 && <span>Anomalía {Math.round(alert.score)}/100</span>}
          {alert.event_count > 1 && <span>{alert.event_count} eventos</span>}
          {alert.ip_address && <span className="mono">IP {alert.ip_address}</span>}
          <span title={formatDateTime(alert.created_at)}>{timeAgo(alert.updated_at)}</span>
          <span>{ALERT_STATUS[alert.status]}</span>
        </div>
      </div>
      <div className="alert-actions">
        {!done ? (
          <>
            <button className="btn btn-secondary btn-sm" onClick={() => set("resuelta")} disabled={Boolean(busy)}>
              <Icon name="check" size={14} /> Resolver
            </button>
            {alert.status !== "en_revision" && (
              <button className="btn btn-ghost btn-sm" onClick={() => set("en_revision")} disabled={Boolean(busy)}>En revisión</button>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => set("falso_positivo")} disabled={Boolean(busy)}>Falso positivo</button>
          </>
        ) : (
          <button className="btn btn-ghost btn-sm" onClick={() => set("abierta")} disabled={Boolean(busy)}>Reabrir</button>
        )}
      </div>
    </article>
  );
}

export default function AlertsPage() {
  const notify = useToast();
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [status, setStatus] = useState("activas");
  const [severity, setSeverity] = useState("");
  const [error, setError] = useState("");
  const [retraining, setRetraining] = useState(false);

  const load = useCallback(() => {
    setError("");
    Promise.all([api.alertSummary(-new Date().getTimezoneOffset()), api.listAlerts({ status, severity })])
      .then(([s, a]) => {
        setSummary(s);
        setAlerts(a);
      })
      .catch((e) => setError(e.message));
  }, [status, severity]);
  useEffect(load, [load]);

  const changeStatus = async (alert, next) => {
    try {
      await api.updateAlert(alert.id, { status: next });
      notify(`Alerta marcada como “${ALERT_STATUS[next].toLowerCase()}”`);
      load();
    } catch (e) {
      notify(e.message, "error");
    }
  };

  const retrain = async () => {
    setRetraining(true);
    try {
      await api.retrainAnomalyModel();
      notify("Modelo de anomalías reentrenado con la bitácora actual");
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setRetraining(false);
    }
  };

  if (error) return <ErrorState message={error} onRetry={load} />;

  const perDay = (summary?.per_day || []).map((d) => {
    const date = new Date(`${d.date}T12:00:00Z`);
    return {
      ...d,
      label: `${date.getUTCDate()} ${date.toLocaleDateString("es-CO", { month: "short", timeZone: "UTC" }).replace(".", "")}`,
      tooltipLabel: date.toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }),
    };
  });
  const model = summary?.model;

  return (
    <>
      <PageHeader
        eyebrow="Administración · IA"
        title="Alertas de seguridad"
        description="Detección de accesos sospechosos: reglas explicables para ataques conocidos y un modelo Isolation Forest que aprende el comportamiento normal de la bitácora."
        actions={<button className="btn btn-secondary" onClick={load}><Icon name="refresh" size={16} /> Actualizar</button>}
      />

      {!summary ? <div className="card"><SkeletonRows /></div> : (
        <>
          <div className="stats">
            <StatCard hero icon="bell" label="Alertas activas" value={summary.active_total} foot={`${summary.total} en total`} />
            {["critica", "alta", "media"].map((level) => (
              <div className="stat" key={level}>
                <div className="stat-label"><SeverityBadge level={level} /></div>
                <div className="stat-value">{summary.active_by_severity[level] || 0}</div>
                <div className="stat-foot">activas</div>
              </div>
            ))}
          </div>

          <div className="grid grid-3">
            <section className="card">
              <div className="card-head"><div><h2>Alertas por día</h2><p>Últimos 14 días</p></div></div>
              <div className="card-body">
                <ColumnChart data={perDay} series={[{ key: "alerts", label: "Alertas", color: "var(--series-1)" }]} ariaLabel="Alertas por día" />
              </div>
            </section>
            <section className="card">
              <div className="card-head">
                <div><h2>Modelo de anomalías</h2><p>{model?.algorithm}</p></div>
              </div>
              <div className="card-body">
                {model?.trained ? (
                  <div className="mini-kv" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>
                    <div><span>Entrenado</span><b>{timeAgo(model.trained_at)}</b></div>
                    <div><span>Eventos reales</span><b className="num">{model.real_events}</b></div>
                    <div><span>Línea base sintética</span><b className="num">{model.synthetic_events}</b></div>
                    <div><span>Umbral de alerta</span><b className="num">{model.threshold}/100</b></div>
                    <div><span>Reentrenamiento</span><b>cada {model.retrain_every} eventos</b></div>
                  </div>
                ) : <p className="muted">Sin entrenar.</p>}
                <button className="btn btn-secondary btn-sm" style={{ marginTop: 16 }} onClick={retrain} disabled={retraining}>
                  {retraining ? <Spinner label="Entrenando…" /> : <><Icon name="cpu" size={15} /> Reentrenar ahora</>}
                </button>
              </div>
            </section>
          </div>
        </>
      )}

      <section className="card section">
        <div className="toolbar">
          <div className="segmented" role="group" aria-label="Estado">
            {STATUS_FILTERS.map(([value, label]) => (
              <button key={label} className={status === value ? "active" : ""} onClick={() => setStatus(value)}>{label}</button>
            ))}
          </div>
          <select className="select" value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Severidad">
            <option value="">Toda severidad</option>
            {SEVERITY_ORDER.map((s) => <option key={s} value={s}>{SEVERITY[s].label}</option>)}
          </select>
          {alerts && <span className="subtle" style={{ marginLeft: "auto", fontSize: 13 }}>{alerts.length} alertas</span>}
        </div>
        {!alerts ? <SkeletonRows /> : alerts.length === 0 ? (
          <EmptyState icon="shield" title="Sin alertas para este filtro">
            Prueba la detección con <span className="mono">python scripts/simulate_attacks.py</span> en la carpeta backend.
          </EmptyState>
        ) : alerts.map((alert) => <AlertItem key={alert.id} alert={alert} onChange={changeStatus} />)}
      </section>

      {summary && (
        <section className="card section">
          <div className="card-head"><div><h2>Qué se vigila</h2><p>Reglas activas y modelo de IA</p></div></div>
          <div className="card-body rule-list" style={{ paddingTop: 8 }}>
            {summary.rules.map((rule) => (
              <div key={rule.code}>
                <b>{rule.name} <span className="subtle" style={{ fontWeight: 400 }}>· {rule.severity}</span></b>
                <span>{rule.description}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
