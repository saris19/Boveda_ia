import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import BarList from "../components/charts/BarList";
import ColumnChart from "../components/charts/ColumnChart";
import SegmentBar from "../components/charts/SegmentBar";
import Icon from "../components/Icon";
import { EmptyState, ErrorState, PageHeader, SkeletonRows, StatCard } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ACTION_LABELS, formatBytes, percent, timeAgo } from "../utils/format";

const ACTIVITY_SERIES = [
  { key: "ok", label: "Exitosos", color: "var(--series-1)" },
  { key: "failed", label: "Fallidos", color: "var(--critical)" },
];

function ActivityTable({ rows }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Día</th><th className="right">Exitosos</th><th className="right">Fallidos</th><th className="right">Subidas</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.date}>
              <td>{row.tooltipLabel}</td>
              <td className="right num">{row.ok}</td>
              <td className="right num">{row.failed}</td>
              <td className="right num">{row.uploads}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DashboardPage() {
  const { user, isAdmin, canUpload } = useAuth();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [showTable, setShowTable] = useState(false);

  const [alerts, setAlerts] = useState(null);

  const load = useCallback(() => {
    setError("");
    api.stats(-new Date().getTimezoneOffset()).then(setStats).catch((e) => setError(e.message));
    if (isAdmin) api.alertSummary().then(setAlerts).catch(() => setAlerts(null));
  }, [isAdmin]);
  useEffect(load, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!stats) {
    return (
      <>
        <PageHeader eyebrow="Panel" title={`Hola, ${user.username}`} />
        <div className="card"><SkeletonRows rows={6} /></div>
      </>
    );
  }

  const activity = stats.activity.map((day) => {
    const date = new Date(`${day.date}T12:00:00Z`);
    return {
      ...day,
      ok: day.events - day.failed,
      label: `${date.getUTCDate()} ${date.toLocaleDateString("es-CO", { month: "short", timeZone: "UTC" }).replace(".", "")}`,
      tooltipLabel: date.toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }),
    };
  });
  const totalEvents = activity.reduce((sum, d) => sum + d.events, 0);

  return (
    <>
      <PageHeader
        eyebrow="Panel"
        title={`Hola, ${user.username}`}
        description="Resumen de los documentos a los que tienes acceso y de la actividad reciente."
        actions={
          <>
            <Link className="btn btn-secondary" to="/buscar"><Icon name="search" size={16} /> Buscar</Link>
            {canUpload && <Link className="btn btn-primary" to="/documentos?subir=1"><Icon name="upload" size={16} /> Subir documento</Link>}
          </>
        }
      />

      <div className="stats">
        <StatCard hero icon="lock" label="Documentos cifrados" value={stats.total_documents} foot={`${formatBytes(stats.total_bytes)} protegidos`} />
        <StatCard icon="alert" label="Confidenciales o restringidos" value={stats.sensitive_documents}
          foot={`${percent(stats.sensitive_documents, stats.total_documents)}% del total`} />
        <StatCard icon="shield" label="Riesgo promedio" value={stats.average_risk} unit="/100" foot="Según datos sensibles detectados" />
        {isAdmin ? (
          <Link to="/alertas" className="stat" style={{ color: "inherit", textDecoration: "none" }}>
            <div className="stat-label"><Icon name="bell" size={16} />Alertas de seguridad activas</div>
            <div className="stat-value">{alerts ? alerts.active_total : "—"}</div>
            <div className="stat-foot">
              {alerts ? `${alerts.active_by_severity.critica} críticas · ${alerts.active_by_severity.alta} altas` : ""}
              {` · ${stats.failed_logins_7d} inicios fallidos en 7 días`}
            </div>
          </Link>
        ) : (
          <StatCard icon="search" label="Indexados para búsqueda" value={stats.indexed_documents}
            foot="Búsqueda dentro del contenido cifrado" />
        )}
      </div>

      {stats.total_documents === 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <EmptyState icon="files" title="Tu bóveda está vacía"
            action={canUpload && <Link className="btn btn-primary" to="/documentos?subir=1">Subir el primer documento</Link>}>
            {canUpload
              ? "Sube un documento: se cifrará, la IA lo clasificará y podrás buscarlo por su contenido."
              : "Cuando alguien comparta un documento contigo aparecerá aquí."}
          </EmptyState>
        </div>
      )}

      <div className="grid grid-3">
        <section className="card">
          <div className="card-head">
            <div>
              <h2>Actividad de los últimos 14 días</h2>
              <p>{isAdmin ? "Todas las acciones registradas en la bitácora" : "Tus acciones registradas"} · {totalEvents} eventos</p>
            </div>
            <button className="link-btn" onClick={() => setShowTable((v) => !v)}>{showTable ? "Ver gráfica" : "Ver tabla"}</button>
          </div>
          <div className="card-body">
            {showTable ? (
              <ActivityTable rows={activity} />
            ) : (
              <>
                <div className="legend" style={{ marginBottom: 16 }}>
                  {ACTIVITY_SERIES.map((s) => (
                    <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>
                  ))}
                </div>
                <ColumnChart data={activity} series={ACTIVITY_SERIES} ariaLabel="Eventos por día" />
              </>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-head"><div><h2>Niveles de sensibilidad</h2><p>Asignados por la IA al subir</p></div></div>
          <div className="card-body">
            <SegmentBar items={stats.by_sensitivity} />
            <div className="mini-kv">
              <div><span>Indexados para búsqueda</span><b className="num">{stats.indexed_documents} de {stats.total_documents}</b></div>
              <div><span>Volumen cifrado</span><b className="num">{formatBytes(stats.total_bytes)}</b></div>
              <div><span>Cifrado</span><b>AES-256-GCM</b></div>
            </div>
          </div>
        </section>
      </div>

      <div className="grid grid-3 section">
        <section className="card">
          <div className="card-head"><div><h2>Documentos por categoría</h2><p>Clasificación automática</p></div>
            <Link to="/documentos" className="link-btn">Ver documentos</Link></div>
          <div className="card-body"><BarList items={stats.by_category} /></div>
        </section>
        <section className="card">
          <div className="card-head"><div><h2>Datos sensibles más frecuentes</h2><p>Documentos que los contienen</p></div></div>
          <div className="card-body"><BarList items={stats.top_findings} emptyText="No se han detectado datos sensibles." /></div>
        </section>
      </div>

      <section className="card section">
        <div className="card-head"><div><h2>Actividad reciente</h2><p>{isAdmin ? "Últimos eventos del sistema" : "Tus últimos eventos"}</p></div>
          {isAdmin && <Link to="/bitacora" className="link-btn">Abrir bitácora</Link>}</div>
        <div className="card-body" style={{ paddingTop: 8 }}>
          {stats.recent_events.length === 0 ? <p className="muted">Sin actividad todavía.</p> : stats.recent_events.map((event) => (
            <div className="activity-item" key={event.id}>
              <span className={`activity-icon ${event.success ? "" : "fail"}`}>
                <Icon name={event.success ? "check" : "alert"} size={15} />
              </span>
              <div>
                <b style={{ fontWeight: 550 }}>{ACTION_LABELS[event.action] || event.action}</b>
                <span className="muted"> · {event.username || "desconocido"}</span>
                {!event.success && <span className="badge badge-restringido" style={{ marginLeft: 8, height: 20 }}>Fallido</span>}
                {event.detail && <div className="subtle" style={{ fontSize: 12.5 }}>{event.detail}</div>}
              </div>
              <time dateTime={event.timestamp}>{timeAgo(event.timestamp)}</time>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
