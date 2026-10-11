import { Check, X } from "lucide-react";
export default function Toast({ toasts }) {
  return (
    <div className="toast-container" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast ${toast.type}`}>
          <span className="toast-icon">
            {toast.type === "success" ? <Check size={14} /> : <X size={14} />}
          </span>
          {toast.message}
        </div>
      ))}
    </div>
  );
}
