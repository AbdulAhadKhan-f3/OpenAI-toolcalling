"""SQLite storage. encounters (1) -> diagnoses (many), medications (many).
Also keeps result_json in sync so the rest of the app keeps working."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.logger import get_logger

log = get_logger(__name__)

DB_PATH = Path(__file__).parent / "clinical.db"

DIAGNOSIS_STATUSES = {"confirmed", "suspected", "ruled_out", "history"}
MEDICATION_STATUSES = {"prescribed", "dose_changed", "continued", "stopped", "not_prescribed", "patient_reported"}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init():
    log.debug("Initialising database at %s", DB_PATH)
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS encounters(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            title TEXT, transcript TEXT, complete INTEGER, result_json TEXT);

        CREATE TABLE IF NOT EXISTS diagnoses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            encounter_id INTEGER REFERENCES encounters(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            term TEXT DEFAULT '',
            dx_type TEXT DEFAULT '',
            evidence TEXT DEFAULT '',
            speaker TEXT DEFAULT 'unclear',
            note TEXT DEFAULT '',
            source TEXT DEFAULT 'manual',
            created_at TEXT,
            updated_at TEXT);

        CREATE TABLE IF NOT EXISTS medications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            encounter_id INTEGER REFERENCES encounters(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            dose TEXT DEFAULT '',
            route TEXT DEFAULT '',
            frequency TEXT DEFAULT '',
            timing TEXT DEFAULT '',
            duration TEXT DEFAULT '',
            status TEXT NOT NULL,
            indication TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            evidence TEXT DEFAULT '',
            speaker TEXT DEFAULT 'unclear',
            source TEXT DEFAULT 'manual',
            created_at TEXT,
            updated_at TEXT);
        """)
        # Lightweight migrations for existing databases
        for col, typedef in [
            ("diagnoses", "term TEXT DEFAULT ''"),
            ("diagnoses", "dx_type TEXT DEFAULT ''"),
            ("diagnoses", "speaker TEXT DEFAULT 'unclear'"),
            ("diagnoses", "note TEXT DEFAULT ''"),
            ("diagnoses", "source TEXT DEFAULT 'manual'"),
            ("diagnoses", "created_at TEXT"),
            ("diagnoses", "updated_at TEXT"),
            ("medications", "timing TEXT DEFAULT ''"),
            ("medications", "indication TEXT DEFAULT ''"),
            ("medications", "reason TEXT DEFAULT ''"),
            ("medications", "speaker TEXT DEFAULT 'unclear'"),
            ("medications", "source TEXT DEFAULT 'manual'"),
            ("medications", "created_at TEXT"),
            ("medications", "updated_at TEXT"),
        ]:
            try:
                c.execute(f"ALTER TABLE {col} ADD COLUMN {typedef}")
            except sqlite3.OperationalError:
                pass  # column already exists
    log.info("Database ready: %s", DB_PATH)


# ───────────────────────── helpers for result_json sync ─────────────────────────

def _load_result(c, eid):
    row = c.execute("SELECT result_json FROM encounters WHERE id = ?", (eid,)).fetchone()
    if not row:
        return None
    return json.loads(row["result_json"] or "{}")


def _save_result(c, eid, result):
    c.execute("UPDATE encounters SET result_json = ? WHERE id = ?",
              (json.dumps(result), eid))


def _rebuild_final_state(result):
    """Rebuild final_state from the current extractions lists (same logic as agent.to_final_state)."""
    from services.agent import to_final_state
    result["final_state"] = to_final_state(result.get("extractions", {}))
    return result


# ───────────────────────── original save (AI path) ─────────────────────────

def save(title, transcript, result) -> int:
    """Store the full result as JSON + normalised rows (source='ai')."""
    fs = result["final_state"]
    extractions = result.get("extractions", {})
    now = _now()
    try:
        with conn() as c:
            eid = c.execute(
                "INSERT INTO encounters(title, transcript, complete, result_json) VALUES(?,?,?,?)",
                (title, transcript, int(result["complete"]), json.dumps(result))).lastrowid

            for d in extractions.get("diagnoses", []):
                c.execute("""INSERT INTO diagnoses
                    (encounter_id, name, status, term, dx_type, evidence, speaker, note, source, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (eid,
                     d.get("name") or d.get("diagnosis") or "?",
                     d.get("status", "suspected"),
                     d.get("term", ""),
                     d.get("dx_type") or d.get("type") or "",
                     d.get("evidence", ""),
                     d.get("speaker", "unclear"),
                     d.get("note", ""),
                     "ai", now, now))

            for m in extractions.get("medications", []):
                c.execute("""INSERT INTO medications
                    (encounter_id, name, dose, route, frequency, timing, duration, status,
                     indication, reason, evidence, speaker, source, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (eid,
                     m.get("name", "?"),
                     m.get("dose", ""),
                     m.get("route", ""),
                     m.get("frequency", ""),
                     m.get("timing", ""),
                     m.get("duration", ""),
                     m.get("status", "prescribed"),
                     m.get("indication", ""),
                     m.get("reason", ""),
                     m.get("evidence", ""),
                     m.get("speaker", "unclear"),
                     "ai", now, now))

        log.info("Saved encounter #%d: '%s'", eid, title)
        return eid
    except Exception:
        log.error("Failed to save encounter '%s'", title, exc_info=True)
        raise


# ───────────────────────── list / get (unchanged behaviour) ─────────────────────────

def list_encounters(q: str = ""):
    with conn() as c:
        rows = c.execute("""
            SELECT e.id, e.created_at, e.title, e.complete,
              (SELECT group_concat(name, ', ') FROM diagnoses
                 WHERE encounter_id = e.id AND status = 'confirmed') AS diagnoses,
              (SELECT group_concat(name, ', ') FROM medications
                 WHERE encounter_id = e.id AND status IN ('prescribed','continued','dose_changed')) AS medications
            FROM encounters e
            WHERE :q = '' OR e.transcript LIKE :like
               OR EXISTS (SELECT 1 FROM diagnoses d WHERE d.encounter_id = e.id AND d.name LIKE :like)
               OR EXISTS (SELECT 1 FROM medications m WHERE m.encounter_id = e.id AND m.name LIKE :like)
            ORDER BY e.id DESC""", {"q": q, "like": f"%{q}%"}).fetchall()
    return [dict(r) for r in rows]


def get(eid: int):
    with conn() as c:
        r = c.execute("SELECT * FROM encounters WHERE id = ?", (eid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["result"] = json.loads(d.pop("result_json"))
    return d


# ───────────────────────── DIAGNOSES CRUD ─────────────────────────

def list_diagnoses(encounter_id: int):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM diagnoses WHERE encounter_id = ? ORDER BY id", (encounter_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_diagnosis(encounter_id: int, data: dict, source: str = "manual"):
    name = (data.get("name") or data.get("diagnosis") or "").strip()
    status = (data.get("status") or "suspected").strip()
    if not name:
        raise ValueError("Diagnosis name is required.")
    if status not in DIAGNOSIS_STATUSES:
        raise ValueError(f"status must be one of {sorted(DIAGNOSIS_STATUSES)}")

    now = _now()
    with conn() as c:
        cur = c.execute("""INSERT INTO diagnoses
            (encounter_id, name, status, term, dx_type, evidence, speaker, note, source, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (encounter_id, name, status,
             data.get("term", ""),
             data.get("dx_type", ""),
             data.get("evidence", ""),
             data.get("speaker", "unclear"),
             data.get("note", ""),
             source, now, now))
        item = dict(c.execute("SELECT * FROM diagnoses WHERE id = ?", (cur.lastrowid,)).fetchone())

        # keep result_json in sync
        result = _load_result(c, encounter_id)
        if result is not None:
            extractions = result.setdefault("extractions", {})
            diagnoses = extractions.setdefault("diagnoses", [])
            diagnoses.append({
                "name": item["name"], "status": item["status"], "term": item["term"],
                "dx_type": item["dx_type"], "evidence": item["evidence"],
                "speaker": item["speaker"], "note": item["note"],
            })
            _rebuild_final_state(result)
            _save_result(c, encounter_id, result)

    return item


def update_diagnosis(encounter_id: int, item_id: int, changes: dict):
    allowed = {}
    for k in ("name", "status", "term", "dx_type", "evidence", "speaker", "note"):
        if k in changes:
            allowed[k] = str(changes[k]).strip()
    if "status" in allowed and allowed["status"] not in DIAGNOSIS_STATUSES:
        raise ValueError(f"status must be one of {sorted(DIAGNOSIS_STATUSES)}")
    if not allowed:
        raise ValueError("No valid fields to update.")

    with conn() as c:
        sets = ", ".join(f"{k} = ?" for k in allowed)
        c.execute(f"UPDATE diagnoses SET {sets}, updated_at = ? WHERE id = ? AND encounter_id = ?",
                  [*allowed.values(), _now(), item_id, encounter_id])
        row = c.execute("SELECT * FROM diagnoses WHERE id = ? AND encounter_id = ?",
                        (item_id, encounter_id)).fetchone()
        if not row:
            return None
        item = dict(row)

        # sync result_json
        result = _load_result(c, encounter_id)
        if result is not None:
            diagnoses = result.get("extractions", {}).get("diagnoses", [])
            # replace by matching old name+status is fragile; we rebuild from the table instead
            table_rows = c.execute(
                "SELECT * FROM diagnoses WHERE encounter_id = ? ORDER BY id", (encounter_id,)
            ).fetchall()
            result.setdefault("extractions", {})["diagnoses"] = [
                {
                    "name": r["name"], "status": r["status"], "term": r["term"] or "",
                    "dx_type": r["dx_type"] or "", "evidence": r["evidence"] or "",
                    "speaker": r["speaker"] or "unclear", "note": r["note"] or "",
                }
                for r in table_rows
            ]
            _rebuild_final_state(result)
            _save_result(c, encounter_id, result)

    return item


def delete_diagnosis(encounter_id: int, item_id: int):
    with conn() as c:
        deleted = c.execute(
            "DELETE FROM diagnoses WHERE id = ? AND encounter_id = ?", (item_id, encounter_id)
        ).rowcount > 0
        if not deleted:
            return False

        result = _load_result(c, encounter_id)
        if result is not None:
            table_rows = c.execute(
                "SELECT * FROM diagnoses WHERE encounter_id = ? ORDER BY id", (encounter_id,)
            ).fetchall()
            result.setdefault("extractions", {})["diagnoses"] = [
                {
                    "name": r["name"], "status": r["status"], "term": r["term"] or "",
                    "dx_type": r["dx_type"] or "", "evidence": r["evidence"] or "",
                    "speaker": r["speaker"] or "unclear", "note": r["note"] or "",
                }
                for r in table_rows
            ]
            _rebuild_final_state(result)
            _save_result(c, encounter_id, result)
    return True


# ───────────────────────── MEDICATIONS CRUD ─────────────────────────

def list_medications(encounter_id: int):
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM medications WHERE encounter_id = ? ORDER BY id", (encounter_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_medication(encounter_id: int, data: dict, source: str = "manual"):
    name = (data.get("name") or "").strip()
    status = (data.get("status") or "prescribed").strip()
    if not name:
        raise ValueError("Medication name is required.")
    if status not in MEDICATION_STATUSES:
        raise ValueError(f"status must be one of {sorted(MEDICATION_STATUSES)}")

    now = _now()
    with conn() as c:
        cur = c.execute("""INSERT INTO medications
            (encounter_id, name, dose, route, frequency, timing, duration, status,
             indication, reason, evidence, speaker, source, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (encounter_id, name,
             data.get("dose", ""), data.get("route", ""), data.get("frequency", ""),
             data.get("timing", ""), data.get("duration", ""), status,
             data.get("indication", ""), data.get("reason", ""),
             data.get("evidence", ""), data.get("speaker", "unclear"),
             source, now, now))
        item = dict(c.execute("SELECT * FROM medications WHERE id = ?", (cur.lastrowid,)).fetchone())

        result = _load_result(c, encounter_id)
        if result is not None:
            meds = result.setdefault("extractions", {}).setdefault("medications", [])
            meds.append({
                "name": item["name"], "dose": item["dose"], "route": item["route"],
                "frequency": item["frequency"], "timing": item["timing"],
                "duration": item["duration"], "status": item["status"],
                "indication": item["indication"], "reason": item["reason"],
                "evidence": item["evidence"], "speaker": item["speaker"],
            })
            _rebuild_final_state(result)
            _save_result(c, encounter_id, result)

    return item


def update_medication(encounter_id: int, item_id: int, changes: dict):
    allowed = {}
    for k in ("name", "dose", "route", "frequency", "timing", "duration",
              "status", "indication", "reason", "evidence", "speaker"):
        if k in changes:
            allowed[k] = str(changes[k]).strip()
    if "status" in allowed and allowed["status"] not in MEDICATION_STATUSES:
        raise ValueError(f"status must be one of {sorted(MEDICATION_STATUSES)}")
    if not allowed:
        raise ValueError("No valid fields to update.")

    with conn() as c:
        sets = ", ".join(f"{k} = ?" for k in allowed)
        c.execute(f"UPDATE medications SET {sets}, updated_at = ? WHERE id = ? AND encounter_id = ?",
                  [*allowed.values(), _now(), item_id, encounter_id])
        row = c.execute("SELECT * FROM medications WHERE id = ? AND encounter_id = ?",
                        (item_id, encounter_id)).fetchone()
        if not row:
            return None
        item = dict(row)

        result = _load_result(c, encounter_id)
        if result is not None:
            table_rows = c.execute(
                "SELECT * FROM medications WHERE encounter_id = ? ORDER BY id", (encounter_id,)
            ).fetchall()
            result.setdefault("extractions", {})["medications"] = [
                {
                    "name": r["name"], "dose": r["dose"] or "", "route": r["route"] or "",
                    "frequency": r["frequency"] or "", "timing": r["timing"] or "",
                    "duration": r["duration"] or "", "status": r["status"],
                    "indication": r["indication"] or "", "reason": r["reason"] or "",
                    "evidence": r["evidence"] or "", "speaker": r["speaker"] or "unclear",
                }
                for r in table_rows
            ]
            _rebuild_final_state(result)
            _save_result(c, encounter_id, result)

    return item


def delete_medication(encounter_id: int, item_id: int):
    with conn() as c:
        deleted = c.execute(
            "DELETE FROM medications WHERE id = ? AND encounter_id = ?", (item_id, encounter_id)
        ).rowcount > 0
        if not deleted:
            return False

        result = _load_result(c, encounter_id)
        if result is not None:
            table_rows = c.execute(
                "SELECT * FROM medications WHERE encounter_id = ? ORDER BY id", (encounter_id,)
            ).fetchall()
            result.setdefault("extractions", {})["medications"] = [
                {
                    "name": r["name"], "dose": r["dose"] or "", "route": r["route"] or "",
                    "frequency": r["frequency"] or "", "timing": r["timing"] or "",
                    "duration": r["duration"] or "", "status": r["status"],
                    "indication": r["indication"] or "", "reason": r["reason"] or "",
                    "evidence": r["evidence"] or "", "speaker": r["speaker"] or "unclear",
                }
                for r in table_rows
            ]
            _rebuild_final_state(result)
            _save_result(c, encounter_id, result)
    return True