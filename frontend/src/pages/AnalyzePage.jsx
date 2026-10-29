import { useState } from "react";
import { api } from "../api/client";
import BarList from "../components/charts/BarList";
import Dropzone from "../components/Dropzone";
import { FindingsList, PageHeader, RiskMeter, SensitivityBadge, StatCard } from "../components/ui";
import { useToast } from "../context/ToastContext";

export default function AnalyzePage() {
  const notify = useToast();
  const [result, setResult] = useState(null);
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);

  const analyze = async (file) => {
    setBusy(true);
    setFileName(file.name);
    try {
      setResult(await api.analyzeFile(file));
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const scores = Object.entries(result?.category_scores || {})
    .slice(0, 5)
    .map(([label, value]) => ({ label, value: Math.round(value * 100) }));

  return (
    <>
      <PageHeader
        eyebrow="IA"
        title="Analizar con IA"
        description="Prueba la clasificación y la detección de datos sensibles. El archivo no se guarda: se analiza en memoria y se descarta."
      />
      <Dropzone onFile={analyze} busy={busy} step={1} title="Suelta un archivo para analizarlo sin guardarlo" />

      {result && !busy && (
        <div className="section">
          <p className="muted" style={{ marginBottom: 12 }}>Resultado para <b>{fileName}</b></p>
          <div className="stats" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
            <StatCard icon="sparkles" label="Categoría" value={result.category}
              foot={`${Math.round(result.category_confidence * 100)}% de confianza`} />
            <div className="stat">
              <div className="stat-label">Nivel de sensibilidad</div>
              <div style={{ margin: "8px 0" }}><SensitivityBadge level={result.sensitivity} /></div>
              <div className="stat-foot">Determina quién debería verlo</div>
            </div>
            <div className="stat">
              <div className="stat-label">Puntaje de riesgo</div>
              <div className="stat-value">{result.risk_score}<small>/100</small></div>
              <RiskMeter score={result.risk_score} />
            </div>
          </div>
          <div className="grid grid-2">
            <section className="card">
              <div className="card-head"><div><h2>Probabilidad por categoría</h2><p>Modelo TF-IDF + Naive Bayes · porcentaje</p></div></div>
              <div className="card-body"><BarList items={scores} /></div>
            </section>
            <section className="card">
              <div className="card-head"><div><h2>Datos sensibles</h2><p>Valores enmascarados</p></div></div>
              <div className="card-body"><FindingsList findings={result.sensitive_findings} /></div>
            </section>
          </div>
        </div>
      )}
    </>
  );
}
