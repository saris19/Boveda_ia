// HTTP client for the Bóveda IA API.
// The token lives in sessionStorage: it survives page reloads but is discarded when the tab closes.

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const SESSION_KEY = "boveda.session";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

let unauthorizedHandler = null;
export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

export function loadSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION_KEY));
  } catch {
    return null;
  }
}

export function saveSession(session) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    /* private mode: the session simply won't survive a reload */
  }
}

export function clearSession() {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

function describeError(body, status) {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) return "Datos inválidos: revisa los campos del formulario.";
  if (status >= 500) return "El servidor tuvo un problema. Intenta de nuevo en unos segundos.";
  return `Error ${status}`;
}

async function request(path, { method = "GET", json, form, body, raw = false, auth = true } = {}) {
  const headers = {};
  const session = loadSession();
  if (auth && session?.token) headers.Authorization = `Bearer ${session.token}`;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }

  let response;
  try {
    response = await fetch(API_URL + path, { method, headers, body });
  } catch {
    throw new ApiError("No se pudo conectar con el servidor. Revisa tu conexión o intenta de nuevo.", 0);
  }

  if (response.status === 401 && auth && session?.token) {
    clearSession();
    unauthorizedHandler?.();
    throw new ApiError("Tu sesión expiró. Inicia sesión de nuevo.", 401);
  }
  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(describeError(payload, response.status), response.status);
  }
  if (raw) return response;
  return response.status === 204 ? null : response.json();
}

function toQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

function fileForm(file) {
  const form = new FormData();
  form.append("file", file);
  return form;
}

export const api = {
  health: () => request("/api/health", { auth: false }),
  login: (username, password) =>
    request("/api/auth/login", {
      method: "POST",
      auth: false,
      body: new URLSearchParams({ username, password }),
    }),
  me: () => request("/api/auth/me"),

  // tzOffset: minutes to add to UTC to get the viewer's local time (so "today" matches their clock)
  stats: (tzOffset = 0) => request(`/api/stats${toQuery({ tz_offset: tzOffset })}`),

  listDocuments: () => request("/api/documents"),
  uploadDocument: (file) => request("/api/documents", { method: "POST", form: fileForm(file) }),
  analyzeFile: (file) => request("/api/documents/analyze", { method: "POST", form: fileForm(file) }),
  deleteDocument: (id) => request(`/api/documents/${id}`, { method: "DELETE" }),
  listPermissions: (id) => request(`/api/documents/${id}/permissions`),
  shareDocument: (id, payload) => request(`/api/documents/${id}/share`, { method: "POST", json: payload }),
  revokePermission: (id, permissionId) =>
    request(`/api/documents/${id}/permissions/${permissionId}`, { method: "DELETE" }),
  async downloadDocument(document, versionNumber) {
    const path = versionNumber
      ? `/api/documents/${document.id}/versions/${versionNumber}/download`
      : `/api/documents/${document.id}/download`;
    const response = await request(path, { raw: true });
    const url = URL.createObjectURL(await response.blob());
    const link = Object.assign(window.document.createElement("a"), { href: url, download: document.original_name });
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
  listVersions: (id) => request(`/api/documents/${id}/versions`),
  uploadVersion: (id, file) => request(`/api/documents/${id}/versions`, { method: "POST", form: fileForm(file) }),
  restoreVersion: (id, number) => request(`/api/documents/${id}/versions/${number}/restore`, { method: "POST" }),
  updateClassification: (id, payload) =>
    request(`/api/documents/${id}/classification`, { method: "PATCH", json: payload }),

  listTrash: () => request("/api/trash"),
  restoreFromTrash: (id) => request(`/api/trash/${id}/restore`, { method: "POST" }),
  purgeFromTrash: (id) => request(`/api/trash/${id}`, { method: "DELETE" }),

  listAlerts: (params) => request(`/api/alerts${toQuery(params)}`),
  alertSummary: (tzOffset = 0) => request(`/api/alerts/summary${toQuery({ tz_offset: tzOffset })}`),
  updateAlert: (id, payload) => request(`/api/alerts/${id}`, { method: "PATCH", json: payload }),
  retrainAnomalyModel: () => request("/api/alerts/model/retrain", { method: "POST" }),

  securityOverview: () => request("/api/admin/security"),
  rotateMasterKey: () => request("/api/admin/rotate-key", { method: "POST" }),
  retrainClassifier: () => request("/api/admin/classifier/retrain", { method: "POST" }),

  search: (params) => request(`/api/search${toQuery(params)}`),

  listUsers: () => request("/api/users"),
  createUser: (payload) => request("/api/users", { method: "POST", json: payload }),
  updateUser: (id, payload) => request(`/api/users/${id}`, { method: "PATCH", json: payload }),
  unblockUser: (id) => request(`/api/users/${id}/unblock`, { method: "POST" }),
  auditLog: (params) => request(`/api/audit${toQuery(params)}`),
};
