import { useState, useEffect } from "react";
import {
  IconStethoscope,
  IconHistory,
  IconX,
  IconActivity,
  IconUpload,
} from "./icons";

export function Sidebar({
  currentView,
  onNavigate,
  hasActiveResult,
  selectedId,
  isMobileOpen,
  onCloseMobile,
  historyRefreshTrigger,
}) {
  const [recordCount, setRecordCount] = useState(0);

  useEffect(() => {
    fetch("/api/encounters")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setRecordCount(data.length))
      .catch(() => {});
  }, [historyRefreshTrigger]);

  const handleNav = (view) => {
    onNavigate(view);
    if (onCloseMobile) onCloseMobile();
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isMobileOpen && (
        <div
          className="sidebar-backdrop"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={`permanent-sidebar ${isMobileOpen ? "mobile-open" : ""}`}
      >
        {/* ─────────────────────────────
            BRAND
        ───────────────────────────── */}
        <div className="sidebar-brand">
          <div className="brand-icon">
            <IconStethoscope width="21" height="21" />
          </div>

          <div className="brand-info">
            <div className="brand-title-row">
              <span className="brand-name">ClinScribe</span>
              <span className="brand-badge">AI</span>
            </div>

            <span className="brand-subtitle">Clinical Documentation</span>
          </div>

          {/* Mobile close */}
          <button
            className="mobile-close-btn"
            onClick={onCloseMobile}
            aria-label="Close sidebar"
          >
            <IconX />
          </button>
        </div>

        {/* ─────────────────────────────
            NAVIGATION
        ───────────────────────────── */}
        <nav className="sidebar-nav-menu" aria-label="Main Navigation">
          <div className="nav-group-label">WORKSPACE</div>

          {/* Patients — default landing, shown first */}
          <button
            className={`nav-menu-item ${currentView === "patients" ? "active" : ""}`}
            onClick={() => handleNav("patients")}
          >
            <div className="nav-item-icon">
              <IconActivity width="18" height="18" />
            </div>
            <div className="nav-item-content">
              <span className="nav-item-title">Patients</span>
              <span className="nav-item-sub">Patient registry</span>
            </div>
          </button>

          {/* New Consultation */}
          <button
            className={`nav-menu-item ${currentView === "upload" ? "active" : ""}`}
            onClick={() => handleNav("upload")}
          >
            <div className="nav-item-icon">
              <IconUpload width="18" height="18" />
            </div>
            <div className="nav-item-content">
              <span className="nav-item-title">New Consultation</span>
              <span className="nav-item-sub">Upload audio or transcript</span>
            </div>
          </button>

          {/* Records */}
          <button
            className={`nav-menu-item ${currentView === "records" ? "active" : ""}`}
            onClick={() => handleNav("records")}
          >
            <div className="nav-item-icon">
              <IconHistory width="18" height="18" />
            </div>
            <div className="nav-item-content">
              <span className="nav-item-title">Encounter Records</span>
              <span className="nav-item-sub">Previous consultations</span>
            </div>
            {recordCount > 0 && (
              <span className="nav-badge-count">{recordCount}</span>
            )}
          </button>

          {/* Active encounter */}
          {hasActiveResult && (
            <>
              <div className="nav-section-divider" />
              <div className="nav-group-label">CURRENT ENCOUNTER</div>
              <button
                className={`nav-menu-item ${currentView === "results" ? "active" : ""}`}
                onClick={() => handleNav("results")}
              >
                <div className="nav-item-icon active-icon">
                  <IconStethoscope width="18" height="18" />
                </div>
                <div className="nav-item-content">
                  <span className="nav-item-title">Clinical Results</span>
                  <span className="nav-item-sub">
                    {selectedId ? `Encounter #${selectedId}` : "Current analysis"}
                  </span>
                </div>
                <span className="active-dot-indicator" />
              </button>
            </>
          )}
        </nav>

        {/* ─────────────────────────────
            FOOTER
        ───────────────────────────── */}
        <div className="sidebar-footer">
          <div className="clinical-status">
            <span className="status-dot" />

            <div>
              <span className="status-title">Clinical workspace</span>

              <span className="status-subtitle">Ready for consultation</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
