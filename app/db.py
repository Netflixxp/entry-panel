from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.security import hash_password


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "panel.sqlite3"


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS entry_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                ssh_port INTEGER NOT NULL DEFAULT 22,
                ssh_user TEXT NOT NULL DEFAULT 'root',
                ssh_key_path TEXT,
                ssh_password TEXT,
                status TEXT NOT NULL DEFAULT 'unknown',
                nginx_status TEXT NOT NULL DEFAULT 'unknown',
                last_sync_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS site_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                domain TEXT NOT NULL DEFAULT 'zhongzhuan.example.com',
                site_name TEXT NOT NULL DEFAULT 'Edge Resource Hub',
                tagline TEXT NOT NULL DEFAULT 'Fast, verified resource delivery for developer assets.',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sni_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER,
                sni_domain TEXT NOT NULL UNIQUE,
                target_host TEXT NOT NULL,
                target_port INTEGER NOT NULL DEFAULT 443,
                enabled INTEGER NOT NULL DEFAULT 1,
                remark TEXT,
                traffic_bytes INTEGER NOT NULL DEFAULT 0,
                traffic_offset_bytes INTEGER NOT NULL DEFAULT 0,
                last_check_ok INTEGER,
                last_check_ip TEXT,
                last_check_latency_ms INTEGER,
                last_check_error TEXT,
                last_check_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (node_id) REFERENCES entry_nodes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS config_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER NOT NULL,
                version_label TEXT NOT NULL,
                config_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (node_id) REFERENCES entry_nodes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS apply_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER NOT NULL,
                config_version_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                log TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                FOREIGN KEY (node_id) REFERENCES entry_nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (config_version_id) REFERENCES config_versions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _ensure_column(conn, "sni_rules", "last_check_ok", "INTEGER")
        _ensure_column(conn, "sni_rules", "node_id", "INTEGER")
        _ensure_column(conn, "sni_rules", "traffic_bytes", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "sni_rules", "traffic_offset_bytes", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "sni_rules", "last_check_ip", "TEXT")
        _ensure_column(conn, "sni_rules", "last_check_latency_ms", "INTEGER")
        _ensure_column(conn, "sni_rules", "last_check_error", "TEXT")
        _ensure_column(conn, "sni_rules", "last_check_at", "TEXT")
        admin_count = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
        if admin_count == 0:
            conn.execute(
                "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                ("admin", hash_password("admin123")),
            )
        conn.execute(
            """
            INSERT OR IGNORE INTO site_settings (id, domain, site_name, tagline)
            VALUES (1, 'zhongzhuan.example.com', 'Edge Resource Hub',
                    'Fast, verified resource delivery for developer assets.')
            """
        )
        first_node = conn.execute("SELECT id FROM entry_nodes ORDER BY id LIMIT 1").fetchone()
        if first_node:
            conn.execute("UPDATE sni_rules SET node_id = ? WHERE node_id IS NULL", (first_node["id"],))


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(query, params).fetchone()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return list(conn.execute(query, params).fetchall())


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with get_conn() as conn:
        cur = conn.execute(query, params)
        return int(cur.lastrowid)


def audit(action: str, detail: str) -> None:
    execute("INSERT INTO audit_logs (action, detail) VALUES (?, ?)", (action, detail))


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
