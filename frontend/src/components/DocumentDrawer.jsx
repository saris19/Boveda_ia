import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import {
  CATEGORIES,
  ROLE_LABELS,
  SENSITIVITY,
  SENSITIVITY_ORDER,
  formatBytes,
  formatDateTime,
  roleShareAllowed,
} from "../utils/format";
import Icon from "./Icon";
import { ConfirmDialog, Drawer, FileIcon, FindingsList, RiskMeter, SensitivityBadge, Spinner } from "./ui";

const POLICY_TEXT = {
  confidencial: "Documento confidencial: solo se puede compartir con usuarios específicos o con los roles Editor y Administrador.",
  restringido: "Documento restringido: solo se puede compartir con usuarios específicos, uno por uno.",
};

function SharePanel({ document, users }) {
  const notify = useToast();
  const [permissions, setPermissions] = useState(null);
  const roleOptions = Object.keys(ROLE_LABELS).filter((role) => roleShareAllowed(document.sensitivity, role));
  const [target, setTarget] = useState(roleOptions.length ? `role:${roleOptions[roleOptions.length - 1]}` : "");
  const [level, setLevel] = useState("read");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api.listPermissions(document.id).then(setPermissions).catch((e) => notify(e.message, "error"));
  }, [document.id, notify]);
  useEffect(load, [load]);

  const share = async (event) => {
    event.preventDefault();
    if (!target) return;
    const [kind, value] = target.split(":");
    setSaving(true);
    try {
      await api.shareDocument(document.id, { access_level: level, [kind === "user" ? "username" : "role"]: value });
      notify("Acceso concedido");
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const revoke = async (permission) => {
    try {
      await api.revokePermission(document.id, permission.id);
      notify("Acceso revocado");
      load();
    } catch (e) {
      notify(e.message, "error");
    }
  };

  const nameOf = (p) =>
    p.user_id
      ? users.find((u) => u.id === p.user_id)?.username || `Usuario #${p.user_id}`
      : `Todos los ${ROLE_LABELS[p.role]?.toLowerCase()}es`;
  const inactiveRoleGrant = (p) => !p.user_id && !roleShareAllowed(document.sensitivity, p.role);

  return (
    <section className="drawer-section">
      <h3>Compartir</h3>
      {POLICY_TEXT[document.sensitivity] && (
        <div className="notice warn" style={{ marginBottom: 12 }}>
          <Icon name="shield" size={16} /> {POLICY_TEXT[document.sensitivity]}
        </div>
      )}
      <form className="form-grid" style={{ gridTemplateColumns: "1fr 120px auto" }} onSubmit={share}>
        <label className="field">
          <span>Usuario o rol</span>
          <select className="select" value={target} onChange={(e) => setTarget(e.target.value)}>
            {roleOptions.length > 0 && (
              <optgroup label="Roles">
                {roleOptions.map((value) => (
                  <option key={value} value={`role:${value}`}>Todos los {ROLE_LABELS[value].toLowerCase()}es</option>
                ))}
              </optgroup>
            )}
            <optgroup label="Usuarios">
              {!roleOptions.length && <option value="">Elige un usuario…</option>}
              {users.filter((u) => u.id !== document.owner_id && u.is_active).map((u) => (
                <option key={u.id} value={`user:${u.username}`}>{u.username} · {ROLE_LABELS[u.role]}</option>
              ))}
            </optgroup>
          </select>
        </label>
        <label className="field">
          <span>Permiso</span>
          <select className="select" value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="read">Lectura</option>
            <option value="manage">Gestión</option>
          </select>
        </label>
        <button className="btn btn-secondary" disabled={saving || !target}>
          <Icon name="share" size={16} /> Compartir
        </button>
      </form>
      <div style={{ marginTop: 12 }}>
        {permissions === null ? (
          <Spinner label="Cargando permisos…" />
        ) : permissions.length === 0 ? (
          <p className="muted" style={{ fontSize: 14 }}>Solo el propietario y los administradores tienen acceso.</p>
        ) : (
          permissions.map((p) => (
            <div className="list-row" key={p.id}>
              <span style={inactiveRoleGrant(p) ? { textDecoration: "line-through", opacity: 0.6 } : undefined}>
                {nameOf(p)} <span className="subtle">· {p.access_level === "manage" ? "gestión" : "lectura"}</span>
                {inactiveRoleGrant(p) && <span className="subtle"> · sin efecto por la sensibilidad</span>}
              </span>
              <button className="btn btn-ghost btn-sm" onClick={() => revoke(p)}>Revocar</button>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function VersionsPanel({ document, canManage, onChanged }) {
  const notify = useToast();
  const inputRef = useRef(null);
  const [versions, setVersions] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    api.listVersions(document.id).then(setVersions).catch(() => setVersions([]));
  }, [document.id]);
  useEffect(load, [load, document.version_number, document.sensitivity, document.category]);

  const uploadVersion = async (file) => {
    if (!file) return;
    setBusy("upload");
    try {
      const updated = await api.uploadVersion(document.id, file);
      notify(`Versión ${updated.version_number} cifrada y analizada`);
      onChanged(updated);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy("");
    }
  };

  const restore = async (number) => {
    setBusy(`restore-${number}`);
    try {
      const updated = await api.restoreVersion(document.id, number);
      notify(`Versión ${number} restaurada como versión ${updated.version_number}`);
      onChanged(updated);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy("");
    }
  };

  const download = async (number) => {
    try {
      await api.downloadDocument(document, number);
    } catch (e) {
      notify(e.message, "error");
    }
  };

  return (
    <section className="drawer-section">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3>Versiones</h3>
        {canManage && (
          <>
            <button className="link-btn" onClick={() => inputRef.current?.click()} disabled={busy === "upload"}>
              {busy === "upload" ? "Cifrando…" : "+ Subir nueva versión"}
            </button>
            <input ref={inputRef} type="file" hidden accept=".txt,.md,.csv,.pdf,.docx"
              onChange={(e) => { uploadVersion(e.target.files[0]); e.target.value = ""; }} />
          </>
        )}
      </div>
      {versions === null ? <Spinner label="Cargando versiones…" /> : versions.map((v) => (
        <div className="version-row" key={v.version_number}>
          <span className={`version-tag ${v.is_current ? "current" : ""}`}>v{v.version_number}</span>
          <div style={{ minWidth: 0 }}>
            <div>{v.is_current ? <b style={{ fontWeight: 600 }}>Versión actual</b> : v.original_name}
              <span className="subtle"> · {formatBytes(v.size_bytes)} · {SENSITIVITY[v.sensitivity]?.label}</span></div>
            <div className="subtle" style={{ fontSize: 12.5 }}>{formatDateTime(v.uploaded_at)}{v.uploaded_by_username && ` · ${v.uploaded_by_username}`}</div>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {!v.is_current && (
              <>
                <button className="btn btn-ghost btn-sm" onClick={() => download(v.version_number)} title="Descargar esta versión">
                  <Icon name="download" size={15} />
                </button>
                {canManage && (
                  <button className="btn btn-ghost btn-sm" onClick={() => restore(v.version_number)} disabled={Boolean(busy)}>
                    {busy === `restore-${v.version_number}` ? "…" : "Restaurar"}
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      ))}
    </section>
  );
}

function ClassificationEditor({ document, onChanged }) {
  const notify = useToast();
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState(document.category);
  const [sensitivity, setSensitivity] = useState(document.sensitivity);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setCategory(document.category);
    setSensitivity(document.sensitivity);
  }, [document.category, document.sensitivity]);

  const save = async (event) => {
    event.preventDefault();
    const payload = {};
    if (category !== document.category) payload.category = category;
    if (sensitivity !== document.sensitivity) payload.sensitivity = sensitivity;
    if (!Object.keys(payload).length) {
      setOpen(false);
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateClassification(document.id, payload);
      notify(payload.category ? "Corrección guardada: el modelo se reentrena con ella" : "Sensibilidad actualizada");
      onChanged(updated);
      setOpen(false);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button className="link-btn" onClick={() => setOpen(true)}>
        <Icon name="edit" size={13} /> Corregir clasificación
      </button>
    );
  }
  return (
    <form onSubmit={save} className="card card-pad" style={{ marginTop: 12, padding: 16 }}>
      <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <label className="field">
          <span>Categoría</span>
          <select className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Sensibilidad</span>
          <select className="select" value={sensitivity} onChange={(e) => setSensitivity(e.target.value)}>
            {SENSITIVITY_ORDER.map((s) => <option key={s} value={s}>{SENSITIVITY[s].label}</option>)}
          </select>
        </label>
      </div>
      <p className="hint" style={{ margin: "10px 0" }}>
        Las correcciones de categoría se guardan (sin nombres ni números) para reentrenar el modelo.
      </p>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary btn-sm" disabled={saving}>{saving ? "Guardando…" : "Guardar corrección"}</button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>Cancelar</button>
      </div>
    </form>
  );
}

export default function DocumentDrawer({ document: initial, onClose, onDeleted, onUpdated }) {
  const { canUpload } = useAuth();
  const notify = useToast();
  const [document, setDocument] = useState(initial);
  const [users, setUsers] = useState([]);
  const [downloading, setDownloading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const canManage = document.my_access === "manage" && canUpload;

  useEffect(() => setDocument(initial), [initial]);
  useEffect(() => {
    if (canManage) api.listUsers().then(setUsers).catch(() => setUsers([]));
  }, [canManage]);

  const changed = (updated) => {
    setDocument(updated);
    onUpdated?.(updated);
  };

  const download = async () => {
    setDownloading(true);
    try {
      await api.downloadDocument(document);
      notify("Descifrado e integridad SHA-256 verificada");
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setDownloading(false);
    }
  };

  const remove = async () => {
    setDeleting(true);
    try {
      await api.deleteDocument(document.id);
      notify("Documento enviado a la papelera");
      onDeleted?.(document.id);
      onClose();
    } catch (e) {
      notify(e.message, "error");
      setDeleting(false);
    }
  };

  return (
    <Drawer onClose={onClose} labelledBy="drawer-title">
      <div className="drawer-head">
        <FileIcon name={document.original_name} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 id="drawer-title">{document.original_name}</h2>
          <div className="chips" style={{ marginTop: 8 }}>
            <SensitivityBadge level={document.sensitivity} />
            <span className="badge">{document.category}</span>
            <span className="badge badge-outline">v{document.version_number}</span>
          </div>
        </div>
        <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Cerrar" autoFocus>
          <Icon name="close" />
        </button>
      </div>

      <div className="drawer-body">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-primary" onClick={download} disabled={downloading}>
            {downloading ? <Spinner label="Descifrando…" /> : <><Icon name="download" size={16} /> Descargar</>}
          </button>
          {canManage && (
            <button className="btn btn-danger" onClick={() => setConfirming(true)}>
              <Icon name="trash" size={16} /> Enviar a la papelera
            </button>
          )}
        </div>

        <section className="drawer-section">
          <h3>Análisis de IA</h3>
          <dl className="kv">
            <dt>Categoría</dt>
            <dd>
              {document.category}{" "}
              <span className="subtle">
                · {document.manual_classification ? "corregida por una persona" : `${Math.round(document.category_confidence * 100)}% de confianza`}
              </span>
            </dd>
            <dt>Riesgo</dt>
            <dd><RiskMeter score={document.risk_score} /></dd>
            <dt>Palabras clave</dt>
            <dd>
              <div className="chips">
                {(document.keywords || []).length
                  ? document.keywords.map((k) => <span key={k} className="chip">{k}</span>)
                  : <span className="subtle">—</span>}
              </div>
            </dd>
          </dl>
          {canManage && <div style={{ marginTop: 12 }}><ClassificationEditor document={document} onChanged={changed} /></div>}
        </section>

        <section className="drawer-section">
          <h3>Datos sensibles detectados (enmascarados)</h3>
          <FindingsList findings={document.sensitive_findings} />
        </section>

        <VersionsPanel document={document} canManage={canManage} onChanged={changed} />

        <section className="drawer-section">
          <h3>Seguridad</h3>
          <dl className="kv">
            <dt>Cifrado</dt><dd>AES-256-GCM · llave única por versión</dd>
            <dt>Llave maestra</dt><dd>{document.key_version ? `Versión ${document.key_version} del llavero` : "Llave raíz (sin rotaciones)"}</dd>
            <dt>Integridad</dt><dd className="mono">{document.sha256}</dd>
            <dt>Tamaño</dt><dd>{formatBytes(document.size_bytes)}</dd>
            <dt>Propietario</dt><dd>{document.owner_username}</dd>
            <dt>Actualizado</dt><dd>{formatDateTime(document.uploaded_at)}</dd>
            <dt>Tu acceso</dt><dd>{document.my_access === "manage" ? "Gestión" : "Lectura"}</dd>
            <dt>ID</dt><dd className="mono">{document.id}</dd>
          </dl>
        </section>

        {canManage && <SharePanel key={document.sensitivity} document={document} users={users} />}
      </div>

      {confirming && (
        <ConfirmDialog
          title="¿Enviar a la papelera?"
          confirmLabel="Enviar a la papelera"
          danger
          busy={deleting}
          onConfirm={remove}
          onCancel={() => setConfirming(false)}
        >
          “{document.original_name}” dejará de estar disponible para todos. Podrás restaurarlo desde la Papelera durante 30 días.
        </ConfirmDialog>
      )}
    </Drawer>
  );
}
