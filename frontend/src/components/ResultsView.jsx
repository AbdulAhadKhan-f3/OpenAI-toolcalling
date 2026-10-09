import { useState, useEffect } from "react";
import { EditModal } from "./EditModal";
import {
  IconActivity,
  IconPill,
  IconAlertTriangle,
  IconFileText,
  IconTerminal,
  IconCopy,
  IconCheck,
  IconRefresh,
  IconChevronRight,
  IconCheckCircle,
  IconShare,
  IconPlus,
  IconTrash,
  IconEdit,
} from "./icons";
import { CareList, PatientBar } from "./CarePanel";

const EMPTY_VALUES = new Set([
  "",
  "not stated",
  "not specified",
  "unspecified",
  "unknown",
  "n/a",
  "na",
  "null",
]);

const DX_FIELDS = [
  {
    key: "name",
    label: "Diagnosis name",
    type: "text",
    required: true,
    placeholder: "e.g. Community-acquired pneumonia",
  },
  {
    key: "status",
    label: "Status",
    type: "select",
    required: true,
    options: [
      { value: "confirmed", label: "Confirmed" },
      { value: "suspected", label: "Suspected" },
      { value: "ruled_out", label: "Ruled out" },
      { value: "history", label: "History" },
    ],
  },
  {
    key: "term",
    label: "Term",
    type: "select",
    options: [
      { value: "short_term", label: "Short-term" },
      { value: "long_term", label: "Long-term" },
    ],
  },
  {
    key: "dx_type",
    label: "Type",
    type: "text",
    placeholder: "e.g. infectious, cardiovascular, metabolic...",
  },
];

const MED_FIELDS = [
  {
    key: "name",
    label: "Medication name",
    type: "text",
    required: true,
    placeholder: "e.g. Metformin",
  },
  {
    key: "status",
    label: "Status",
    type: "select",
    required: true,
    options: [
      { value: "prescribed", label: "Prescribed" },
      { value: "dose_changed", label: "Dose changed" },
      { value: "continued", label: "Continued" },
      { value: "stopped", label: "Stopped" },
      { value: "not_prescribed", label: "Not prescribed" },
      { value: "patient_reported", label: "Patient reported" },
    ],
  },
  { key: "dose", label: "Dose", type: "text", placeholder: "e.g. 500 mg" },
  { key: "route", label: "Route", type: "text", placeholder: "e.g. oral" },
  {
    key: "frequency",
    label: "Frequency",
    type: "text",
    placeholder: "e.g. twice daily",
  },
  {
    key: "duration",
    label: "Duration",
    type: "text",
    placeholder: "e.g. 7 days",
  },
  {
    key: "indication",
    label: "Indication / Reason",
    type: "text",
    placeholder: "Why it was given or changed",
  },
];

function cleanVal(v) {
  const str = String(v ?? "").trim();
  return EMPTY_VALUES.has(str.toLowerCase()) ? "" : str;
}


export function ResultsView({ data}) {
  const [activeTab, setActiveTab] = useState("Diagnosis");
  const [medFilter, setMedFilter] = useState("all");
  const [copiedSoap, setCopiedSoap] = useState(false);
  const [copiedTranscript, setCopiedTranscript] = useState(false);

  // Care items (tasks / recalls / referrals)
  const [care, setCare] = useState({ tasks: [], recalls: [], referrals: [] });
  const [consult, setConsult] = useState(null);
  const [patient, setPatient] = useState(null);

  // Editable diagnoses & medications (loaded from the new CRUD endpoints)
  const [diagnoses, setDiagnoses] = useState([]);
  const [medications, setMedications] = useState([]);

  // Simple inline edit state
  const [editingDx, setEditingDx] = useState(null); // null | {id?} | 'new'
  const [editingMed, setEditingMed] = useState(null);
  const [dxForm, setDxForm] = useState({
    name: "",
    status: "confirmed",
    term: "short_term",
    dx_type: "",
  });
  const [medForm, setMedForm] = useState({
    name: "",
    status: "prescribed",
    dose: "",
    route: "",
    frequency: "",
    timing: "",
    duration: "",
    indication: "",
  });

  const loadAll = () => {
    if (!data.id) return;
    fetch(`/api/encounters/${data.id}`)
      .then((r) => r.json())
      .then((enc) => {
        setCare(enc.care || { tasks: [], recalls: [], referrals: [] });
        setConsult(enc.consult || null);
        setPatient(enc.patient || null);
      })
      .catch(() => {});

    fetch(`/api/encounters/${data.id}/diagnoses`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setDiagnoses)
      .catch(() => setDiagnoses([]));

    fetch(`/api/encounters/${data.id}/medications`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setMedications)
      .catch(() => setMedications([]));
  };

  useEffect(loadAll, [data.id]);

  const careKind = {
    Tasks: "tasks",
    Recalls: "recalls",
    Referrals: "referrals",
  }[activeTab];
  const openCount = (kind) =>
    (care[kind] || []).filter((i) => i.status === "open").length;

  // ---------- Diagnosis helpers ----------
  const startAddDx = () => {
    setDxForm({
      name: "",
      status: "confirmed",
      term: "short_term",
      dx_type: "",
    });
    setEditingDx("new");
  };
  const startEditDx = (d) => {
    setDxForm({
      name: d.name || "",
      status: d.status || "suspected",
      term: d.term || "short_term",
      dx_type: d.dx_type || "",
    });
    setEditingDx(d.id);
  };
  const cancelDx = () => setEditingDx(null);

  const saveDx = async () => {
    if (!dxForm.name.trim()) return alert("Diagnosis name is required");
    const body = { ...dxForm, name: dxForm.name.trim() };
    try {
      if (editingDx === "new") {
        const res = await fetch(`/api/encounters/${data.id}/diagnoses`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(await res.text());
      } else {
        const res = await fetch(
          `/api/encounters/${data.id}/diagnoses/${editingDx}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
        );
        if (!res.ok) throw new Error(await res.text());
      }
      setEditingDx(null);
      loadAll();
    } catch (e) {
      alert("Could not save diagnosis: " + e.message);
    }
  };

  const deleteDx = async (id) => {
    if (!confirm("Delete this diagnosis?")) return;
    try {
      const res = await fetch(`/api/encounters/${data.id}/diagnoses/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(await res.text());
      loadAll();
    } catch (e) {
      alert("Could not delete: " + e.message);
    }
  };

  // ---------- Medication helpers ----------
  const startAddMed = () => {
    setMedForm({
      name: "",
      status: "prescribed",
      dose: "",
      route: "",
      frequency: "",
      timing: "",
      duration: "",
      indication: "",
    });
    setEditingMed("new");
  };
  const startEditMed = (m) => {
    setMedForm({
      name: m.name || "",
      status: m.status || "prescribed",
      dose: m.dose || "",
      route: m.route || "",
      frequency: m.frequency || "",
      timing: m.timing || "",
      duration: m.duration || "",
      indication: m.indication || "",
    });
    setEditingMed(m.id);
  };
  const cancelMed = () => setEditingMed(null);

  const saveMed = async () => {
    if (!medForm.name.trim()) return alert("Medication name is required");
    const body = { ...medForm, name: medForm.name.trim() };
    try {
      if (editingMed === "new") {
        const res = await fetch(`/api/encounters/${data.id}/medications`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(await res.text());
      } else {
        const res = await fetch(
          `/api/encounters/${data.id}/medications/${editingMed}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
        );
        if (!res.ok) throw new Error(await res.text());
      }
      setEditingMed(null);
      loadAll();
    } catch (e) {
      alert("Could not save medication: " + e.message);
    }
  };

  const deleteMed = async (id) => {
    if (!confirm("Delete this medication?")) return;
    try {
      const res = await fetch(`/api/encounters/${data.id}/medications/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(await res.text());
      loadAll();
    } catch (e) {
      alert("Could not delete: " + e.message);
    }
  };

  // ---------- Rest of the original derived data (for other tabs) ----------
  // const finalState = data.final_state || {};
  const soap = data.soap || null;
  const extractions = data.extractions || {};
  const warnings = data.warnings || [];
  const corrections = data.corrections || [];
  const rawTranscript =
    data.transcript || data.text || data.raw_text || data.dialogue || "";

  const parseItems = (list, ...categories) => {
    return (list || [])
      .filter((i) => !categories.length || categories.includes(i.category))
      .map((i) => ({
        ...i,
        detail: cleanVal(i.detail),
        duration: cleanVal(i.duration),
      }))
      .filter((i) => i.detail);
  };

  const allergies = parseItems(extractions.history, "allergy");
  const history = parseItems(
    extractions.history,
    "past_history",
    "family_history",
    "social_history",
  );
  const instructions = parseItems(extractions.follow_up);
  const findings = parseItems(extractions.findings);

  const transcriptLines = rawTranscript
    ? rawTranscript.split(/\r?\n/).filter((l) => l.trim().length > 0)
    : [];

  // Counts now come from the live editable lists
  const tabCounts = {
    Diagnosis: diagnoses.length,
    Medications: medications.length,
    Tasks: openCount("tasks"),
    Recalls: openCount("recalls"),
    Referrals: openCount("referrals"),
    Allergies: allergies.length,
    "Medical History": history.length,
    Instructions: instructions.length,
    "Clinical Findings": findings.length,
    Transcription: transcriptLines.length,
    "SOAP Note": soap ? 1 : 0,
  };

  const tabsConfig = [
    {
      id: "Diagnosis",
      label: "Diagnosis",
      icon: IconActivity,
      count: tabCounts.Diagnosis,
    },
    {
      id: "Medications",
      label: "Medications",
      icon: IconPill,
      count: tabCounts.Medications,
    },
    {
      id: "Tasks",
      label: "Tasks",
      icon: IconCheckCircle,
      count: tabCounts.Tasks,
    },
    {
      id: "Recalls",
      label: "Recalls",
      icon: IconRefresh,
      count: tabCounts.Recalls,
    },
    {
      id: "Referrals",
      label: "Referrals",
      icon: IconShare,
      count: tabCounts.Referrals,
    },
    {
      id: "Allergies",
      label: "Allergies",
      icon: IconAlertTriangle,
      count: tabCounts.Allergies,
      isAlert: allergies.length > 0,
    },
    {
      id: "Medical History",
      label: "History",
      icon: IconFileText,
      count: tabCounts["Medical History"],
    },
    {
      id: "Instructions",
      label: "Instructions",
      icon: IconCheckCircle,
      count: tabCounts.Instructions,
    },
    {
      id: "Clinical Findings",
      label: "Findings",
      icon: IconActivity,
      count: tabCounts["Clinical Findings"],
    },
    {
      id: "Transcription",
      label: "Transcription",
      icon: IconTerminal,
      count: null,
    },
    { id: "SOAP Note", label: "SOAP Note", icon: IconFileText, count: null },
  ];

  const handleCopySoap = () => {
    if (!soap) return;
    const formatted = `CLINICAL SOAP NOTE: ${data.title || "Patient Encounter"}
======================================================
SUBJECTIVE:
${soap.subjective || "N/A"}

OBJECTIVE:
${soap.objective || "N/A"}

ASSESSMENT:
${soap.assessment || "N/A"}

PLAN:
${soap.plan || "N/A"}

SUMMARY:
${soap.summary || "N/A"}
======================================================`;
    navigator.clipboard.writeText(formatted).then(() => {
      setCopiedSoap(true);
      setTimeout(() => setCopiedSoap(false), 2500);
    });
  };

  const handleCopyTranscript = () => {
    if (!rawTranscript) return;
    navigator.clipboard.writeText(rawTranscript).then(() => {
      setCopiedTranscript(true);
      setTimeout(() => setCopiedTranscript(false), 2500);
    });
  };

  // Filtered meds for the filter pills
  const filteredMeds = medications.filter((m) => {
    if (medFilter === "all") return true;
    if (medFilter === "new")
      return m.status === "prescribed" || m.status === "dose_changed";
    if (medFilter === "active")
      return ["prescribed", "continued", "dose_changed"].includes(m.status);
    if (medFilter === "stopped") return m.status === "stopped";
    if (medFilter === "considered")
      return m.status === "not_prescribed" || m.status === "patient_reported";
    return true;
  });

  return (
    <div className="results-container">
      {data.id && (
        <PatientBar
          patient={patient}
          consult={consult}
        />
      )}

      {/* banners stay the same */}
      {corrections.length > 0 && (
        <div className="alert-banner med-correction-banner">
          <div className="banner-icon-col">
            <IconPill width="16" height="16" />
          </div>
          <div className="banner-content">
            <span className="banner-heading">
              Medication Spelling Reconciliations
            </span>
            <div className="corrections-pills-list">
              {corrections.map(([heard, fixed], idx) => (
                <div key={idx} className="correction-item-tag">
                  <span className="heard-word">"{heard}"</span>
                  <IconChevronRight width="11" height="11" />
                  <span className="fixed-word">{fixed}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      
      {/* TABS */}
      <div className="horizontal-tabs-container">
        <nav className="horizontal-tabs-nav" role="tablist">
          {tabsConfig.map((t) => {
            const Icon = t.icon;
            const isActive = activeTab === t.id;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={isActive}
                className={`top-tab-btn ${isActive ? "active" : ""} ${t.isAlert ? "alert-tab" : ""}`}
                onClick={() => setActiveTab(t.id)}
              >
                <Icon width="14" height="14" className="tab-icon" />
                <span className="tab-label">{t.label}</span>
                {t.count !== null && (
                  <span
                    className={`tab-counter ${isActive ? "active-counter" : ""}`}
                  >
                    {t.count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      <main className="tab-content-viewport" role="tabpanel">
        {/* ========== DIAGNOSIS TAB ========== */}
        {activeTab === "Diagnosis" && (
          <div className="tab-pane diagnosis-pane">
            <div
              className="pane-section-header"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <h3>Diagnoses & Clinical Assessments</h3>
                <span className="section-count-tag">
                  {diagnoses.length} identified
                </span>
              </div>
              <button className="add-item-btn" onClick={startAddDx}>
                <IconPlus width="14" height="14" />
                <span>Add Diagnosis</span>
              </button>
            </div>

            {diagnoses.length === 0 ? (
              <div className="empty-results-box">
                <IconActivity width="28" height="28" className="empty-svg" />
                <p className="empty-title">No diagnoses recorded</p>
              </div>
            ) : (
              <div className="cards-grid">
                {diagnoses.map((d) => (
                  <div
                    key={d.id}
                    className="clinical-card"
                  >
                    <div className="card-top-row">
                      <span className="card-title-text">{d.name}</span>
                      <div className="card-tags-group">
                        <span className="status-tag neutral">{d.status?.replace(/_/g, " ")}</span>
                        <span className="term-tag">{d.term === "long_term" ? "long-term" : "short-term"}</span>
                        {d.source === "ai" && (
                          <span className="status-tag dim">AI</span>
                        )}
                      </div>
                    </div>
                    <div className="card-bottom-row">
                      <span className="kv-pair">
                        <span className="kv-key">type:</span>{" "}
                        <span className="kv-val">
                          {d.dx_type || "not specified"}
                        </span>
                      </span>
                      <span className="kv-pair">
                        <span className="kv-key">speaker:</span>{" "}
                        <span className="kv-val">{d.speaker || "unclear"}</span>
                      </span>
                    </div>
                    <div className="card-actions">
                      <button
                        className="card-action-btn edit-btn"
                        onClick={() => startEditDx(d)}
                      >
                        <IconEdit width="12" height="12" /> Edit
                      </button>
                      <button
                        className="card-action-btn delete-btn"
                        onClick={() => deleteDx(d.id)}
                      >
                        <IconTrash width="12" height="12" /> Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ========== MEDICATIONS TAB ========== */}
        {activeTab === "Medications" && (
          <div className="tab-pane medications-pane">
            <div className="pane-controls-row">
              <div className="pane-section-header">
                <h3>Medication Reconciliation</h3>
                <span className="section-count-tag">
                  {filteredMeds.length} of {medications.length}
                </span>
              </div>
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <div className="med-filter-pills">
                  {[
                    { id: "all", label: "All" },
                    { id: "new", label: "Prescribed" },
                    { id: "active", label: "Continued" },
                    { id: "stopped", label: "Discontinued" },
                    { id: "considered", label: "Considered" },
                  ].map((f) => (
                    <button
                      key={f.id}
                      className={`filter-pill ${medFilter === f.id ? "active" : ""}`}
                      onClick={() => setMedFilter(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
                <button className="add-item-btn" onClick={startAddMed}>
                  <IconPlus width="14" height="14" />
                  <span>Add Medication</span>
                </button>
              </div>
            </div>

            {filteredMeds.length === 0 ? (
              <div className="empty-results-box">
                <IconPill width="28" height="28" className="empty-svg" />
                <p className="empty-title">No medications match this filter</p>
              </div>
            ) : (
              <div className="med-list">
                  {filteredMeds.map((m) => {
                    const isStopped = m.status === "stopped";
                    const isConsidered =
                      m.status === "not_prescribed" ||
                      m.status === "patient_reported";
                    return (
                      <div
                        key={m.id}
                        className={`med-row ${isStopped || isConsidered ? "dim" : ""}`}
                      >
                        <div className="med-row-left">
                          <span className="med-name">{m.name}</span>
                          <div className="card-tags-group">
                            <span className="status-tag neutral">
                              {m.status?.replace(/_/g, " ")}
                            </span>
                            {m.source === "ai" && (
                              <span className="status-tag dim">AI</span>
                            )}
                          </div>
                        </div>
                      <div className="med-row-details">
                        {m.dose && (
                          <span className="kv-pair">
                            <span className="kv-key">dose:</span>{" "}
                            <span className="kv-val">{m.dose}</span>
                          </span>
                        )}
                        {m.frequency && (
                          <span className="kv-pair">
                            <span className="kv-key">freq:</span>{" "}
                            <span className="kv-val">{m.frequency}</span>
                          </span>
                        )}
                        {m.route && (
                          <span className="kv-pair">
                            <span className="kv-key">route:</span>{" "}
                            <span className="kv-val">{m.route}</span>
                          </span>
                        )}
                        {m.duration && (
                          <span className="kv-pair">
                            <span className="kv-key">for:</span>{" "}
                            <span className="kv-val">{m.duration}</span>
                          </span>
                        )}
                      </div>
                      <div className="med-row-actions">
                        <button
                          className="card-action-btn edit-btn"
                          onClick={() => startEditMed(m)}
                        >
                          <IconEdit width="12" height="12" /> Edit
                        </button>
                        <button
                          className="card-action-btn delete-btn"
                          onClick={() => deleteMed(m.id)}
                        >
                          <IconTrash width="12" height="12" /> Delete
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Care tabs stay exactly as before */}
        {careKind && (
          <CareList
            key={careKind}
            kind={careKind}
            encounterId={data.id}
            items={care[careKind] || []}
            onChange={(items) => setCare((c) => ({ ...c, [careKind]: items }))}
          />
        )}

        {/* ===== the rest of the tabs stay unchanged ===== */}
        {/* (Allergies, History, Instructions, Findings, Transcription, SOAP) */}
        {/* You can keep the exact same JSX you already had for those tabs */}

        {activeTab === "Allergies" && (
          <div className="tab-pane allergies-pane">
            <div className="pane-section-header">
              <h3>Allergies & Adverse Drug Reactions</h3>
              <span className="section-count-tag alert-tag">
                {allergies.length} documented
              </span>
            </div>
            {allergies.length === 0 ? (
              <div className="empty-results-box safe-box">
                <IconCheckCircle
                  width="28"
                  height="28"
                  className="empty-svg safe-icon"
                />
                <p className="empty-title">No documented drug allergies</p>
              </div>
            ) : (
              <div className="cards-grid">
                {allergies.map((a, i) => (
                  <div key={i} className="clinical-card allergy-card">
                    <div className="card-top-row">
                      <span className="card-title-text">
                        {cleanVal(a.detail || a.name)}
                      </span>
                      <span className="status-tag neutral">
                        Reported Allergy
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "Medical History" && (
          <div className="tab-pane history-pane">
            <div className="pane-section-header">
              <h3>Medical, Family & Social History</h3>
              <span className="section-count-tag">{history.length} items</span>
            </div>
            {history.length === 0 ? (
              <div className="empty-results-box">
                <p className="empty-title">No historical conditions noted</p>
              </div>
            ) : (
              <div className="cards-grid">
                {history.map((h, i) => (
                  <div key={i} className="clinical-card history-card-item">
                    <div className="card-top-row">
                      <span className="card-title-text">{h.detail}</span>
                      <span className="status-tag neutral">
                        {(h.category || "History").replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "Instructions" && (
          <div className="tab-pane instructions-pane">
            <div className="pane-section-header">
              <h3>Discharge & Follow-Up Instructions</h3>
              <span className="section-count-tag">
                {instructions.length} items
              </span>
            </div>
            {instructions.length === 0 ? (
              <div className="empty-results-box">
                <p className="empty-title">
                  No follow-up instructions recorded
                </p>
              </div>
            ) : (
              <div className="cards-grid">
                {instructions.map((inst, i) => (
                  <div key={i} className="clinical-card instruction-card">
                    <div className="card-top-row">
                      <span className="card-title-text">{inst.detail}</span>
                      <span className="status-tag neutral">
                        {(inst.category || "Follow-up").replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "Clinical Findings" && (
          <div className="tab-pane findings-pane">
            <div className="pane-section-header">
              <h3>Diagnostic Observations & Tests</h3>
              <span className="section-count-tag">
                {findings.length} findings
              </span>
            </div>
            {findings.length === 0 ? (
              <div className="empty-results-box">
                <p className="empty-title">
                  No physical or diagnostic findings recorded
                </p>
              </div>
            ) : (
              <div className="cards-grid">
                {findings.map((f, i) => (
                  <div key={i} className="clinical-card finding-card">
                    <div className="card-top-row">
                      <span className="card-title-text">{f.detail}</span>
                      <span className="status-tag neutral">
                        {(f.category || "Finding").replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "Transcription" && (
          <div className="tab-pane transcription-pane">
            <div className="pane-section-header">
              <div>
                <h3>Uploaded Dialogue & Transcription</h3>
              </div>
              <button
                className="copy-soap-inner-btn"
                onClick={handleCopyTranscript}
              >
                {copiedTranscript ? (
                  <IconCheck width="14" height="14" />
                ) : (
                  <IconCopy width="14" height="14" />
                )}
                <span>
                  {copiedTranscript ? "Copied Transcript" : "Copy Dialogue"}
                </span>
              </button>
            </div>
            {!rawTranscript ? (
              <div className="empty-results-box">
                <IconTerminal width="28" height="28" className="empty-svg" />
                <p className="empty-title">No transcript available</p>
              </div>
            ) : (
              <div className="transcript-box-container">
                <div className="transcript-body">
                  {transcriptLines.map((line, idx) => {
                    const isDoctor = /^doctor:/i.test(line);
                    const isPatient = /^patient:/i.test(line);
                    return (
                      <div
                        key={idx}
                        className={`transcript-line ${isDoctor ? "doctor-line" : isPatient ? "patient-line" : ""}`}
                      >
                        {line}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "SOAP Note" && (
          <div className="tab-pane soap-pane">
            <div className="pane-section-header">
              <div>
                <h3>Standard Structured SOAP Clinical Note</h3>
              </div>
              <button className="copy-soap-inner-btn" onClick={handleCopySoap}>
                {copiedSoap ? (
                  <IconCheck width="14" height="14" />
                ) : (
                  <IconCopy width="14" height="14" />
                )}
                <span>
                  {copiedSoap ? "Copied to Clipboard" : "Copy Complete Note"}
                </span>
              </button>
            </div>
            {!soap ? (
              <div className="empty-results-box">
                <p className="empty-title">No SOAP note submitted</p>
              </div>
            ) : (
              <div className="soap-quad-grid">
                <div className="soap-box soap-s">
                  <div className="soap-letter-badge">S</div>
                  <div className="soap-box-content">
                    <h4>Subjective</h4>
                    <p>
                      {soap.subjective || "No subjective findings recorded."}
                    </p>
                  </div>
                </div>
                <div className="soap-box soap-o">
                  <div className="soap-letter-badge">O</div>
                  <div className="soap-box-content">
                    <h4>Objective</h4>
                    <p>
                      {soap.objective ||
                        "No objective examination or lab findings recorded."}
                    </p>
                  </div>
                </div>
                <div className="soap-box soap-a">
                  <div className="soap-letter-badge">A</div>
                  <div className="soap-box-content">
                    <h4>Assessment</h4>
                    <p>
                      {soap.assessment || "No clinical assessment recorded."}
                    </p>
                  </div>
                </div>
                <div className="soap-box soap-p">
                  <div className="soap-letter-badge">P</div>
                  <div className="soap-box-content">
                    <h4>Plan</h4>
                    <p>
                      {soap.plan || "No clinical management plan recorded."}
                    </p>
                  </div>
                </div>
                {soap.summary && (
                  <div className="soap-box soap-summary wide-soap">
                    <div className="soap-letter-badge">✦</div>
                    <div className="soap-box-content">
                      <h4>Encounter Summary</h4>
                      <p>{soap.summary}</p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
      {/* ===== MODALS ===== */}
      <EditModal
        open={editingDx !== null}
        title={editingDx === "new" ? "Add Diagnosis" : "Edit Diagnosis"}
        fields={DX_FIELDS}
        values={dxForm}
        onChange={(key, val) => setDxForm((prev) => ({ ...prev, [key]: val }))}
        onSave={saveDx}
        onClose={cancelDx}
      />

      <EditModal
        open={editingMed !== null}
        title={editingMed === "new" ? "Add Medication" : "Edit Medication"}
        fields={MED_FIELDS}
        values={medForm}
        onChange={(key, val) => setMedForm((prev) => ({ ...prev, [key]: val }))}
        onSave={saveMed}
        onClose={cancelMed}
      />
    </div>
  );
}
