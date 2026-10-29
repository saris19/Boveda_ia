import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import DocumentDrawer from "../components/DocumentDrawer";
import Dropzone from "../components/Dropzone";
import Icon from "../components/Icon";
import { EmptyState, ErrorState, FileIcon, PageHeader, RiskMeter, SensitivityBadge, SkeletonRows } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { CATEGORIES, SENSITIVITY, SENSITIVITY_ORDER, formatBytes, formatDate } from "../utils/format";

export function useUploader(onUploaded) {
  const notify = useToast();
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const timer = useRef(null);

  const upload = async (file) => {
    setBusy(true);
    setStep(0);
    // The pipeline runs server-side in one request; the steps show what is happening meanwhile.
    timer.current = setInterval(() => setStep((s) => Math.min(s + 1, 3)), 700);
    try {
      const document = await api.uploadDocument(file);
      notify(`“${document.original_name}” cifrado · ${document.category} · ${SENSITIVITY[document.sensitivity].label}`);
      onUploaded(document);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      clearInterval(timer.current);
      setBusy(false);
    }
  };
  useEffect(() => () => clearInterval(timer.current), []);
  return { upload, busy, step };
}

export default function DocumentsPage() {
  const { canUpload } = useAuth();
  const [params, setParams] = useSearchParams();
  const [documents, setDocuments] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [showUpload, setShowUpload] = useState(params.get("subir") === "1");
  const [filter, setFilter] = useState("");
  const [category, setCategory] = useState("");
  const [sensitivity, setSensitivity] = useState("");

  const load = useCallback(() => {
    setError("");
    return api.listDocuments().then(setDocuments).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const { upload, busy, step } = useUploader((document) => {
    load();
    setSelected(document);
    setShowUpload(false);
    if (params.get("subir")) setParams({});
  });

  const visible = useMemo(() => {
    const text = filter.trim().toLowerCase();
    return (documents || []).filter(
      (d) =>
        (!text || d.original_name.toLowerCase().includes(text) || d.owner_username.toLowerCase().includes(text)) &&
        (!category || d.category === category) &&
        (!sensitivity || d.sensitivity === sensitivity),
    );
  }, [documents, filter, category, sensitivity]);

  return (
    <>
      <PageHeader
        eyebrow="Bóveda"
        title="Documentos"
        description="Todo se cifra antes de guardarse. La IA analiza el contenido solo en memoria."
        actions={canUpload && (
          <button className="btn btn-primary" onClick={() => setShowUpload((v) => !v)}>
            <Icon name={showUpload ? "close" : "upload"} size={16} /> {showUpload ? "Cerrar" : "Subir documento"}
          </button>
        )}
      />

      {canUpload && (showUpload || documents?.length === 0) && (
        <div style={{ marginBottom: 24 }}>
          <Dropzone onFile={upload} busy={busy} step={step} />
        </div>
      )}

      <section className="card">
        <div className="toolbar">
          <input className="input grow" placeholder="Filtrar por nombre o propietario…" value={filter}
            onChange={(e) => setFilter(e.target.value)} aria-label="Filtrar documentos" />
          <select className="select" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Categoría">
            <option value="">Todas las categorías</option>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select className="select" value={sensitivity} onChange={(e) => setSensitivity(e.target.value)} aria-label="Sensibilidad">
            <option value="">Toda sensibilidad</option>
            {SENSITIVITY_ORDER.map((s) => <option key={s} value={s}>{SENSITIVITY[s].label}</option>)}
          </select>
          {documents && <span className="subtle" style={{ fontSize: 13 }}>{visible.length} de {documents.length}</span>}
        </div>

        {error ? (
          <ErrorState message={error} onRetry={load} />
        ) : !documents ? (
          <SkeletonRows />
        ) : documents.length === 0 ? (
          <EmptyState title="Aún no hay documentos">
            {canUpload ? "Sube tu primer archivo con el recuadro de arriba." : "Cuando alguien comparta un documento contigo aparecerá aquí."}
          </EmptyState>
        ) : visible.length === 0 ? (
          <EmptyState icon="filter" title="Ningún documento coincide con los filtros"
            action={<button className="btn btn-secondary" onClick={() => { setFilter(""); setCategory(""); setSensitivity(""); }}>Limpiar filtros</button>} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Documento</th><th>Categoría IA</th><th>Sensibilidad</th><th>Riesgo</th><th className="right">Tamaño</th><th>Subido</th></tr>
              </thead>
              <tbody>
                {visible.map((d) => (
                  <tr key={d.id} className="clickable" tabIndex={0} onClick={() => setSelected(d)}
                    onKeyDown={(e) => e.key === "Enter" && setSelected(d)}>
                    <td>
                      <div className="file-cell">
                        <FileIcon name={d.original_name} />
                        <div><b>{d.original_name}</b><span>{d.owner_username}</span></div>
                      </div>
                    </td>
                    <td>{d.category}</td>
                    <td><SensitivityBadge level={d.sensitivity} /></td>
                    <td><RiskMeter score={d.risk_score} /></td>
                    <td className="right num mono">{formatBytes(d.size_bytes)}</td>
                    <td className="subtle" style={{ whiteSpace: "nowrap" }}>{formatDate(d.uploaded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selected && (
        <DocumentDrawer document={selected} onClose={() => setSelected(null)}
          onDeleted={(id) => setDocuments((list) => list.filter((d) => d.id !== id))}
          onUpdated={(updated) => setDocuments((list) => list.map((d) => (d.id === updated.id ? updated : d)))} />
      )}
    </>
  );
}
