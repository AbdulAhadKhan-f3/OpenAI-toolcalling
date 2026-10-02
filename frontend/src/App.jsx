import { useEffect, useState } from "react";
import "./App.css";

const SAMPLE = `Doctor: What brings you in today?
Patient: A cough and fever for five days.
Doctor: I think this could be bronchitis. Let me check your X-ray.
Doctor: The X-ray confirms pneumonia, so it's not bronchitis.
Doctor: I was considering amoxicillin.
Patient: I had a rash with amoxicillin before.
Doctor: Then don't take it. I'll prescribe azithromycin 500 mg once daily for 5 days.
Patient: I also take metformin.
Doctor: Keep taking metformin. Follow up in one week.`;

// Small helper: every API call goes through here so errors look the same everywhere.
async function api(path, options) {
  const r = await fetch(path, options);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const error = new Error(data.detail || `Request failed (${r.status})`);
    error.status = r.status;
    throw error;
  }
  return data;
}

function isNonClinicalError(error) {
  return error.status === 422
    && /no clinical (information|content)|not a medical conversation/i.test(error.message);
}

const EMPTY_FIELD_VALUES = new Set(["", "not stated", "not specified", "unspecified", "unknown", "n/a", "na", "null"]);

function visibleValue(value) {
  const text = String(value ?? "").trim();
  return EMPTY_FIELD_VALUES.has(text.toLowerCase()) ? "" : text;
}

function compactFields(values) {
  return values.map(visibleValue).filter(Boolean).join(" · ");
}

function Item({ kind, title, tag, evidence }) {
  return (
    <div className={`item ${kind}`}>
      <div><b>{title}</b>{tag && <span className="tag">{tag}</span>}</div>
      {evidence && <div className="ev">“{evidence}”</div>}
    </div>
  );
}

// Shows one analysis result. Used by both the "new" and "history" pages.
function Result({ data }) {
  const fs = data.final_state;
  const soap = data.soap;
  const ex = data.extractions || {};   // history, findings and follow-up items (older saved results may not have it)
  const others = [...(ex.history || []), ...(ex.findings || []), ...(ex.follow_up || [])]
    .map((item) => ({ ...item, detail: visibleValue(item.detail), duration: visibleValue(item.duration) }))
    .filter((item) => item.detail);
  return (
    <div className="results-view">
      <header className="results-heading">
        <div><p className="eyebrow">Encounter output</p><h2>{data.title || "Clinical summary"}</h2></div>
        <span className={`status-badge ${data.complete ? "complete" : "incomplete"}`}>{data.complete ? "SOAP complete" : "SOAP incomplete"}</span>
      </header>
      {data.warnings?.length > 0 && <div className="review-alert">{data.warnings.map((warning, i) => <p key={i}>{warning}</p>)}</div>}
      {data.corrections?.length > 0 && (
        <div className="correction-notice">
          <b>Review possible medication-name corrections</b>
          {data.corrections.map(([heard, corrected], i) => <span key={`${heard}-${i}`}>“{heard}” → <b>{corrected}</b></span>)}
        </div>
      )}
      <div className="results-grid">
        <div className="results-column">
          <section className="panel-card result-panel">
            <h3>Diagnoses</h3>
            {fs.confirmed_diagnoses.map((d) => <Item key={d.diagnosis} title={d.diagnosis} tag="confirmed" evidence={d.evidence} />)}
            {fs.not_confirmed_diagnoses.map((d) => <Item key={d.diagnosis} kind="maybe" title={d.diagnosis} tag={d.status.replace("_", " ")} evidence={d.evidence} />)}
            {!fs.confirmed_diagnoses.length && !fs.not_confirmed_diagnoses.length && <p className="mute">No diagnoses found.</p>}
          </section>
          <section className="panel-card result-panel">
            <h3>Medications</h3>
            {fs.active_medications.map((m) => <Item key={m.name} title={compactFields([m.name, m.dose, m.route, m.frequency, m.duration])} tag={m.new ? "new" : "existing"} evidence={m.evidence} />)}
            {fs.stopped_medications.map((m) => <Item key={m.name} kind="stop" title={m.name} tag="stopped" evidence={m.evidence} />)}
            {fs.considered_only_medications.map((m) => <Item key={m.name} kind="maybe" title={m.name} tag="considered only" evidence={m.evidence} />)}
            {!fs.active_medications.length && !fs.stopped_medications.length && !fs.considered_only_medications.length && <p className="mute">No medications found.</p>}
          </section>
          <section className="panel-card result-panel supporting-data">
            <h3>History, findings & follow-up</h3>
            {others.map((item, index) => <Item key={`${item.category || item.type}-${index}`} title={item.duration ? `${item.detail} · ${item.duration}` : item.detail} tag={(item.category || item.type || "").replace(/_/g, " ")} evidence={item.evidence} />)}
            {!others.length && <p className="mute">Nothing recorded.</p>}
          </section>
        </div>
        <div className="results-column">
          <section className="panel-card soap-panel">
            <h3>SOAP note</h3>
            {soap ? <>
              {[["S — Subjective", "subjective"], ["O — Objective", "objective"], ["A — Assessment", "assessment"], ["P — Plan", "plan"], ["Summary", "summary"]]
                .map(([label, key]) => <p key={key}><b>{label}: </b>{soap[key]}</p>)}
              {soap.validation_warnings.map((warning, index) => <div key={index} className="warn">{warning}</div>)}
            </> : <p className="mute">The model did not submit a SOAP note.</p>}
          </section>
          <details className="trace-panel">
            <summary>Tool trace · {data.trace.length} calls</summary>
            <div className="trace-list">
              {data.trace.map((call, index) => <details key={index}>
                <summary className={call.result.error ? "err" : ""}>{index + 1}. {call.tool}{call.result.error ? " — rejected" : ""}</summary>
                <pre className="trace-output">{JSON.stringify(call.args, null, 2)}</pre>
                <pre className="trace-output">→ {JSON.stringify(call.result, null, 2)}</pre>
              </details>)}
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}

function Analyze({ onComplete }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [clinicalAlert, setClinicalAlert] = useState(false);
  const [notice, setNotice] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [dragging, setDragging] = useState(false);

  async function loadFile(file) {
    if (!file) return;
    setError("");
    setClinicalAlert(false);
    setNotice("");
    setSelectedFile(file);
    if (file.name.toLowerCase().endsWith(".txt")) {
      setText(await file.text());
      setNotice("Transcript loaded. Review it before analysis.");
      return;
    }
    setBusy("transcribing");
    setNotice("Transcribing locally with Nemotron. The first run may take longer while the model downloads.");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const d = await api("/api/transcribe", { method: "POST", body: fd });
      setText(d.transcript);
      setNotice(d.warning || "Transcription complete. Review names, medication spellings, and speaker labels.");
    } catch (err) {
      setError(err.message);
      setNotice("");
    } finally {
      setBusy("");
    }
  }

  function pickFile(event) {
    const file = event.currentTarget.files[0];
    event.currentTarget.value = "";
    loadFile(file);
  }

  function dropFile(event) {
    event.preventDefault();
    setDragging(false);
    loadFile(event.dataTransfer.files[0]);
  }

  async function run() {
    setBusy("analyzing");
    setError("");
    setClinicalAlert(false);
    try {
      const fd = new FormData();
      fd.append("text", text);
      const result = await api("/api/encounters", { method: "POST", body: fd });
      setText(result.transcript || text);
      onComplete(result);
    } catch (err) {
      if (isNonClinicalError(err)) {
        setClinicalAlert(true);
      } else {
        setError(err.message);
      }
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="analyze-layout">
      <section className="panel-card upload-panel">
        <div className="panel-header">
          <div><p className="eyebrow">New encounter</p><h2>Upload a source</h2></div>
          <span className="status-badge">Step 1 of 2</span>
        </div>
        <label
          className={`upload-dropzone${dragging ? " dragging" : ""}`}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={dropFile}
        >
          <input type="file" accept=".txt,.mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac,.mpeg,.mpga,audio/*" onChange={pickFile} />
          <span className="upload-mark" aria-hidden="true"><i /><i /><i /><i /><i /></span>
          <span className="upload-copy"><b>Drop a transcript or recording</b><span>TXT, MP3, WAV, M4A, MP4, WebM, OGG, FLAC</span></span>
          <span className="upload-action">Browse</span>
        </label>
        {selectedFile && <div className="selected-file-name">Selected: <b>{selectedFile.name}</b></div>}
        <div className="upload-actions">
          <button className="ghost-button" onClick={() => { setText(SAMPLE); setNotice("Sample loaded. Review it before analysis."); setSelectedFile(null); }}>Load sample</button>
          <button className="primary-button" onClick={run} disabled={Boolean(busy) || !text.trim()}>
            {busy === "analyzing" ? "Analyzing…" : "Analyze transcript"}
          </button>
        </div>
        {clinicalAlert && (
          <div className="clinical-alert" role="alert">
            <div>
              <b>Enter a clinical consultation</b>
              <p>This workspace analyzes doctor-patient health conversations. Add or upload clinical transcript text, then try again.</p>
            </div>
            <button className="alert-dismiss" onClick={() => setClinicalAlert(false)} aria-label="Dismiss message">×</button>
          </div>
        )}
        {busy === "transcribing" && <p className="working"><i /> Transcribing with Nemotron…</p>}
        {error && <p className="err" role="alert">{error}</p>}
        {notice && !error && <p className="notice" role="status">{notice}</p>}
      </section>
      <section className="panel-card transcript-panel">
        <div className="panel-header transcript-panel-header">
          <div><p className="eyebrow">Review before analysis</p><h2>Transcript</h2></div>
          <span className="mute">{text.trim() ? `${text.trim().split(/\s+/).length} words` : "No transcript yet"}</span>
        </div>
        <textarea className="transcript-editor" value={text} onChange={(event) => setText(event.target.value)} placeholder="Doctor: ...&#10;Patient: ..." aria-label="Transcript text" />
      </section>
    </div>
  );
}

function History({ onSelect }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Re-query whenever the search box changes (small delay so we don't fire on every keystroke)
  useEffect(() => {
    const t = setTimeout(() => api(`/api/encounters?q=${encodeURIComponent(q)}`).then(setRows).catch((e) => setError(e.message)), 250);
    return () => clearTimeout(t);
  }, [q]);

  async function viewEncounter(id) {
    setBusy(true);
    setError("");
    try {
      const encounter = await api(`/api/encounters/${id}`);
      onSelect({ ...encounter.result, title: encounter.title });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel-card history-panel">
      <div className="panel-header">
        <div><p className="eyebrow">Record library</p><h2>Saved analyses</h2></div>
        <input className="search" value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search encounters" aria-label="Search saved analyses" />
      </div>
      {error && <p className="err" role="alert">{error}</p>}
      <div className="history-list">
        {rows.map((row) => (
          <button key={row.id} className="history-record" onClick={() => viewEncounter(row.id)} disabled={busy}>
            <span className="history-record-main"><b>{row.title}</b><span>{row.created_at}</span></span>
            <span className="history-record-detail">{row.diagnoses || "No confirmed diagnosis"} · {row.medications || "No active medications"}</span>
          </button>
        ))}
        {!rows.length && <p className="mute">No saved encounters match this search.</p>}
      </div>
    </section>
  );
}

export default function App() {
  const [page, setPage] = useState("upload");
  const [result, setResult] = useState(null);

  function openResult(data) {
    setResult(data);
    setPage("results");
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">+</span>
          <div><p className="eyebrow">Clinical documentation</p><h1>Conversation analyzer</h1></div>
        </div>
        <div className="status-badge model-badge">Nemotron · local audio</div>
      </header>
      <nav className="tab-nav workspace-tabs" aria-label="Workspace sections">
        <button className={`tab-button${page === "upload" ? " active" : ""}`} onClick={() => setPage("upload")}>Upload</button>
        <button className={`tab-button${page === "results" ? " active" : ""}`} onClick={() => setPage("results")} disabled={!result}>Results</button>
        <button className={`tab-button${page === "history" ? " active" : ""}`} onClick={() => setPage("history")}>History</button>
      </nav>
      <div className="page-content">
        {page === "upload" && <Analyze onComplete={openResult} />}
        {page === "results" && result && <Result data={result} />}
        {page === "history" && <History onSelect={openResult} />}
      </div>
    </main>
  );
}
