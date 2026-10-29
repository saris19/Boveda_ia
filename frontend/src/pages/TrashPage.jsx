import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import Icon from "../components/Icon";
import { ConfirmDialog, EmptyState, ErrorState, FileIcon, PageHeader, SensitivityBadge, SkeletonRows } from "../components/ui";
import { useToast } from "../context/ToastContext";
import { formatBytes, formatDateTime, parseDate } from "../utils/format";

function daysLeft(value) {
  const date = parseDate(value);
  return date ? Math.max(0, Math.ceil((date.getTime() - Date.now()) / 86400000)) : 0;
}

export default function TrashPage() {
  const notify = useToast();
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [purging, setPurging] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setError("");
    api.listTrash().then(setItems).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const restore = async (item) => {
    try {
      await api.restoreFromTrash(item.id);
      notify(`“${item.original_name}” restaurado`);
      load();
    } catch (e) {
      notify(e.message, "error");
    }
  };

  const purge = async () => {
    setBusy(true);
    try {
      await api.purgeFromTrash(purging.id);
      notify(`“${purging.original_name}” eliminado definitivamente`);
      setPurging(null);
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader eyebrow="Bóveda" title="Papelera"
        description="Los documentos eliminados se conservan cifrados 30 días. Después se borran automáticamente junto con todas sus versiones." />
      <section className="card">
        {error ? <ErrorState message={error} onRetry={load} /> : !items ? <SkeletonRows /> : items.length === 0 ? (
          <EmptyState icon="trash" title="La papelera está vacía">Lo que envíes a la papelera aparecerá aquí.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Documento</th><th>Sensibilidad</th><th>Eliminado</th><th>Se borra en</th><th /></tr></thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="file-cell">
                        <FileIcon name={item.original_name} />
                        <div><b>{item.original_name}</b><span>{item.owner_username} · {formatBytes(item.size_bytes)} · v{item.version_number}</span></div>
                      </div>
                    </td>
                    <td><SensitivityBadge level={item.sensitivity} /></td>
                    <td className="subtle">{formatDateTime(item.deleted_at)}<br />por {item.deleted_by_username || "—"}</td>
                    <td className="num">{daysLeft(item.purge_at)} días</td>
                    <td className="right" style={{ whiteSpace: "nowrap" }}>
                      <button className="btn btn-secondary btn-sm" onClick={() => restore(item)}><Icon name="history" size={15} /> Restaurar</button>{" "}
                      <button className="btn btn-ghost btn-sm" onClick={() => setPurging(item)}>Eliminar definitivamente</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {purging && (
        <ConfirmDialog title="¿Eliminar definitivamente?" danger busy={busy} confirmLabel="Eliminar para siempre"
          onConfirm={purge} onCancel={() => setPurging(null)}>
          Se borrarán “{purging.original_name}” y todas sus versiones cifradas. Esta acción no se puede deshacer.
        </ConfirmDialog>
      )}
    </>
  );
}
