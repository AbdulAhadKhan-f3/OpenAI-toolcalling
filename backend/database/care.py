"""Patients, consults (with token cost), tasks, recalls and referrals.
Uses the same SQLite file as db.py but its own tables, so db.py does not need to change."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "clinical.db"      # the same file db.py opens
STATUSES = ("open", "done", "cancelled")
FIELDS = {                                                      # editable text columns for each kind
    "tasks": ("detail", "owner", "due"),
    "recalls": ("detail", "type", "due"),
    "referrals": ("refer_to", "detail", "urgency", "condition"),
}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")     # same format as db.py's CURRENT_TIMESTAMP


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _kind(kind):
    if kind not in FIELDS:
        raise ValueError(f"Unknown kind: {kind}")


def init():
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS consults (
                encounter_id INTEGER PRIMARY KEY, patient_id INTEGER, title TEXT DEFAULT '',
                diagnoses TEXT DEFAULT '', summary TEXT DEFAULT '', model TEXT DEFAULT '',
                input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, total_tokens INTEGER DEFAULT 0,
                cost_usd REAL, created_at TEXT NOT NULL);
        """)
        # Add extended patient fields — safe on older SQLite (3.37 added IF NOT EXISTS for ADD COLUMN)
        for col in ("date_of_birth TEXT DEFAULT ''", "gender TEXT DEFAULT ''",
                    "phone TEXT DEFAULT ''", "email TEXT DEFAULT ''", "notes TEXT DEFAULT ''"):
            try:
                con.execute(f"ALTER TABLE patients ADD COLUMN {col}")
            except Exception:
                pass  # column already exists
        for kind, cols in FIELDS.items():
            con.execute(f"""CREATE TABLE IF NOT EXISTS {kind} (
                id INTEGER PRIMARY KEY AUTOINCREMENT, encounter_id INTEGER, patient_id INTEGER,
                {', '.join(c + " TEXT DEFAULT ''" for c in cols)},
                status TEXT DEFAULT 'open', source TEXT DEFAULT 'manual', evidence TEXT DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")


# ---------- patients ----------
def find_or_create_patient(name):
    name = " ".join(str(name or "").split())
    if not name:
        return None
    with _conn() as con:
        row = con.execute("SELECT id FROM patients WHERE lower(name) = lower(?)", (name,)).fetchone()
        if row:
            return row["id"]
        return con.execute("INSERT INTO patients (name, created_at) VALUES (?, ?)", (name, _now())).lastrowid


def get_patient(patient_id):
    with _conn() as con:
        row = con.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    return dict(row) if row else None


PATIENT_FIELDS = ("name", "date_of_birth", "gender", "phone", "email", "notes")


def update_patient(patient_id, data):
    allowed = {k: str(v).strip() for k, v in data.items() if k in PATIENT_FIELDS and v is not None}
    if not allowed:
        return get_patient(patient_id)
    with _conn() as con:
        sets = ", ".join(f"{k} = ?" for k in allowed)
        con.execute(f"UPDATE patients SET {sets} WHERE id = ?", [*allowed.values(), patient_id])
        row = con.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    return dict(row) if row else None


def list_patients(q=""):
    with _conn() as con:
        rows = con.execute("""
            SELECT p.id, p.name, COUNT(c.encounter_id) AS consults, MAX(c.created_at) AS last_seen,
                   COALESCE(SUM(c.total_tokens), 0) AS total_tokens, SUM(c.cost_usd) AS total_cost_usd
            FROM patients p LEFT JOIN consults c ON c.patient_id = p.id
            WHERE p.name LIKE ? GROUP BY p.id
            ORDER BY COALESCE(MAX(c.created_at), p.created_at) DESC""", (f"%{q}%",)).fetchall()
    return [dict(r) for r in rows]


# ---------- consults and cost ----------
def estimate_cost(input_tokens, output_tokens):
    """Cost in USD from PRICE_INPUT_PER_1M and PRICE_OUTPUT_PER_1M in .env. None when the prices are not set."""
    price_in, price_out = os.getenv("PRICE_INPUT_PER_1M"), os.getenv("PRICE_OUTPUT_PER_1M")
    if price_in is None or price_out is None:
        return None
    return round(input_tokens / 1e6 * float(price_in) + output_tokens / 1e6 * float(price_out), 6)


def save_consult(encounter_id, patient_id, title, diagnoses, summary, usage):
    cost = estimate_cost(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    with _conn() as con:
        con.execute("INSERT OR IGNORE INTO consults (encounter_id, created_at) VALUES (?, ?)", (encounter_id, _now()))
        con.execute("""UPDATE consults SET patient_id=?, title=?, diagnoses=?, summary=?, model=?, input_tokens=?,
                       output_tokens=?, total_tokens=?, cost_usd=? WHERE encounter_id=?""",
                    (patient_id, title, diagnoses, summary, usage.get("model", ""), usage.get("input_tokens", 0),
                     usage.get("output_tokens", 0), usage.get("total_tokens", 0), cost, encounter_id))


def set_encounter_patient(encounter_id, patient_id, title="", created_at=None):
    """Attach an existing encounter (for example an old one) to a patient."""
    with _conn() as con:
        con.execute("INSERT OR IGNORE INTO consults (encounter_id, title, created_at) VALUES (?, ?, ?)",
                    (encounter_id, title, created_at or _now()))
        con.execute("UPDATE consults SET patient_id = ? WHERE encounter_id = ?", (patient_id, encounter_id))
        for kind in FIELDS:
            con.execute(f"UPDATE {kind} SET patient_id = ? WHERE encounter_id = ?", (patient_id, encounter_id))


def get_consult(encounter_id):
    with _conn() as con:
        row = con.execute("SELECT * FROM consults WHERE encounter_id = ?", (encounter_id,)).fetchone()
    return dict(row) if row else None


# ---------- tasks, recalls, referrals ----------
def add_item(kind, data, source="manual"):
    _kind(kind)
    cols, now = FIELDS[kind], _now()
    with _conn() as con:
        cur = con.execute(
            f"INSERT INTO {kind} (encounter_id, patient_id, {', '.join(cols)}, source, evidence, created_at, updated_at) "
            f"VALUES (?, ?, {', '.join('?' for _ in cols)}, ?, ?, ?, ?)",
            [data.get("encounter_id"), data.get("patient_id"), *(str(data.get(c) or "").strip() for c in cols),
             source, str(data.get("evidence") or ""), now, now])
        row = con.execute(f"SELECT * FROM {kind} WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def list_items(kind, encounter_id=None, patient_id=None):
    _kind(kind)
    where, args = [], []
    if encounter_id is not None:
        where.append("encounter_id = ?")
        args.append(encounter_id)
    if patient_id is not None:
        where.append("patient_id = ?")
        args.append(patient_id)
    sql = f"SELECT * FROM {kind}" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY (status != 'open'), id"
    with _conn() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def update_item(kind, item_id, changes):
    _kind(kind)
    allowed = {k: str(v).strip() for k, v in changes.items() if k in (*FIELDS[kind], "status")}
    if allowed.get("status", "open") not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with _conn() as con:
        if allowed:
            sets = ", ".join(f"{k} = ?" for k in allowed)          # column names come from the whitelist above
            con.execute(f"UPDATE {kind} SET {sets}, updated_at = ? WHERE id = ?", [*allowed.values(), _now(), item_id])
        row = con.execute(f"SELECT * FROM {kind} WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def delete_item(kind, item_id):
    _kind(kind)
    with _conn() as con:
        return con.execute(f"DELETE FROM {kind} WHERE id = ?", (item_id,)).rowcount > 0


def encounter_care(encounter_id):
    return {kind: list_items(kind, encounter_id=encounter_id) for kind in FIELDS}


# ---------- patient history ----------
def patient_history(patient_id):
    patient = get_patient(patient_id)
    if not patient:
        return None
    with _conn() as con:
        consults = [dict(r) for r in con.execute(
            "SELECT * FROM consults WHERE patient_id = ? ORDER BY created_at DESC", (patient_id,))]
    care = {kind: list_items(kind, patient_id=patient_id) for kind in FIELDS}
    for c in consults:
        c["open_items"] = sum(1 for items in care.values() for i in items
                              if i["encounter_id"] == c["encounter_id"] and i["status"] == "open")
    costs = [c["cost_usd"] for c in consults if c["cost_usd"] is not None]
    return {"patient": patient, "consults": consults, "care": care,
            "total_tokens": sum(c["total_tokens"] or 0 for c in consults),
            "total_cost_usd": round(sum(costs), 6) if costs else None}
