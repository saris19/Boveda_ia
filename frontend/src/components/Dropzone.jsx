import { useRef, useState } from "react";
import Icon from "./Icon";

const ACCEPT = ".txt,.md,.csv,.pdf,.docx";
const STEPS = ["Leyendo archivo", "Analizando con IA", "Cifrando AES-256", "Guardando"];

export default function Dropzone({ onFile, busy, step = 0, title = "Arrastra un archivo o haz clic para seleccionarlo" }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const pick = (file) => {
    if (file && !busy) onFile(file);
  };

  return (
    <div
      className={`dropzone ${dragging ? "is-drag" : ""} ${busy ? "is-busy" : ""}`}
      role="button"
      tabIndex={0}
      aria-busy={busy}
      aria-label="Subir documento"
      onClick={() => !busy && inputRef.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), inputRef.current?.click())}
      onDragOver={(e) => (e.preventDefault(), setDragging(true))}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        pick(e.dataTransfer.files[0]);
      }}
    >
      <div className="icon-circle">{busy ? <span className="spinner" /> : <Icon name="upload" size={20} />}</div>
      {busy ? (
        <>
          <b>Procesando documento…</b>
          <div className="progress-steps">
            {STEPS.map((label, index) => (
              <span key={label} className={index < step ? "done" : index === step ? "now" : ""}>
                {index < step ? "✓ " : ""}{label}
              </span>
            ))}
          </div>
        </>
      ) : (
        <>
          <b>{title}</b>
          <span className="subtle mono" style={{ fontSize: 12.5 }}>.txt · .md · .csv · .pdf · .docx — máximo 10 MB</span>
        </>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          pick(e.target.files[0]);
          e.target.value = "";
        }}
      />
    </div>
  );
}
