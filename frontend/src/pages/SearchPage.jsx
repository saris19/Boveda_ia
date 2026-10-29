import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import DocumentDrawer from "../components/DocumentDrawer";
import Icon from "../components/Icon";
import { EmptyState, FileIcon, PageHeader, SensitivityBadge, Spinner } from "../components/ui";
import { CATEGORIES, SENSITIVITY, SENSITIVITY_ORDER, formatDate } from "../utils/format";

const SUGGESTIONS = ["factura", "paciente", "contrato laboral", "firewall", "cédula", "pago a proveedores"];

function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") || "");
  const [filters, setFilters] = useState({ category: "", sensitivity: "", date_from: "", date_to: "" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const query = useDebounced(text);
  const lastWrittenQuery = useRef(params.get("q") || "");
  const hasFilters = Object.values(filters).some(Boolean);

  // Keep the box in sync when a new search arrives from the top bar (not from our own URL updates).
  const urlQuery = params.get("q") || "";
  useEffect(() => {
    if (urlQuery !== lastWrittenQuery.current) {
      lastWrittenQuery.current = urlQuery;
      setText(urlQuery);
    }
  }, [urlQuery]);

  useEffect(() => {
    if (!query.trim() && !hasFilters) {
      setData(null);
      return;
    }
    let alive = true;
    setLoading(true);
    setError("");
    lastWrittenQuery.current = query.trim();
    setParams(query.trim() ? { q: query.trim() } : {}, { replace: true });
    api
      .search({ q: query.trim(), ...filters })
      .then((result) => alive && setData(result))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, filters]);

  const setFilter = (key) => (event) => setFilters((f) => ({ ...f, [key]: event.target.value }));

  return (
    <>
      <PageHeader
        eyebrow="IA · Índice ciego"
        title="Búsqueda inteligente"
        description="Busca dentro del contenido de los archivos cifrados, por nombre, categoría o palabras clave. Tolera errores de escritura y entiende de qué tema hablas."
      />

      <div className="search-box">
        <Icon name="search" size={20} />
        <input className="input input-lg" placeholder="Ej: factura de proveedor, historia clínica, contrato…"
          value={text} onChange={(e) => setText(e.target.value)} aria-label="Buscar" autoFocus />
      </div>

      <div className="search-filters">
        <label className="field"><span>Categoría</span>
          <select className="select" value={filters.category} onChange={setFilter("category")}>
            <option value="">Todas</option>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className="field"><span>Sensibilidad</span>
          <select className="select" value={filters.sensitivity} onChange={setFilter("sensitivity")}>
            <option value="">Todas</option>
            {SENSITIVITY_ORDER.map((s) => <option key={s} value={s}>{SENSITIVITY[s].label}</option>)}
          </select>
        </label>
        <label className="field"><span>Desde</span><input type="date" className="input" value={filters.date_from} onChange={setFilter("date_from")} /></label>
        <label className="field"><span>Hasta</span><input type="date" className="input" value={filters.date_to} onChange={setFilter("date_to")} /></label>
        {hasFilters && (
          <button className="btn btn-ghost" onClick={() => setFilters({ category: "", sensitivity: "", date_from: "", date_to: "" })}>
            Limpiar filtros
          </button>
        )}
      </div>

      {data?.intent && (
        <div className="intent">
          <Icon name="sparkles" />
          <span>La IA relaciona tu búsqueda con <b>{data.intent.category}</b> ({Math.round(data.intent.confidence * 100)}% de probabilidad) y prioriza esos documentos.</span>
        </div>
      )}

      {error && <p className="form-error" style={{ marginTop: 20 }}><Icon name="alert" size={16} /> {error}</p>}

      {!data && !loading && !error && (
        <>
          <EmptyState icon="search" title="¿Qué estás buscando?">
            Prueba con alguna de estas búsquedas:
          </EmptyState>
          <div className="suggestions" style={{ marginTop: -40, marginBottom: 8 }}>
            {SUGGESTIONS.map((s) => (
              <button key={s} className="btn btn-secondary btn-sm" onClick={() => setText(s)}>{s}</button>
            ))}
          </div>
          <div className="how">
            <div><b>1 · Contenido cifrado</b><span>Cada palabra del archivo se guarda como un código HMAC irreversible: se puede buscar sin descifrar ni guardar el texto.</span></div>
            <div><b>2 · Metadatos con tolerancia</b><span>Nombre, categoría y palabras clave, aceptando plurales y errores de escritura.</span></div>
            <div><b>3 · Intención con IA</b><span>El clasificador entiende el tema de la búsqueda y sugiere documentos relacionados.</span></div>
          </div>
        </>
      )}

      {(data || loading) && (
        <div className={loading && data ? "refetching" : ""}>
          <div className="results-meta">
            <span>{loading && !data ? <Spinner label="Buscando…" /> : `${data.total} resultado${data.total === 1 ? "" : "s"}`}</span>
            {data?.total > 0 && <span className="subtle" style={{ fontSize: 13 }}>Ordenados por relevancia</span>}
          </div>
          {data && data.total === 0 && (
            <EmptyState icon="search" title="Sin resultados">
              No encontramos documentos para esa búsqueda entre los que tienes acceso. Revisa los filtros o prueba otras palabras.
            </EmptyState>
          )}
          {data?.results.map(({ document, score, reasons, matched_terms }) => (
            <button key={document.id} className="result" onClick={() => setSelected(document)}>
              <div style={{ display: "flex", gap: 14, minWidth: 0 }}>
                <FileIcon name={document.original_name} />
                <div style={{ minWidth: 0 }}>
                  <h3>{document.original_name} <SensitivityBadge level={document.sensitivity} /></h3>
                  <div className="subtle" style={{ fontSize: 13 }}>
                    {document.category} · {document.owner_username} · {formatDate(document.uploaded_at)}
                  </div>
                  <div className="reasons">
                    {reasons.map((reason) => <span key={reason}><Icon name="check" size={14} /> {reason}</span>)}
                  </div>
                  {matched_terms.length > 0 && (
                    <div className="chips" style={{ marginTop: 10 }}>
                      {matched_terms.map((term) => <span key={term} className="chip chip-accent">{term}</span>)}
                    </div>
                  )}
                </div>
              </div>
              {query.trim() && (
                <div className="relevance">
                  <span className="subtle" style={{ fontSize: 12 }}>Relevancia</span>
                  <b>{Math.round(score * 100)}%</b>
                  <div className="risk-track"><div className="risk-fill" style={{ width: `${Math.max(score * 100, 3)}%`, background: "var(--series-1)" }} /></div>
                </div>
              )}
            </button>
          ))}
        </div>
      )}

      {selected && <DocumentDrawer document={selected} onClose={() => setSelected(null)}
        onUpdated={(updated) => setData((d) => d && { ...d, results: d.results.map((r) => (r.document.id === updated.id ? { ...r, document: updated } : r)) })}
        onDeleted={() => setData((d) => d && { ...d, results: d.results.filter((r) => r.document.id !== selected.id), total: d.total - 1 })} />}
    </>
  );
}
