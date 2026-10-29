import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import BarList from "../components/charts/BarList";
import Icon from "../components/Icon";
import { ConfirmDialog, ErrorState, PageHeader, SensitivityBadge, SkeletonRows, Spinner } from "../components/ui";
import { useToast } from "../context/ToastContext";
import { formatDateTime, timeAgo } from "../utils/format";

const FEATURE_LABELS = {
  hour_sin: "hora del día (seno)",
  hour_cos: "hora del día (coseno)",
  is_weekend: "fin de semana",
  is_failure: "acción rechazada",
  action_risk: "impacto de la acción",
  events_10m: "acciones en 10 min",
  downloads_60m: "descargas en 1 h",
  failures_60m: "fallos en 1 h",
  distinct_docs_60m: "documentos distintos en 1 h",
  new_ip: "IP nueva",
  sensitivity: "sensibilidad del documento",
  hour_deviation: "desvío de su horario habitual",
};

export default function SecurityCenterPage() {
  const notify = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [confirmRotate, setConfirmRotate] = useState(false);
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    setError("");
    api.securityOverview().then(setData).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const rotate = async () => {
    setBusy("rotate");
    try {
      const result = await api.rotateMasterKey();
      notify(`Llave rotada a la versión ${result.new_version}: ${result.rewrapped_keys} llaves de documento re-envueltas`);
      setConfirmRotate(false);
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy("");
    }
  };

  const retrainClassifier = async () => {
    setBusy("classifier");
    try {
      await api.retrainClassifier();
      notify("Clasificador reentrenado");
      load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy("");
    }
  };

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <><PageHeader eyebrow="Administración" title="Centro de seguridad" /><div className="card"><SkeletonRows /></div></>;

  const { keyring, classifier, anomaly_model: anomaly, policies } = data;
  const byVersion = Object.entries(keyring.documents_by_key_version).map(([version, value]) => ({
    label: version === "0" ? "Llave raíz" : `Versión ${version}`,
    value,
  }));

  return (
    <>
      <PageHeader eyebrow="Administración" title="Centro de seguridad"
        description="Jerarquía de llaves y rotación, modelos de inteligencia artificial y políticas de acceso por sensibilidad." />

      <div className="grid grid-2">
        <section className="card">
          <div className="card-head"><div><h2>Llaves de cifrado</h2><p>Cifrado de sobre con llavero rotativo</p></div></div>
          <div className="card-body">
            <div className="key-chain" aria-label="Jerarquía de llaves">
              <div><Icon name="key" size={16} /> <span><b>Llave raíz</b> · variable VAULT_MASTER_KEY (nunca se guarda en la base de datos)</span></div>
              <div><Icon name="key" size={16} /> <span><b>Llave maestra v{keyring.active_version}</b> · {keyring.active_version ? "en el llavero, envuelta con la raíz" : "aún no se ha rotado"}</span></div>
              <div><Icon name="lock" size={16} /> <span><b>Llave de cada documento</b> · aleatoria, envuelta con la maestra</span></div>
              <div><Icon name="file" size={16} /> <span><b>Contenido</b> · AES-256-GCM</span></div>
            </div>
            <div className="mini-kv">
              <div><span>Versión activa</span><b>{keyring.active_version}</b></div>
              <div><span>Rotaciones realizadas</span><b className="num">{keyring.rotations}</b></div>
              <div><span>Última rotación</span><b>{keyring.last_rotation ? formatDateTime(keyring.last_rotation) : "—"}</b></div>
            </div>
            {byVersion.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <p className="subtle" style={{ fontSize: 13, marginBottom: 8 }}>Documentos por versión de llave</p>
                <BarList items={byVersion} />
              </div>
            )}
            <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => setConfirmRotate(true)}>
              <Icon name="refresh" size={16} /> Rotar llave maestra
            </button>
          </div>
        </section>

        <section className="card">
          <div className="card-head"><div><h2>Clasificador de documentos</h2><p>{classifier.algorithm}</p></div></div>
          <div className="card-body">
            <div className="stats" style={{ gridTemplateColumns: "1fr 1fr", marginBottom: 16 }}>
              <div className="stat"><div className="stat-label">Exactitud (validación cruzada 5)</div>
                <div className="stat-value">{Math.round(classifier.cv_accuracy * 100)}<small>%</small></div></div>
              <div className="stat"><div className="stat-label">Ejemplos de entrenamiento</div>
                <div className="stat-value">{classifier.seed_samples + classifier.feedback_samples}</div>
                <div className="stat-foot">{classifier.feedback_samples} correcciones humanas</div></div>
            </div>
            <div className="mini-kv" style={{ marginTop: 0 }}>
              <div><span>Entrenado</span><b>{timeAgo(classifier.trained_at)}</b></div>
              <div><span>Categorías</span><b>{classifier.categories.length}</b></div>
            </div>
            {classifier.corrections.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <p className="subtle" style={{ fontSize: 13, marginBottom: 6 }}>Correcciones recibidas</p>
                {classifier.corrections.map((c) => (
                  <div key={`${c.from}-${c.to}`} className="list-row" style={{ fontSize: 13.5 }}>
                    <span>{c.from} → <b>{c.to}</b></span><span className="num">{c.count}</span>
                  </div>
                ))}
              </div>
            )}
            <button className="btn btn-secondary" style={{ marginTop: 16 }} onClick={retrainClassifier} disabled={busy === "classifier"}>
              {busy === "classifier" ? <Spinner label="Entrenando…" /> : <><Icon name="cpu" size={16} /> Reentrenar con las correcciones</>}
            </button>
          </div>
        </section>
      </div>

      <section className="card section">
        <div className="card-head"><div><h2>Detector de accesos sospechosos</h2><p>{anomaly.algorithm}</p></div></div>
        <div className="card-body">
          <div className="mini-kv" style={{ marginTop: 0, paddingTop: 0, borderTop: "none", maxWidth: 520 }}>
            <div><span>Entrenado</span><b>{anomaly.trained ? timeAgo(anomaly.trained_at) : "—"}</b></div>
            <div><span>Eventos reales de la bitácora</span><b className="num">{anomaly.real_events}</b></div>
            <div><span>Línea base sintética (arranque en frío)</span><b className="num">{anomaly.synthetic_events}</b></div>
          </div>
          <p className="subtle" style={{ fontSize: 13, margin: "16px 0 8px" }}>Variables que analiza en cada evento</p>
          <div className="feature-chips">
            {(anomaly.features || []).map((f) => <span key={f} className="chip">{FEATURE_LABELS[f] || f}</span>)}
          </div>
        </div>
      </section>

      <section className="card section">
        <div className="card-head"><div><h2>Políticas por nivel de sensibilidad</h2><p>Se aplican automáticamente según la clasificación de la IA</p></div></div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Nivel</th><th>Compartir con un rol completo</th><th>Quién puede acceder</th></tr></thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.level}><td><SensitivityBadge level={p.level} /></td><td>{p.role_sharing}</td><td className="muted">{p.access}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {confirmRotate && (
        <ConfirmDialog title="¿Rotar la llave maestra?" confirmLabel="Rotar ahora" busy={busy === "rotate"}
          onConfirm={rotate} onCancel={() => setConfirmRotate(false)}>
          Se generará una nueva llave maestra y se volverán a envolver las llaves de todos los documentos y versiones.
          El contenido cifrado no cambia y los documentos siguen disponibles durante el proceso.
        </ConfirmDialog>
      )}
    </>
  );
}
