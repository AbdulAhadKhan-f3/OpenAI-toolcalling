import { useEffect, useState } from "react";
import { IconSearch, IconX, IconChevronRight, IconPlus } from "./icons";

const money = (v) => (v == null ? "—" : `$${v.toFixed(4)}`);
const getJson = (url) => fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(new Error("Could not load data"))));

const KIND_LABEL = { tasks: "Tasks", recalls: "Recalls", referrals: "Referrals" };

function formatDate(dateStr) {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr.replace(" ", "T"));
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch { return dateStr; }
}

/* ─── Add / Edit Patient Modal ──────────────────────────────────────────── */
const PATIENT_FIELDS = [
  { key: "name",          label: "Full Name",       required: true,  placeholder: "e.g. John Smith" },
  { key: "date_of_birth", label: "Date of Birth",   placeholder: "e.g. 1985-04-12" },
  { key: "gender",        label: "Gender",          placeholder: "e.g. Male / Female / Other" },
  { key: "phone",         label: "Phone",           placeholder: "e.g. +1 555 000 0000" },
  { key: "email",         label: "Email",           placeholder: "e.g. john@example.com" },
  { key: "notes",         label: "Notes",           placeholder: "Any relevant background…" },
];

function PatientFormModal({ title, initial = {}, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: "", date_of_birth: "", gender: "", phone: "", email: "", notes: "",
    ...initial,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    setError("");
    try {
      let res, data;
      if (initial.id) {
        // Edit existing
        res = await fetch(`/api/patients/${initial.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form),
        });
      } else {
        // Create new
        res = await fetch("/api/patients", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: form.name.trim() }),
        });
      }
      data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Request failed");
      // If creating, patch the remaining fields
      if (!initial.id && data.id) {
        const extra = { date_of_birth: form.date_of_birth, gender: form.gender,
                        phone: form.phone, email: form.email, notes: form.notes };
        if (Object.values(extra).some((v) => v.trim())) {
          const r2 = await fetch(`/api/patients/${data.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(extra),
          });
          if (r2.ok) data = await r2.json().catch(() => data);
        }
      }
      onSaved(data);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  };

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            <IconX width="16" height="16" />
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {PATIENT_FIELDS.map((f) => (
              <div key={f.key} className="modal-field">
                <label>
                  {f.label}
                  {f.required && <span className="required-star">*</span>}
                </label>
                <input
                  type="text"
                  value={form[f.key] || ""}
                  onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                  placeholder={f.placeholder || ""}
                  autoFocus={f.key === "name"}
                />
              </div>
            ))}
            {error && <div className="status-toast error" style={{ marginTop: 0 }}>{error}</div>}
          </div>
          <div className="modal-footer">
            <button type="button" className="modal-btn cancel" onClick={onClose} disabled={saving}>Cancel</button>
            <button type="submit" className="modal-btn primary" disabled={saving || !form.name.trim()}>
              {saving ? "Saving…" : (initial.id ? "Save Changes" : "Add Patient")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ─── Patient List ──────────────────────────────────────────────────────── */
function PatientList({ onSelectPatient, onNewConsultation }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);

  const fetchPatients = (query = q) => {
    setLoading(true);
    getJson(`/api/patients?q=${encodeURIComponent(query)}`)
      .then((data) => { setRows(data); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  };

  useEffect(() => {
    const t = setTimeout(() => fetchPatients(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  const handleCreated = (patient) => {
    setShowAddModal(false);
    fetchPatients();
    onSelectPatient(patient.id);
  };

  return (
    <div className="records-view-container">
      {showAddModal && (
        <PatientFormModal
          title="Add Patient"
          onClose={() => setShowAddModal(false)}
          onSaved={handleCreated}
        />
      )}

      {/* Header */}
      <div className="records-header-card">
        <div className="records-header-left">
          <div className="records-badge">
            <span className="records-badge-dot" />
            Patient Registry
          </div>
          <h2 className="records-heading">Patients</h2>
          <p className="records-subtext">
            Select a patient to view their consultation history, tasks, recalls and referrals.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div className="records-search-box" style={{ maxWidth: 260 }}>
            <IconSearch width="15" height="15" className="search-icon" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search patients…"
              aria-label="Search patients"
            />
            {q && (
              <button className="clear-search-btn" onClick={() => setQ("")} aria-label="Clear">
                <IconX width="13" height="13" />
              </button>
            )}
          </div>
          <button className="btn-primary-new" onClick={() => setShowAddModal(true)}>
            <IconPlus width="14" height="14" />
            Add Patient
          </button>
        </div>
      </div>

      {error && <div className="records-error-box">{error}</div>}

      <div className="records-content-card">
        {loading ? (
          <div className="records-loading-skeleton">
            {[1,2,3,4].map((i) => <div key={i} className="record-row-skeleton" />)}
          </div>
        ) : rows.length === 0 ? (
          <div className="records-empty-state">
            <h3 className="empty-state-title">No patients yet</h3>
            <p className="empty-state-desc">
              Patients are created automatically when you run a new consultation and enter a patient name.
            </p>
          </div>
        ) : (
          <div className="records-table-wrapper">
            <table className="records-table">
              <thead>
                <tr>
                  <th>Patient Name</th>
                  <th style={{ width: 90 }}>Consults</th>
                  <th style={{ width: 130 }}>Last Seen</th>
                  <th style={{ width: 100 }}>Tokens</th>
                  <th style={{ width: 90 }}>Cost</th>
                  <th style={{ width: 80, textAlign: "right" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id} className="record-row" onClick={() => onSelectPatient(p.id)}>
                    <td>
                      <div className="patient-name-cell">
                        <div className="patient-avatar">{p.name?.[0]?.toUpperCase() || "?"}</div>
                        <span className="record-main-title">{p.name}</span>
                      </div>
                    </td>
                    <td>
                      <span className="record-id-badge">{p.consults}</span>
                    </td>
                    <td><span className="record-date-text">{formatDate(p.last_seen)}</span></td>
                    <td><span className="record-date-text">{(p.total_tokens || 0).toLocaleString()}</span></td>
                    <td><span className="record-date-text">{money(p.total_cost_usd)}</span></td>
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                        <button
                          className="btn-consult-row"
                          onClick={(e) => { e.stopPropagation(); onNewConsultation({ id: p.id, name: p.name }); }}
                          title="New consultation for this patient"
                        >
                          + Consult
                        </button>
                        <button className="btn-view-record" onClick={(e) => { e.stopPropagation(); onSelectPatient(p.id); }}>
                          View <IconChevronRight width="12" height="12" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Patient Detail (consultations list) ───────────────────────────────── */
function PatientDetail({ patientId, onBack, onSelectRecord, onNewConsultation }) {
  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");
  const [showEdit, setShowEdit] = useState(false);

  const load = () => {
    getJson(`/api/patients/${patientId}`)
      .then(setHistory)
      .catch((e) => setError(e.message));
  };

  useEffect(load, [patientId]);

  if (error) return (
    <div className="records-view-container">
      <div className="records-error-box">{error}</div>
      <button className="btn-back-link" onClick={onBack}>← All patients</button>
    </div>
  );

  if (!history) return (
    <div className="records-view-container">
      <div className="records-loading-skeleton">
        {[1,2,3].map((i) => <div key={i} className="record-row-skeleton" />)}
      </div>
    </div>
  );

  const { patient, consults, care } = history;
  const openItems = Object.entries(care || {}).reduce((sum, [, items]) => {
    return sum + (items || []).filter((i) => i.status === "open").length;
  }, 0);

  // Build detail chips for non-empty patient fields
  const detailChips = [
    patient.date_of_birth && { label: "DOB", value: patient.date_of_birth },
    patient.gender        && { label: "Gender", value: patient.gender },
    patient.phone         && { label: "Phone", value: patient.phone },
    patient.email         && { label: "Email", value: patient.email },
  ].filter(Boolean);

  return (
    <div className="records-view-container">
      {showEdit && (
        <PatientFormModal
          title="Edit Patient"
          initial={patient}
          onClose={() => setShowEdit(false)}
          onSaved={() => { setShowEdit(false); load(); }}
        />
      )}

      {/* Header */}
      <div className="records-header-card">
        <div className="records-header-left">
          <button className="btn-back-link" onClick={onBack}>← All patients</button>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 6 }}>
            <div className="patient-avatar patient-avatar-lg">{patient.name?.[0]?.toUpperCase() || "?"}</div>
            <div>
              <h2 className="records-heading" style={{ marginBottom: 2 }}>{patient.name}</h2>
              <p className="records-subtext">
                {consults.length} consultation{consults.length !== 1 ? "s" : ""}
                {openItems > 0 && ` · ${openItems} open item${openItems !== 1 ? "s" : ""}`}
                {history.total_tokens > 0 && ` · ${history.total_tokens.toLocaleString()} tokens`}
                {history.total_cost_usd != null && ` · ${money(history.total_cost_usd)} total`}
              </p>
              {detailChips.length > 0 && (
                <div className="patient-detail-chips">
                  {detailChips.map((c) => (
                    <span key={c.label} className="patient-detail-chip">
                      <span className="chip-label">{c.label}</span>
                      <span className="chip-value">{c.value}</span>
                    </span>
                  ))}
                </div>
              )}
              {patient.notes && <p className="patient-notes-text">{patient.notes}</p>}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          <button className="btn-primary-new" onClick={() => onNewConsultation({ id: patient.id, name: patient.name })}>
            + New Consultation
          </button>
          <button className="btn-primary-new" style={{ background: "var(--navy)" }} onClick={() => setShowEdit(true)}>
            Edit Patient
          </button>
        </div>
      </div>

      {/* Open care items summary */}
      {Object.entries(care || {}).map(([k, items]) => {
        const open = (items || []).filter((i) => i.status === "open");
        if (!open.length) return null;
        return (
          <div key={k} className="records-content-card care-open">
            <h3 className="care-title">{KIND_LABEL[k]} still open</h3>
            <ul>
              {open.map((i) => (
                <li key={i.id}>
                  {i.refer_to ? `${i.refer_to}: ${i.detail}` : i.detail}
                  {i.due ? ` — due ${i.due}` : ""}
                </li>
              ))}
            </ul>
          </div>
        );
      })}

      {/* Consultations table */}
      <div className="records-content-card">
        {consults.length === 0 ? (
          <div className="records-empty-state">
            <h3 className="empty-state-title">No consultations yet</h3>
            <p className="empty-state-desc">Consultations linked to this patient will appear here.</p>
          </div>
        ) : (
          <div className="records-table-wrapper">
            <table className="records-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Diagnoses / Summary</th>
                  <th style={{ width: 90 }}>Open items</th>
                  <th style={{ width: 100 }}>Tokens</th>
                  <th style={{ width: 90 }}>Cost</th>
                  <th style={{ width: 80, textAlign: "right" }} />
                </tr>
              </thead>
              <tbody>
                {consults.map((c) => (
                  <tr key={c.encounter_id} className="record-row" onClick={() => onSelectRecord(c.encounter_id)}>
                    <td><span className="record-date-text">{formatDate(c.created_at)}</span></td>
                    <td>
                      <div className="record-title-cell">
                        <span className="record-main-title">
                          {c.diagnoses || c.title || `Encounter #${c.encounter_id}`}
                        </span>
                        {c.summary && <span className="record-date-text">{c.summary}</span>}
                      </div>
                    </td>
                    <td>
                      {c.open_items > 0
                        ? <span className="record-id-badge" style={{ background: "var(--amber-bg)", color: "#92400E", borderColor: "#FDE68A" }}>{c.open_items}</span>
                        : <span className="record-date-text">—</span>}
                    </td>
                    <td><span className="record-date-text">{(c.total_tokens || 0).toLocaleString()}</span></td>
                    <td><span className="record-date-text">{money(c.cost_usd)}</span></td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-view-record" onClick={(e) => { e.stopPropagation(); onSelectRecord(c.encounter_id); }}>
                        Open <IconChevronRight width="12" height="12" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Root export ───────────────────────────────────────────────────────── */
export function PatientsView({ onSelectRecord, onNewConsultation }) {
  const [selectedPatientId, setSelectedPatientId] = useState(null);

  if (selectedPatientId) {
    return (
      <PatientDetail
        patientId={selectedPatientId}
        onBack={() => setSelectedPatientId(null)}
        onSelectRecord={onSelectRecord}
        onNewConsultation={onNewConsultation}
      />
    );
  }

  return <PatientList onSelectPatient={setSelectedPatientId} onNewConsultation={onNewConsultation} />;
}
