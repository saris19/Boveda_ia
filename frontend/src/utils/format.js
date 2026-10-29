export const ROLE_LABELS = { admin: "Administrador", editor: "Editor", viewer: "Lector" };

export const SENSITIVITY = {
  publico: { label: "Público", color: "var(--good)" },
  interno: { label: "Interno", color: "var(--info)" },
  confidencial: { label: "Confidencial", color: "var(--warning)" },
  restringido: { label: "Restringido", color: "var(--critical)" },
};
export const SENSITIVITY_ORDER = ["publico", "interno", "confidencial", "restringido"];

export const CATEGORIES = [
  "Financiero",
  "Legal",
  "Recursos Humanos",
  "Salud",
  "Técnico / TI",
  "Académico",
  "Administrativo",
  "Sin clasificar",
];

export const ACTION_LABELS = {
  login: "Inicio de sesión",
  upload: "Subida",
  download: "Descarga",
  view: "Consulta",
  share: "Compartir",
  revoke: "Revocar acceso",
  delete: "Eliminación",
  search: "Búsqueda",
  user_create: "Usuario creado",
  user_update: "Usuario editado",
  user_unblock: "Usuario desbloqueado",
  view_permissions: "Ver permisos",
  new_version: "Nueva versión",
  restore_version: "Versión restaurada",
  restore: "Restaurado de papelera",
  purge: "Eliminado definitivo",
  classify: "Corrección de IA",
  alert_update: "Gestión de alerta",
  key_rotation: "Rotación de llave",
  model_retrain: "Reentrenamiento",
};

export const SEVERITY = {
  baja: { label: "Baja", color: "var(--info)" },
  media: { label: "Media", color: "var(--warning)" },
  alta: { label: "Alta", color: "var(--serious)" },
  critica: { label: "Crítica", color: "var(--critical)" },
};
export const SEVERITY_ORDER = ["critica", "alta", "media", "baja"];

export const ALERT_STATUS = {
  abierta: "Abierta",
  en_revision: "En revisión",
  resuelta: "Resuelta",
  falso_positivo: "Falso positivo",
};

export function isFuture(value) {
  const date = parseDate(value);
  return Boolean(date && date.getTime() > Date.now());
}

// Mirrors backend/app/services/policy_service.py
export function roleShareAllowed(sensitivity, role) {
  if (sensitivity === "restringido") return false;
  if (sensitivity === "confidencial") return role === "editor" || role === "admin";
  return true;
}

export function formatBytes(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

// The API returns UTC timestamps; SQLite drops the timezone, so treat naive values as UTC.
export function parseDate(value) {
  if (!value) return null;
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

export function formatDateTime(value) {
  const date = parseDate(value);
  return date ? date.toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" }) : "—";
}

export function formatDate(value) {
  const date = parseDate(value);
  return date ? date.toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" }) : "—";
}

export function timeAgo(value) {
  const date = parseDate(value);
  if (!date) return "";
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  const units = [
    ["año", 31536000],
    ["mes", 2592000],
    ["día", 86400],
    ["hora", 3600],
    ["minuto", 60],
  ];
  for (const [unit, size] of units) {
    const amount = Math.floor(seconds / size);
    if (amount >= 1) {
      const plural = amount === 1 ? unit : unit === "mes" ? "meses" : `${unit}s`;
      return `hace ${amount} ${plural}`;
    }
  }
  return "hace un momento";
}

export function fileExtension(name = "") {
  const parts = name.split(".");
  return parts.length > 1 ? parts.pop().slice(0, 4) : "doc";
}

export function riskColor(score) {
  if (score >= 60) return "var(--critical)";
  if (score >= 30) return "var(--warning)";
  if (score > 0) return "var(--info)";
  return "var(--good)";
}

export function percent(part, total) {
  return total ? Math.round((part / total) * 100) : 0;
}
