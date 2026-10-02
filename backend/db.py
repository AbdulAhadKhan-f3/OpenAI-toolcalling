"""SQLite storage. Three tables: encounters (1) -> diagnoses (many), medications (many)."""
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "clinical.db"


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS encounters(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            title TEXT, transcript TEXT, complete INTEGER, result_json TEXT);
        CREATE TABLE IF NOT EXISTS diagnoses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            encounter_id INTEGER REFERENCES encounters(id) ON DELETE CASCADE,
            name TEXT, status TEXT, evidence TEXT);
        CREATE TABLE IF NOT EXISTS medications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            encounter_id INTEGER REFERENCES encounters(id) ON DELETE CASCADE,
            name TEXT, dose TEXT, route TEXT, frequency TEXT, duration TEXT,
            status TEXT, evidence TEXT);
        """)


def save(title, transcript, result) -> int:
    """Store the full result as JSON (for the detail page) AND as rows (for search)."""
    fs = result["final_state"]
    with conn() as c:
        eid = c.execute(
            "INSERT INTO encounters(title, transcript, complete, result_json) VALUES(?,?,?,?)",
            (title, transcript, int(result["complete"]), json.dumps(result))).lastrowid
        for d in fs["confirmed_diagnoses"] + fs["not_confirmed_diagnoses"]:
            c.execute("INSERT INTO diagnoses(encounter_id,name,status,evidence) VALUES(?,?,?,?)",
                      (eid, d["diagnosis"], d["status"], d["evidence"]))
        for key, status in (("active_medications", "active"), ("stopped_medications", "stopped"),
                            ("considered_only_medications", "considered")):
            for m in fs[key]:
                c.execute("INSERT INTO medications(encounter_id,name,dose,route,frequency,duration,status,evidence)"
                          " VALUES(?,?,?,?,?,?,?,?)",
                          (eid, m["name"], m["dose"], m["route"], m["frequency"], m["duration"],
                           status, m["evidence"]))
    return eid


def list_encounters(q: str = ""):
    """Search by diagnosis name, medication name, or transcript text."""
    with conn() as c:
        rows = c.execute("""
            SELECT e.id, e.created_at, e.title, e.complete,
              (SELECT group_concat(name, ', ') FROM diagnoses
                 WHERE encounter_id = e.id AND status = 'confirmed') AS diagnoses,
              (SELECT group_concat(name, ', ') FROM medications
                 WHERE encounter_id = e.id AND status = 'active') AS medications
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