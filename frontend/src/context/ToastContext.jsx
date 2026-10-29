import { createContext, useCallback, useContext, useState } from "react";
import Icon from "../components/Icon";

const ToastContext = createContext(null);
let nextId = 1;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const notify = useCallback((message, type = "success") => {
    const id = nextId++;
    setToasts((list) => [...list, { id, message, type }].slice(-3)); // keep the 3 most recent
    setTimeout(() => setToasts((list) => list.filter((toast) => toast.id !== id)), 4200);
  }, []);

  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast ${toast.type}`}>
            <Icon name={toast.type === "error" ? "alert" : "check"} />
            <span>{toast.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
