// Small presentational building blocks shared by every page.
import { useEffect } from "react";
import Icon from "./Icon";
import { ROLE_LABELS, SENSITIVITY, SEVERITY, fileExtension, riskColor } from "../utils/format";

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{actions}</div>}
    </header>
  );
}

export function SensitivityBadge({ level }) {
  const info = SENSITIVITY[level] || { label: level };
  return (
    <span className={`badge badge-${level}`}>
      <span className="dot" aria-hidden="true" />
      {info.label}
    </span>
  );
}

export function SeverityBadge({ level }) {
  return (
    <span className={`sev sev-${level}`}>
      <span className="dot" aria-hidden="true" />
      {SEVERITY[level]?.label || level}
    </span>
  );
}

export function RoleBadge({ role }) {
  return <span className="badge badge-outline">{ROLE_LABELS[role] || role}</span>;
}

export function RiskMeter({ score }) {
  return (
    <div className="risk" title={`Riesgo ${score} de 100`}>
      <div className="risk-track" aria-hidden="true">
        <div className="risk-fill" style={{ width: `${Math.max(score, 3)}%`, background: riskColor(score) }} />
      </div>
      <span className="num mono">{score}</span>
    </div>
  );
}

export function FileIcon({ name }) {
  return <span className="file-icon" aria-hidden="true">{fileExtension(name)}</span>;
}

export function StatCard({ icon, label, value, unit, foot, hero = false }) {
  return (
    <div className={`stat ${hero ? "hero" : ""}`}>
      <div className="stat-label">
        {icon && <Icon name={icon} size={16} />}
        {label}
      </div>
      <div className="stat-value">
        {value}
        {unit && <small>{unit}</small>}
      </div>
      {foot && <div className="stat-foot">{foot}</div>}
    </div>
  );
}

export function EmptyState({ icon = "files", title, children, action }) {
  return (
    <div className="empty">
      <div className="icon-circle">
        <Icon name={icon} size={22} />
      </div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}

export function Spinner({ label }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <span className="spinner" aria-hidden="true" />
      {label}
    </span>
  );
}

export function SkeletonRows({ rows = 5 }) {
  return (
    <div className="card-body" aria-busy="true" aria-label="Cargando">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: 18, margin: "14px 0", width: `${90 - i * 8}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <EmptyState icon="alert" title="No se pudo cargar la información" action={onRetry && (
      <button className="btn btn-secondary" onClick={onRetry}>Reintentar</button>
    )}>
      {message}
    </EmptyState>
  );
}

function useEscape(onClose) {
  useEffect(() => {
    const handler = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);
}

export function Drawer({ onClose, labelledBy, children }) {
  useEscape(onClose);
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby={labelledBy}>
        {children}
      </aside>
    </>
  );
}

export function ConfirmDialog({ title, children, confirmLabel = "Confirmar", danger = false, busy, onConfirm, onCancel }) {
  useEscape(onCancel);
  return (
    <>
      <div className="overlay modal-overlay" onClick={onCancel} />
      <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 id="confirm-title">{title}</h2>
        <div className="muted">{children}</div>
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onCancel} autoFocus>Cancelar</button>
          <button className={`btn ${danger ? "btn-danger-solid" : "btn-primary"}`} onClick={onConfirm} disabled={busy}>
            {busy ? <Spinner label="Procesando…" /> : confirmLabel}
          </button>
        </div>
      </div>
    </>
  );
}

export function FindingsList({ findings }) {
  const items = Object.values(findings || {});
  if (!items.length) {
    return (
      <p className="muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Icon name="shield" size={16} /> No se detectaron datos sensibles.
      </p>
    );
  }
  return (
    <div>
      {items.map((finding) => (
        <div key={finding.label} className="list-row" style={{ alignItems: "flex-start", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
            <b style={{ fontWeight: 600 }}>{finding.label}</b>
            <span className="subtle mono">×{finding.count}</span>
          </div>
          <div className="chips">
            {finding.samples.map((sample) => (
              <span key={sample} className="chip">{sample}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
