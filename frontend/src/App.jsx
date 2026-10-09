import { useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { IntakeView } from "./components/IntakeView";
import { RecordsView } from "./components/RecordsView";
import { ResultsView } from "./components/ResultsView";
import { PatientsView } from "./components/PatientsView";
import { IconMenu, IconStethoscope } from "./components/icons";
import "./App.css";

export default function App() {
  const [currentView, setCurrentView] = useState("patients"); // "upload" | "records" | "patients" | "results"
  const [result, setResult] = useState(null);
  const [selectedEncounterId, setSelectedEncounterId] = useState(null);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [historyRefreshTrigger, setHistoryRefreshTrigger] = useState(0);
  const [preselectedPatient, setPreselectedPatient] = useState(null); // { id, name }

  // When a new analysis finishes in IntakeView
  const handleAnalysisComplete = (newResult) => {
    setResult(newResult);
    if (newResult.id) {
      setSelectedEncounterId(newResult.id);
    }
    setPreselectedPatient(null);
    setCurrentView("results");
    setHistoryRefreshTrigger((prev) => prev + 1);
  };

  // Navigate to New Consultation with a patient pre-filled
  const handleNewConsultationForPatient = (patient) => {
    setPreselectedPatient(patient); // { id, name }
    setCurrentView("upload");
  };

  // Select an encounter from the Records or Patients view
  const handleSelectRecord = async (encounterId) => {
    try {
      const res = await fetch(`/api/encounters/${encounterId}`);
      if (!res.ok) throw new Error("Failed to load encounter");
      const enc = await res.json();
      setResult({
        id: enc.id,
        title: enc.title,
        ...enc.result,
      });
      setSelectedEncounterId(encounterId);
      setCurrentView("results");
    } catch (err) {
      console.error("Error loading encounter:", err);
      alert("Could not load encounter details. Please try again.");
    }
  };

  return (
    <div className="clinical-app-layout">
      <Sidebar
        currentView={currentView}
        onNavigate={(view) => {
          if (view === "upload") setPreselectedPatient(null);
          setCurrentView(view);
        }}
        hasActiveResult={Boolean(result)}
        selectedId={selectedEncounterId}
        isMobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        historyRefreshTrigger={historyRefreshTrigger}
      />

      <div className="main-workspace-shell">
        <header className="mobile-header-bar">
          <button
            className="mobile-menu-toggle-btn"
            onClick={() => setIsMobileSidebarOpen(true)}
            aria-label="Open navigation sidebar"
          >
            <IconMenu width="20" height="20" />
          </button>

          <div className="mobile-brand-title">
            <IconStethoscope width="18" height="18" className="mobile-steth-icon" />
            <span>ClinScribe AI</span>
          </div>

          <div className="mobile-status-tag">
            <span className="live-dot" />
            <span>Ready</span>
          </div>
        </header>

        <main className="content-viewport">
          {currentView === "upload" && (
            <IntakeView
              onAnalysisComplete={handleAnalysisComplete}
              preselectedPatient={preselectedPatient}
            />
          )}

          {currentView === "records" && (
            <RecordsView
              onSelectRecord={handleSelectRecord}
              onNewEncounter={() => setCurrentView("upload")}
              refreshTrigger={historyRefreshTrigger}
            />
          )}

          {currentView === "patients" && (
            <PatientsView
              onSelectRecord={handleSelectRecord}
              onNewConsultation={handleNewConsultationForPatient}
            />
          )}

          {currentView === "results" && result && (
            <>
              <ResultsView
                data={result}
                onNewEncounter={() => setCurrentView("upload")}
                onBackToRecords={() => setCurrentView("records")}
              />
            </>
          )}

          {currentView === "results" && !result && (
            <RecordsView
              onSelectRecord={handleSelectRecord}
              onNewEncounter={() => setCurrentView("upload")}
              refreshTrigger={historyRefreshTrigger}
            />
          )}
        </main>
      </div>
    </div>
  );
}
