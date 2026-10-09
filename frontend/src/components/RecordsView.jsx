import React, { useState, useEffect, useMemo } from "react";
import {
  IconSearch,
  IconRefresh,
  IconX,
  IconActivity,
  IconPill,
  IconFileText,
  IconChevronRight,
  IconCheckCircle
} from "./icons";

export function RecordsView({ onSelectRecord, onNewEncounter, refreshTrigger }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(6);

  const fetchRecords = async (query = "") => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/encounters?q=${encodeURIComponent(query)}`);
      if (!res.ok) throw new Error("Failed to load records");
      const data = await res.json();
      setRecords(data);
    } catch (err) {
      setError(err.message || "Failed to load past encounters");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchRecords(searchQuery);
      setCurrentPage(1); // Reset to page 1 on search change
    }, 250);
    return () => clearTimeout(timer);
  }, [searchQuery, refreshTrigger]);

  const formatDate = (dateStr) => {
    if (!dateStr) return "N/A";
    try {
      const d = new Date(dateStr.replace(" ", "T"));
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
    } catch {
      return dateStr;
    }
  };

  // Pagination calculations
  const totalItems = records.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / itemsPerPage));

  const paginatedRecords = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return records.slice(startIndex, startIndex + itemsPerPage);
  }, [records, currentPage, itemsPerPage]);

  const handlePageChange = (page) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  return (
    <div className="records-view-container">
      {/* Top Header Card */}
      <div className="records-header-card">
        <div className="records-header-left">
          <div className="records-badge">
            <span className="records-badge-dot" />
            Previous Uploads & Archives
          </div>
          <h2 className="records-heading">Consultation Records</h2>
          <p className="records-subtext">
            Browse through previously analyzed clinical encounters, review extracted diagnoses, and inspect generated SOAP notes.
          </p>
        </div>

        <div className="records-header-right">
          <button className="btn-primary-new" onClick={onNewEncounter}>
            + New Consultation
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="records-filter-toolbar">
        <div className="records-search-box">
          <IconSearch className="search-icon" width="16" height="16" />
          <input
            type="text"
            placeholder="Search by diagnosis, medication, title..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search records"
          />
          {searchQuery && (
            <button
              className="clear-search-btn"
              onClick={() => setSearchQuery("")}
              aria-label="Clear search"
            >
              <IconX width="14" height="14" />
            </button>
          )}
        </div>

        <div className="toolbar-controls">
          <div className="items-per-page-select">
            <span>Show:</span>
            <select
              value={itemsPerPage}
              onChange={(e) => {
                setItemsPerPage(Number(e.target.value));
                setCurrentPage(1);
              }}
            >
              <option value={6}>6 per page</option>
              <option value={8}>8 per page</option>
              <option value={12}>12 per page</option>
              <option value={20}>20 per page</option>
            </select>
          </div>

          <button
            className="btn-refresh-records"
            onClick={() => fetchRecords(searchQuery)}
            title="Refresh records list"
            disabled={loading}
          >
            <IconRefresh className={loading ? "spin" : ""} width="14" height="14" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Main Records List / Table */}
      <div className="records-content-card">
        {loading && records.length === 0 ? (
          <div className="records-loading-skeleton">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="record-row-skeleton" />
            ))}
          </div>
        ) : error ? (
          <div className="records-error-box">{error}</div>
        ) : records.length === 0 ? (
          <div className="records-empty-state">
            <IconFileText width="40" height="40" className="empty-state-icon" />
            <h3 className="empty-state-title">No consultation records found</h3>
            <p className="empty-state-desc">
              {searchQuery
                ? "No uploaded consultations match your search criteria. Try using different keywords."
                : "No consultations have been uploaded yet. Start by uploading an audio recording or transcript."}
            </p>
            {searchQuery ? (
              <button className="btn-secondary" onClick={() => setSearchQuery("")}>
                Clear Filter
              </button>
            ) : (
              <button className="btn-primary-new" onClick={onNewEncounter}>
                Upload First Consultation
              </button>
            )}
          </div>
        ) : (
          <div className="records-table-wrapper">
            <table className="records-table">
              <thead>
                <tr>
                  <th style={{ width: "60px" }}>ID</th>
                  <th>Consultation Title</th>
                  <th style={{ width: "200px" }}>Date & Time</th>
                  <th>Clinical Highlights</th>
                  <th style={{ width: "130px" }}>Status</th>
                  <th style={{ width: "120px", textAlign: "right" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {paginatedRecords.map((rec) => (
                  <tr
                    key={rec.id}
                    className="record-row"
                    onClick={() => onSelectRecord(rec.id)}
                  >
                    <td>
                      <span className="record-id-badge">#{rec.id}</span>
                    </td>
                    <td>
                      <div className="record-title-cell">
                        <span className="record-main-title">{rec.title}</span>
                      </div>
                    </td>
                    <td>
                      <span className="record-date-text">{formatDate(rec.created_at)}</span>
                    </td>
                    <td>
                      <div className="record-tags-cell">
                        {rec.diagnoses && (
                          <span className="rec-pill dx-pill" title={`Diagnoses: ${rec.diagnoses}`}>
                            <IconActivity width="12" height="12" />
                            <span className="pill-text">{rec.diagnoses}</span>
                          </span>
                        )}
                        {rec.medications && (
                          <span className="rec-pill med-pill" title={`Medications: ${rec.medications}`}>
                            <IconPill width="12" height="12" />
                            <span className="pill-text">{rec.medications}</span>
                          </span>
                        )}
                        {!rec.diagnoses && !rec.medications && (
                          <span className="rec-pill default-pill">General Consultation</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className="record-status-tag">
                        <IconCheckCircle width="13" height="13" />
                        <span>SOAP Ready</span>
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        className="btn-view-record"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectRecord(rec.id);
                        }}
                      >
                        <span>View</span>
                        <IconChevronRight width="13" height="13" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        {records.length > 0 && (
          <div className="pagination-bar">
            <div className="pagination-info">
              Showing <b>{(currentPage - 1) * itemsPerPage + 1}</b> to{" "}
              <b>{Math.min(currentPage * itemsPerPage, totalItems)}</b> of <b>{totalItems}</b> records
            </div>

            <div className="pagination-controls">
              <button
                className="page-nav-btn"
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
              >
                Previous
              </button>

              <div className="page-numbers-list">
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => {
                  // Show current page, edges, and nearby pages
                  if (
                    pageNum === 1 ||
                    pageNum === totalPages ||
                    (pageNum >= currentPage - 1 && pageNum <= currentPage + 1)
                  ) {
                    return (
                      <button
                        key={pageNum}
                        className={`page-num-btn ${currentPage === pageNum ? "active" : ""}`}
                        onClick={() => handlePageChange(pageNum)}
                      >
                        {pageNum}
                      </button>
                    );
                  }
                  if (pageNum === currentPage - 2 || pageNum === currentPage + 2) {
                    return (
                      <span key={pageNum} className="pagination-ellipsis">
                        …
                      </span>
                    );
                  }
                  return null;
                })}
              </div>

              <button
                className="page-nav-btn"
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage === totalPages}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
