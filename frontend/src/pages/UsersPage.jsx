import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import Icon from "../components/Icon";
import { ErrorState, PageHeader, SkeletonRows, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { ROLE_LABELS, formatDate, isFuture } from "../utils/format";

const EMPTY_FORM = { username: "", full_name: "", password: "", role: "viewer" };
const PASSWORD_RULES = [
  [(p) => p.length >= 8, "8+ caracteres"],
  [(p) => /[A-Z]/.test(p), "mayúscula"],
  [(p) => /[a-z]/.test(p), "minúscula"],
  [(p) => /\d/.test(p), "número"],
  [(p) => /[^A-Za-z0-9]/.test(p), "símbolo"],
];

export default function UsersPage() {
  const { user: me } = useAuth();
  const notify = useToast();
  const [users, setUsers] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setError("");
    api.listUsers().then(setUsers).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const create = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      await api.createUser(form);
      notify(`Usuario ${form.username} creado`);
      setForm(EMPTY_FORM);
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const update = async (target, payload) => {
    try {
      await api.updateUser(target.id, payload);
      notify(`Usuario ${target.username} actualizado`);
    } catch (e) {
      notify(e.message, "error");
    }
    load();
  };

  const unblock = async (target) => {
    try {
      await api.unblockUser(target.id);
      notify(`Bloqueos de ${target.username} retirados`);
    } catch (e) {
      notify(e.message, "error");
    }
    load();
  };

  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }));

  return (
    <>
      <PageHeader eyebrow="Administración" title="Usuarios y roles"
        description="Administrador: control total · Editor: sube, comparte y elimina lo suyo · Lector: solo lo que le comparten." />

      <form className="card card-pad" onSubmit={create} style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 15.5, marginBottom: 16 }}>Nuevo usuario</h2>
        <div className="form-grid">
          <label className="field"><span>Usuario</span><input className="input" value={form.username} onChange={set("username")} required pattern="[a-zA-Z0-9_.\-]{3,50}" /></label>
          <label className="field"><span>Nombre completo</span><input className="input" value={form.full_name} onChange={set("full_name")} /></label>
          <label className="field"><span>Contraseña</span><input className="input" type="password" value={form.password} onChange={set("password")} required autoComplete="new-password" /></label>
          <label className="field"><span>Rol</span>
            <select className="select" value={form.role} onChange={set("role")}>
              {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <button className="btn btn-primary" disabled={saving}>{saving ? <Spinner label="Creando…" /> : <><Icon name="plus" size={16} /> Crear usuario</>}</button>
        </div>
        <div className="chips" style={{ marginTop: 14 }}>
          {PASSWORD_RULES.map(([test, label]) => {
            const ok = form.password && test(form.password);
            return <span key={label} className={`chip ${ok ? "chip-accent" : ""}`}>{ok ? "✓ " : ""}{label}</span>;
          })}
        </div>
      </form>

      <section className="card">
        {error ? <ErrorState message={error} onRetry={load} /> : !users ? <SkeletonRows /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Estado</th><th>Creado</th><th /></tr></thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td><div className="file-cell" style={{ minWidth: 0 }}><span className="avatar">{u.username.slice(0, 2)}</span><b className="mono">{u.username}</b></div></td>
                    <td>{u.full_name || <span className="subtle">—</span>}</td>
                    <td>
                      <select className="select" style={{ width: "auto", height: 32 }} value={u.role} disabled={u.id === me?.id || u.username === me?.username}
                        onChange={(e) => update(u, { role: e.target.value })} aria-label={`Rol de ${u.username}`}>
                        {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </td>
                    <td>
                      <div className="chips">
                        {u.is_active
                          ? <span className="badge badge-publico"><span className="dot" />Activo</span>
                          : <span className="badge"><span className="dot" />Inactivo</span>}
                        {isFuture(u.locked_until) && <span className="badge badge-restringido"><span className="dot" />Cuenta bloqueada</span>}
                        {isFuture(u.downloads_blocked_until) && <span className="badge badge-confidencial"><span className="dot" />Descargas pausadas</span>}
                      </div>
                    </td>
                    <td className="subtle">{formatDate(u.created_at)}</td>
                    <td className="right">
                      {(isFuture(u.locked_until) || isFuture(u.downloads_blocked_until)) && (
                        <button className="btn btn-secondary btn-sm" onClick={() => unblock(u)}><Icon name="unlock" size={14} /> Desbloquear</button>
                      )}{" "}
                      {u.username !== me?.username && (
                        <button className="btn btn-ghost btn-sm" onClick={() => update(u, { is_active: !u.is_active })}>
                          {u.is_active ? "Desactivar" : "Activar"}
                        </button>
                      )}
                    </td>
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
