import { useEffect } from "react";
import { IconX } from "./icons";

/**
 * Reusable modal for adding / editing clinical items.
 *
 * props:
 * - open: boolean
 * - title: string
 * - fields: array of { key, label, type, options?, required?, placeholder? }
 * - values: object
 * - onChange: (key, value) => void
 * - onSave: () => void
 * - onClose: () => void
 * - saving?: boolean
 */
export function EditModal({
  open,
  title,
  fields = [],
  values = {},
  onChange,
  onSave,
  onClose,
  saving = false,
}) {
  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            <IconX width="18" height="18" />
          </button>
        </div>

        <div className="modal-body">
          {fields.map((f) => (
            <div key={f.key} className="modal-field">
              <label>
                {f.label}
                {f.required && <span className="required-star">*</span>}
              </label>

              {f.type === "select" ? (
                <select
                  value={values[f.key] ?? ""}
                  onChange={(e) => onChange(f.key, e.target.value)}
                >
                  {(f.options || []).map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              ) : f.type === "textarea" ? (
                <textarea
                  rows={3}
                  value={values[f.key] ?? ""}
                  placeholder={f.placeholder || ""}
                  onChange={(e) => onChange(f.key, e.target.value)}
                />
              ) : (
                <input
                  type="text"
                  value={values[f.key] ?? ""}
                  placeholder={f.placeholder || ""}
                  onChange={(e) => onChange(f.key, e.target.value)}
                />
              )}
            </div>
          ))}
        </div>

        <div className="modal-footer">
          <button className="modal-btn cancel" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="modal-btn primary" onClick={onSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}