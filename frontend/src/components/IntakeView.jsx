import { useState, useEffect, useRef } from "react";
import {
  IconSparkles,
  IconMicrophone,
  IconFileText,
  IconAlertTriangle,
  IconX,
  IconCheckCircle,
} from "./icons";
import { LiveRecorder } from "./LiveRecorder";

const SAMPLE_TRANSCRIPT = `Doctor: What brings you in today?
Patient: A cough and fever for five days.
Doctor: I think this could be bronchitis. Let me check your X-ray.
Doctor: The X-ray confirms pneumonia, so it's not bronchitis.
Doctor: I was considering amoxicillin.
Patient: I had a rash with amoxicillin before.
Doctor: Then don't take it. I'll prescribe azithromycin 500 mg once daily for 5 days.
Patient: I also take metformin.
Doctor: Keep taking metformin. Follow up in one week.`;

/* Custom patient autocomplete — replaces native datalist */
function PatientAutocomplete({ value, onChange, patients }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const filtered = value.trim()
    ? patients.filter((p) => p.name.toLowerCase().includes(value.toLowerCase()))
    : patients;

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="patient-autocomplete" ref={ref}>
      <label className="patient-field">
        Patient name
        <input
          type="text"
          value={value}
          onChange={(e) => { onChange(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder="Search or enter a new patient name"
          autoComplete="off"
        />
      </label>
      {open && filtered.length > 0 && (
        <ul className="patient-dropdown">
          {filtered.slice(0, 8).map((p) => (
            <li
              key={p.id}
              className="patient-dropdown-item"
              onMouseDown={(e) => { e.preventDefault(); onChange(p.name); setOpen(false); }}
            >
              <div className="patient-dropdown-avatar">{p.name[0]?.toUpperCase()}</div>
              <span>{p.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function IntakeView({ onAnalysisComplete, preselectedPatient }) {
  const [text, setText] = useState("");
  const [busyState, setBusyState] = useState(""); // "" | "transcribing" | "analyzing"
  const [errorMsg, setErrorMsg] = useState("");
  const [clinicalAlert, setClinicalAlert] = useState(false);
  const [notice, setNotice] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [patientName, setPatientName] = useState(preselectedPatient?.name || "");
  const [patients, setPatients] = useState([]);
  const [isLiveRecording, setIsLiveRecording] = useState(false);
  const textareaRef = useRef(null);

  // Sync patient name when preselectedPatient changes (e.g. navigating from different patient)
  useEffect(() => {
    if (preselectedPatient) setPatientName(preselectedPatient.name);
  }, [preselectedPatient?.id]);

  useEffect(() => {
    if (isLiveRecording && textareaRef.current) {
      textareaRef.current.scrollTop = textareaRef.current.scrollHeight;
    }
  }, [text, isLiveRecording]);

  useEffect(() => {
    fetch("/api/patients")
      .then((r) => (r.ok ? r.json() : []))
      .then(setPatients)
      .catch(() => {});
  }, []);

  // Helper for API calls
  async function apiCall(path, options) {
    const res = await fetch(path, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(
        data.detail || `Request failed with status ${res.status}`,
      );
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function isNonClinicalError(err) {
    return (
      err.status === 422 &&
      /no clinical (information|content)|not a medical conversation/i.test(
        err.message,
      )
    );
  }

  async function handleFile(file) {
    if (!file) return;
    setErrorMsg("");
    setClinicalAlert(false);
    setNotice("");
    setSelectedFile(file);

    // Text file directly loads into editor
    if (file.name.toLowerCase().endsWith(".txt")) {
      try {
        const fileContent = await file.text();
        setText(fileContent);
        setNotice("Transcript successfully loaded from text file.");
        // eslint-disable-next-line no-unused-vars
      } catch (e) {
        setErrorMsg("Failed to read text file.");
      }
      return;
    }

    // Audio file goes through local transcription
    setBusyState("transcribing");
    setNotice("Transcribing audio locally. Please hold on...");

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await apiCall("/api/transcribe", {
        method: "POST",
        body: formData,
      });
      setText(res.transcript);
      setNotice(
        res.warning ||
          "Audio transcribed successfully. Please review speaker labels and clinical terms.",
      );
    } catch (err) {
      setErrorMsg(err.message || "Failed to transcribe audio.");
      setNotice("");
    } finally {
      setBusyState("");
    }
  }

  function onFileInputChange(e) {
    const file = e.currentTarget.files?.[0];
    e.currentTarget.value = "";
    if (file) handleFile(file);
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  async function handleRunAnalysis() {
    if (!text.trim()) return;
    setBusyState("analyzing");
    setErrorMsg("");
    setClinicalAlert(false);

    try {
      const formData = new FormData();
      formData.append("text", text);
      if (preselectedPatient?.id) {
        formData.append("patient_id", preselectedPatient.id);
      } else if (patientName.trim()) {
        formData.append("patient_name", patientName.trim());
      }
      const result = await apiCall("/api/encounters", {
        method: "POST",
        body: formData,
      });
      // If updated transcript was formatted by backend, update state
      if (result.transcript) setText(result.transcript);
      onAnalysisComplete(result);
    } catch (err) {
      if (isNonClinicalError(err)) {
        setClinicalAlert(true);
      } else {
        setErrorMsg(
          err.message || "An error occurred during consultation analysis.",
        );
      }
    } finally {
      setBusyState("");
    }
  }

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
  const lineCount = text.trim() ? text.split("\n").length : 0;
  const estDuration = Math.max(1, Math.round(wordCount / 130));

  const insertSpeakerTag = (tag) => {
    const prefix = text && !text.endsWith("\n") ? "\n" : "";
    setText((prev) => prev + prefix + tag + " ");
  };

  return (
    <div className="intake-wrapper">
      {/* Top Intake Banner */}
      <div className="intake-hero">
        <div className="intake-hero-text">
          <div className="hero-badge">
            <span className="hero-badge-dot" />
            Clinical Intake Engine
          </div>
          <h2 className="hero-heading">New Clinical Encounter</h2>
          <p className="hero-subtext">
            Upload consultation recordings or enter transcripts to automatically
            extract diagnoses, medications, allergies, and generate standard
            SOAP notes.
          </p>
        </div>

        <div className="intake-steps">
          <div className="step-pill active">
            <span className="step-num">1</span>
            <span>Source Input</span>
          </div>
          <div className="step-divider" />
          <div className="step-pill">
            <span className="step-num">2</span>
            <span>Review Transcript</span>
          </div>
          <div className="step-divider" />
          <div className="step-pill">
            <span className="step-num">3</span>
            <span>SOAP Analysis</span>
          </div>
        </div>
      </div>

      {/* Main Two-Column Intake Grid */}
      <div className="intake-grid">
        {/* Left Column: Upload & Controls */}
        <div className="intake-card upload-card">
          <div className="intake-card-head">
            {preselectedPatient ? (
              <div className="patient-preselected-badge">
                
                <div className="patient-preselected-info">
                  <span className="patient-preselected-label">Patient</span>
                  <span className="patient-preselected-name">{preselectedPatient.name}</span>
                </div>
              </div>
            ) : (
              <PatientAutocomplete
                value={patientName}
                onChange={setPatientName}
                patients={patients}
              />
            )}
            <span className="file-chip">Audio & Text</span>
          </div>

          {/* Drag & Drop Zone */}
          <LiveRecorder
            onStreamUpdate={(streamText) => {
              setText(streamText);
              setSelectedFile(null);
            }}
            onTranscript={(t) => {
              setText(t);
              setSelectedFile(null);
              setNotice(
                "Live transcript updated. Speakers were labeled automatically, so check Doctor and Patient before analysis.",
              );
            }}
            onStatusChange={(status) => {
              setIsLiveRecording(status === "recording" || status === "loading" || status === "finishing");
              if (status === "recording") {
                setNotice("Recording active: speak into your microphone. Transcribed text is streaming directly into the Consultation Transcript box.");
              }
            }}
          />
          <label
            className={`intake-dropzone ${isDragging ? "dragging" : ""} ${
              busyState === "transcribing" ? "is-transcribing" : ""
            }`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept=".txt,.mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac,.mpeg,.mpga,audio/*"
              onChange={onFileInputChange}
              disabled={Boolean(busyState)}
            />

            <div className="dropzone-inner">
              <div className="soundwave-avatar">
                {busyState === "transcribing" ? (
                  <div className="soundwave-animating">
                    <span />
                    <span />
                    <span />
                    <span />
                    <span />
                  </div>
                ) : (
                  <div className="soundwave-static">
                    <IconMicrophone width="22" height="22" />
                  </div>
                )}
              </div>

              <div className="dropzone-text">
                <span className="primary-prompt">
                  {busyState === "transcribing"
                    ? "Transcribing audio locally..."
                    : "Drop recording or transcript file here"}
                </span>
                <span className="secondary-prompt">
                  Supports MP3, WAV, M4A, FLAC, WebM, and TXT files
                </span>
              </div>

              <span className="btn-browse-file">Browse File</span>
            </div>
          </label>

          {/* Selected File Details */}
          {selectedFile && (
            <div className="file-preview-card">
              <div className="file-info-col">
                <div className="file-type-icon">
                  {selectedFile.type.startsWith("audio") ||
                  selectedFile.name.match(/\.(mp3|wav|m4a|flac|ogg)$/i) ? (
                    <IconMicrophone width="16" height="16" />
                  ) : (
                    <IconFileText width="16" height="16" />
                  )}
                </div>
                <div className="file-meta">
                  <span className="file-title">{selectedFile.name}</span>
                  <span className="file-size">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </span>
                </div>
              </div>
              <button
                className="btn-remove-file"
                onClick={() => setSelectedFile(null)}
                title="Remove selected file"
                aria-label="Remove selected file"
              >
                <IconX width="14" height="14" />
              </button>
            </div>
          )}

          {/* Quick Intake Actions */}
          <div className="quick-actions-bar">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setText(SAMPLE_TRANSCRIPT);
                setSelectedFile(null);
                setNotice(
                  "Standard clinical sample loaded. Review or modify transcript.",
                );
                setErrorMsg("");
                setClinicalAlert(false);
              }}
              disabled={Boolean(busyState)}
            >
              <IconSparkles width="15" height="15" />
              <span>Load Clinical Sample</span>
            </button>

            {text && (
              <button
                type="button"
                className="btn-outline-danger"
                onClick={() => {
                  setText("");
                  setSelectedFile(null);
                  setNotice("");
                  setErrorMsg("");
                  setClinicalAlert(false);
                }}
                disabled={Boolean(busyState)}
              >
                Clear
              </button>
            )}
          </div>

          {/* Status Banners */}
          {notice && !errorMsg && (
            <div className="status-toast info">
              <IconCheckCircle width="16" height="16" />
              <span>{notice}</span>
            </div>
          )}

          {errorMsg && (
            <div className="status-toast error">
              <IconAlertTriangle width="16" height="16" />
              <span>{errorMsg}</span>
            </div>
          )}

          {clinicalAlert && (
            <div className="clinical-warning-box">
              <div className="warning-head">
                <IconAlertTriangle width="18" height="18" />
                <h4>Clinical Consultation Required</h4>
              </div>
              <p>
                The analyzer is configured specifically for healthcare
                consultations between a clinician and a patient. Please provide
                clinical dialogue containing symptoms, medical history, or
                treatment plans.
              </p>
              <button
                className="btn-dismiss-warning"
                onClick={() => setClinicalAlert(false)}
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Primary Action Button */}
          <div className="run-action-wrap">
            <button
              className="btn-run-analysis"
              onClick={handleRunAnalysis}
              disabled={Boolean(busyState) || !text.trim()}
            >
              {busyState === "analyzing" ? (
                <>
                  <span className="spinner-dot" />
                  <span>Extracting Clinical Entities & SOAP...</span>
                </>
              ) : busyState === "transcribing" ? (
                <>
                  <span className="spinner-dot" />
                  <span>Transcribing Audio...</span>
                </>
              ) : (
                <>
                  <IconSparkles width="18" height="18" />
                  <span>Analyze Consultation</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Right Column: Transcript Editor */}
        <div className="intake-card transcript-card">
          <div className="intake-card-head">
            <div className="card-head-title">
              <IconFileText className="head-icon" width="18" height="18" />
              <h3>Consultation Transcript</h3>
              {isLiveRecording && (
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "0.75rem",
                    padding: "2px 8px",
                    borderRadius: "12px",
                    backgroundColor: "rgba(239, 68, 68, 0.12)",
                    color: "#ef4444",
                    fontWeight: 600,
                    border: "1px solid rgba(239, 68, 68, 0.3)",
                    marginLeft: "8px",
                  }}
                >
                  <span
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      backgroundColor: "#ef4444",
                      boxShadow: "0 0 6px #ef4444",
                    }}
                  />
                  Live Streaming
                </span>
              )}
            </div>

            <div className="transcript-meta-chips">
              <span className="meta-chip">
                <b>{wordCount}</b> words
              </span>
              <span className="meta-chip">
                <b>{lineCount}</b> lines
              </span>
              {wordCount > 0 && (
                <span className="meta-chip duration-chip">
                  ~{estDuration} min dialogue
                </span>
              )}
            </div>
          </div>

          {/* Speaker quick insert tags */}
          <div className="speaker-tag-bar">
            <span className="tag-bar-label">Insert Speaker:</span>
            <button
              type="button"
              className="speaker-insert-pill doctor-pill"
              onClick={() => insertSpeakerTag("Doctor:")}
              title="Add Doctor speaker label"
            >
              + Doctor:
            </button>
            <button
              type="button"
              className="speaker-insert-pill patient-pill"
              onClick={() => insertSpeakerTag("Patient:")}
              title="Add Patient speaker label"
            >
              + Patient:
            </button>
          </div>

          {/* Editor area */}
          <div className="editor-container">
            <textarea
              ref={textareaRef}
              className="clinical-textarea"
              placeholder={
                isLiveRecording
                  ? "Listening to microphone... Transcribed dialogue will appear here live as speech is detected."
                  : busyState === "transcribing"
                  ? "Transcribing audio locally... Speech will appear here when complete."
                  : `Doctor: What brings you in today?\nPatient: I have had a severe cough and fever for three days.\nDoctor: Let me check your chest and discuss treatment...`
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
              aria-label="Clinical Consultation Transcript"
              spellCheck="false"
            />
          </div>

          <div className="editor-footer-note">
            <p>
              💡 <b>Tip:</b> Dialogue formatted with <code>Doctor:</code> and{" "}
              <code>Patient:</code> speaker prefixes ensures the highest entity
              extraction accuracy and precise medication attribution.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
