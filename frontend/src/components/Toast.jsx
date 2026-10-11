import { CheckIcon, CloseIcon } from "./Icons";
export default function Toast({ toasts }) {
  return (
    <div className="toast-container" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast ${toast.type}`}>
          <span className="toast-icon">
            {toast.type === "success" ? (
              <CheckIcon size={14} />
            ) : (
              <CloseIcon size={14} />
            )}
          </span>
          {toast.message}
        </div>
      ))}
    </div>
  );
}
