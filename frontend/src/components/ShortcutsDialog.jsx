import { CloseIcon, KeyboardIcon } from "./Icons";
import { useEffect, useRef } from "react";

const SHORTCUTS = [
  ["/", "Search the queue"],
  ["j / k", "Next / previous break"],
  ["Enter", "Open the evidence"],
  ["x", "Select for bulk review"],
  ["Ctrl + Enter", "Resolve or reopen the open break"],
  ["Esc", "Close a panel"],
  ["?", "Show this list"],
];

export default function ShortcutsDialog({ onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="shortcuts"
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      aria-labelledby="shortcuts-title"
    >
      <header className="drawer-head">
        <h2 id="shortcuts-title" className="drawer-title">
          <KeyboardIcon size={18} /> Keyboard shortcuts
        </h2>
        <button
          className="icon-btn"
          aria-label="Close shortcuts"
          onClick={onClose}
        >
          <CloseIcon size={16} />
        </button>
      </header>
      <dl className="shortcut-list">
        {SHORTCUTS.map(([keys, action]) => (
          <div key={keys}>
            <dt>
              {keys
                .split(" ")
                .map((key, index) =>
                  ["/", "+"].includes(key) && index ? (
                    <span key={index}> {key} </span>
                  ) : (
                    <kbd key={index}>{key}</kbd>
                  ),
                )}
            </dt>
            <dd>{action}</dd>
          </div>
        ))}
      </dl>
    </dialog>
  );
}
