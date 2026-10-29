import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import Icon from "../components/Icon";
import { EmptyState, ErrorState, PageHeader, SkeletonRows } from "../components/ui";
import { ACTION_LABELS, formatDateTime } from "../utils/format";

export default function AuditPage() {
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState("");
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setError("");
    setLoading(true);
    api
      .auditLog({ limit: 500, only_failed: onlyFailed || undefined })
      .then(setEntries)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [onlyFailed]);
  useEffect(load, [load]);

  const visible = useMemo(() => (entries || []).filter((e) => !action || e.action === action), [entries, action]);
  const failed = (entries || []).filter((e) => !e.success).length;

  return (
    <>
      <PageHeader eyebrow="Administración" title="Bitácora de accesos"
        description="Cada inicio de sesión, búsqueda, descarga, acceso denegado y cambio de permisos queda registrado. Es la base para la detección de accesos sospechosos."
        actions={<button className="btn btn-secondary" onClick={load}><Icon name="activity" size={16} /> Actualizar</button>} />

      <section className={`card ${loading && entries ? "refetching" : ""}`}>
        <div className="toolbar">
          <select className="select" value={action} onChange={(e) => setAction(e.target.value)} aria-label="Acción">
            <option value="">Todas las acciones</option>
            {Object.entries(ACTION_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14 }}>
            <input type="checkbox" checked={onlyFailed} onChange={(e) => setOnlyFailed(e.target.checked)} /> Solo fallidos
          </label>
          {entries && <span className="subtle" style={{ fontSize: 13, marginLeft: "auto" }}>{visible.length} eventos · {failed} fallidos</span>}
        </div>
        {error ? <ErrorState message={error} onRetry={load} /> : !entries ? <SkeletonRows rows={8} /> : visible.length === 0 ? (
          <EmptyState icon="activity" title="Sin eventos para estos filtros" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Resultado</th><th>IP</th><th>Detalle</th></tr></thead>
              <tbody>
                {visible.map((e) => (
                  <tr key={e.id}>
                    <td className="mono subtle" style={{ whiteSpace: "nowrap" }}>{formatDateTime(e.timestamp)}</td>
                    <td className="mono">{e.username || "—"}</td>
                    <td>{ACTION_LABELS[e.action] || e.action}</td>
                    <td>{e.success
                      ? <span className="badge badge-publico"><span className="dot" />Exitoso</span>
                      : <span className="badge badge-restringido"><span className="dot" />Fallido</span>}</td>
                    <td className="mono subtle">{e.ip_address}</td>
                    <td className="subtle" style={{ fontSize: 13 }}>{e.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
