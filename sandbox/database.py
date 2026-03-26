"""
Sandbox Database - SQLite storage for VM tracking
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Sandbox:
    """Represents a sandbox VM"""

    id: Optional[int]
    name: str
    ram: int
    cpus: int
    disk: int
    user: str
    ssh_key: str
    network: str
    image: str
    status: str  # running, stopped, destroyed
    created_at: str
    updated_at: str
    dotfiles_source: Optional[str]
    config_file: Optional[str]
    preset: Optional[str]
    notes: Optional[str]


class SandboxDB:
    """SQLite database for tracking sandboxes"""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".sandbox" / "sandboxes.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def connect(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema"""
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sandboxes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    ram INTEGER NOT NULL DEFAULT 4096,
                    cpus INTEGER NOT NULL DEFAULT 2,
                    disk INTEGER NOT NULL DEFAULT 20,
                    user TEXT NOT NULL DEFAULT 'sandbox',
                    ssh_key TEXT NOT NULL,
                    network TEXT NOT NULL DEFAULT 'default',
                    image TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'stopped',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    dotfiles_source TEXT,
                    config_file TEXT,
                    preset TEXT,
                    notes TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS mounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sandbox_id INTEGER NOT NULL,
                    host_path TEXT NOT NULL,
                    vm_path TEXT NOT NULL,
                    mount_type TEXT NOT NULL DEFAULT '9p',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sandbox_id) REFERENCES sandboxes(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sandbox_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    installed INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (sandbox_id) REFERENCES sandboxes(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS port_forwards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sandbox_id INTEGER NOT NULL,
                    vm_port INTEGER NOT NULL,
                    local_port INTEGER NOT NULL,
                    pid INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (sandbox_id) REFERENCES sandboxes(id)
                )
            """)

    def create_sandbox(self, sandbox: Sandbox) -> Sandbox:
        """Create a new sandbox record"""
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sandboxes (
                    name, ram, cpus, disk, user, ssh_key, network, image,
                    status, created_at, updated_at, dotfiles_source,
                    config_file, preset, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sandbox.name,
                    sandbox.ram,
                    sandbox.cpus,
                    sandbox.disk,
                    sandbox.user,
                    sandbox.ssh_key,
                    sandbox.network,
                    sandbox.image,
                    sandbox.status,
                    sandbox.created_at,
                    sandbox.updated_at,
                    sandbox.dotfiles_source,
                    sandbox.config_file,
                    sandbox.preset,
                    sandbox.notes,
                ),
            )
            sandbox.id = cursor.lastrowid
            return sandbox

    def get_sandbox(self, name: str) -> Optional[Sandbox]:
        """Get a sandbox by name"""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sandboxes WHERE name = ?", (name,)
            ).fetchone()
            if row:
                return self._row_to_sandbox(row)
            return None

    def get_sandbox_by_id(self, sandbox_id: int) -> Optional[Sandbox]:
        """Get a sandbox by ID"""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sandboxes WHERE id = ?", (sandbox_id,)
            ).fetchone()
            if row:
                return self._row_to_sandbox(row)
            return None

    def list_sandboxes(
        self, status: Optional[str] = None, include_destroyed: bool = False
    ) -> list[Sandbox]:
        """List sandboxes, optionally filtered by status"""
        with self.connect() as conn:
            if include_destroyed:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM sandboxes WHERE status = ?", (status,)
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM sandboxes").fetchall()
            else:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM sandboxes WHERE status = ? AND status != 'destroyed'",
                        (status,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM sandboxes WHERE status != 'destroyed'"
                    ).fetchall()
            return [self._row_to_sandbox(row) for row in rows]

    def update_status(self, name: str, status: str) -> bool:
        """Update sandbox status"""
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE sandboxes 
                SET status = ?, updated_at = ?
                WHERE name = ?
                """,
                (status, datetime.now().isoformat(), name),
            )
            return cursor.rowcount > 0

    def delete_sandbox(self, name: str) -> bool:
        """Mark a sandbox as destroyed (soft delete)"""
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE sandboxes
                SET status = 'destroyed', updated_at = ?
                WHERE name = ?
                """,
                (datetime.now().isoformat(), name),
            )
            return cursor.rowcount > 0

    def remove_sandbox(self, name: str) -> bool:
        """Permanently delete a sandbox from database (hard delete)"""
        with self.connect() as conn:
            # First delete associated mounts and packages
            conn.execute("DELETE FROM mounts WHERE sandbox_id = (SELECT id FROM sandboxes WHERE name = ?)", (name,))
            conn.execute("DELETE FROM packages WHERE sandbox_id = (SELECT id FROM sandboxes WHERE name = ?)", (name,))
            # Then delete the sandbox
            cursor = conn.execute("DELETE FROM sandboxes WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def add_mount(
        self, sandbox_id: int, host_path: str, vm_path: str, mount_type: str = "9p"
    ) -> int:
        """Add a mount record"""
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO mounts (sandbox_id, host_path, vm_path, mount_type, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sandbox_id, host_path, vm_path, mount_type, datetime.now().isoformat()),
            )
            return cursor.lastrowid

    def get_mounts(self, sandbox_id: int) -> list[dict]:
        """Get all mounts for a sandbox"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mounts WHERE sandbox_id = ?", (sandbox_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def add_package(self, sandbox_id: int, package_name: str) -> int:
        """Add a package record"""
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO packages (sandbox_id, name, installed)
                VALUES (?, ?, 0)
                """,
                (sandbox_id, package_name),
            )
            return cursor.lastrowid

    def get_packages(self, sandbox_id: int) -> list[dict]:
        """Get all packages for a sandbox"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM packages WHERE sandbox_id = ?", (sandbox_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_package_installed(self, sandbox_id: int, package_name: str) -> bool:
        """Mark a package as installed"""
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE packages 
                SET installed = 1
                WHERE sandbox_id = ? AND name = ?
                """,
                (sandbox_id, package_name),
            )
            return cursor.rowcount > 0

    def _row_to_sandbox(self, row: sqlite3.Row) -> Sandbox:
        """Convert a database row to a Sandbox object"""
        return Sandbox(
            id=row["id"],
            name=row["name"],
            ram=row["ram"],
            cpus=row["cpus"],
            disk=row["disk"],
            user=row["user"],
            ssh_key=row["ssh_key"],
            network=row["network"],
            image=row["image"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            dotfiles_source=row["dotfiles_source"],
            config_file=row["config_file"],
            preset=row["preset"],
            notes=row["notes"],
        )
