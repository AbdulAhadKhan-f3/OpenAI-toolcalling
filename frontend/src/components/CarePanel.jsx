import { useState } from "react";

const KINDS = {
  tasks: { label: "Tasks", title: "detail", fields: [["detail", "What needs doing"], ["owner", "Owner"], ["due", "Due"]] },
  recalls: { label: "Recalls", title: "detail", fields: [["detail", "Reason"], ["type", "Type"], ["due", "Due"]] },
  referrals: { label: "Referrals", title: "refer_to", fields: [["refer_to", "Refer to"], ["detail", "Reason"], ["urgency", "Urgency"], ["condition", "Only if"]] },
};

async function api(url, method = "GET", body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

/** Read-only results header: patient info left, token breakdown right. */
export function PatientBar({ patient, consult }) {
  if (!patient && !consult) return null;

  const inputTokens  = consult?.input_tokens  ?? 0;
  const outputTokens = consult?.output_tokens ?? 0;

  return (
    <div className="results-header-bar">
      {/* Left — patient info */}
      <div className="results-patient-side">
        {patient ? (
          <>
            <div className="patient-avatar" style={{ width: 38, height: 38, fontSize: "0.9rem", flexShrink: 0 }}>
              {patient.name?.[0]?.toUpperCase() || "?"}
            </div>
            <div>
              <span className="results-patient-name">{patient.name}</span>
              <div className="results-patient-meta">
                {patient.date_of_birth && <span>{patient.date_of_birth}</span>}
                {patient.gender        && <span>{patient.gender}</span>}
                {patient.phone         && <span>{patient.phone}</span>}
              </div>
            </div>
          </>
        ) : (
          <span className="patient-bar-label">No patient assigned</span>
        )}
      </div>

      {/* Right — token breakdown */}
      {consult && (inputTokens > 0 || outputTokens > 0) && (
        <div className="results-token-side">
          <div className="token-stat">
            <span className="token-stat-label">Input tokens</span>
            <span className="token-stat-value">{inputTokens.toLocaleString()}</span>
          </div>
          <div className="token-stat-divider" />
          <div className="token-stat">
            <span className="token-stat-label">Output tokens</span>
            <span className="token-stat-value">{outputTokens.toLocaleString()}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/** One tab: the tasks, recalls or referrals of an encounter. Every change is saved through the API. */
export function CareList({ kind, encounterId, items, onChange }) {
  const { fields, title, label } = KINDS[kind];
  const [draft, setDraft] = useState({});
  const [edit, setEdit] = useState(null); // { id, values }
  const [error, setError] = useState("");

  const run = async (fn) => { setError(""); try { await fn(); } catch (e) { setError(e.message); } };
  const replace = (item) => onChange(items.map((i) => (i.id === item.id ? item : i)));
  const add = (e) => {
    e.preventDefault();
    run(async () => {
      const item = await api(`/api/care/${kind}`, "POST", { ...draft, encounter_id: Number(encounterId) });
      onChange([...items, item]); setDraft({});
    });
  };
  const save = () => run(async () => { replace(await api(`/api/care/${kind}/${edit.id}`, "PATCH", edit.values)); setEdit(null); });
  const setStatus = (item, status) => run(async () => replace(await api(`/api/care/${kind}/${item.id}`, "PATCH", { status })));
  const remove = (item) => run(async () => { await api(`/api/care/${kind}/${item.id}`, "DELETE"); onChange(items.filter((i) => i.id !== item.id)); });

  return (
    <div className="tab-pane">
      <div className="pane-section-header">
        <h3>{label}</h3>
        <span className="section-count-tag">{items.filter((i) => i.status === "open").length} open</span>
      </div>
      {error && <div className="status-toast error">{error}</div>}
      <form className="care-form" onSubmit={add}>
        {fields.map(([f, text]) => (
          <input key={f} value={draft[f] || ""} onChange={(e) => setDraft({ ...draft, [f]: e.target.value })}
            placeholder={text} aria-label={text} required={f === title} />
        ))}
        <button className="action-btn primary-btn" type="submit">Add</button>
      </form>

      <div className="cards-grid">
        {items.map((i) => (
          <article key={i.id} className={`clinical-card care-card ${i.status === "done" ? "dim" : ""}`}>
            <div className="card-top-row">
              <span className="card-title-text">{i[title] || i.detail}</span>
              <span className="card-tags-group">
                {i.source === "ai" && <span className="status-tag dim">AI</span>}
                <span className="status-tag neutral">{i.status}</span>
              </span>
            </div>
            {edit?.id === i.id ? (
              <div className="care-edit">
                {fields.map(([f, text]) => (
                  <input key={f} value={edit.values[f] || ""} placeholder={text} aria-label={text}
                    onChange={(e) => setEdit({ ...edit, values: { ...edit.values, [f]: e.target.value } })} />
                ))}
              </div>
            ) : (
              <div className="card-bottom-row">
                {fields.filter(([f]) => f !== title && i[f]).map(([f, text]) => (
                  <span key={f} className="kv-pair"><span className="kv-key">{text}</span><span className="kv-val">{i[f]}</span></span>
                ))}
              </div>
            )}
            {i.evidence && <div className="info-detail-row"><span className="sub-label">Doctor said</span><span className="sub-value">“{i.evidence}”</span></div>}
            <div className="care-actions">
              {edit?.id === i.id ? (
                <><button onClick={save}>Save</button><button onClick={() => setEdit(null)}>Cancel</button></>
              ) : (
                <>
                  {i.status === "open"
                    ? <button onClick={() => setStatus(i, "done")}>Mark done</button>
                    : <button onClick={() => setStatus(i, "open")}>Reopen</button>}
                  <button onClick={() => setEdit({ id: i.id, values: Object.fromEntries(fields.map(([f]) => [f, i[f] || ""])) })}>Edit</button>
                  <button className="danger" onClick={() => remove(i)}>Delete</button>
                </>
              )}
            </div>
          </article>
        ))}
      </div>
      {!items.length && <p className="pane-desc">Nothing here yet. Add one above.</p>}
    </div>
  );
}
