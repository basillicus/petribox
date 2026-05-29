"""
Petribox Database - SQLite storage for dish (VM) tracking
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Dish:
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


class DishDB:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".petribox" / "dishes.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dishes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    ram INTEGER NOT NULL DEFAULT 4096,
                    cpus INTEGER NOT NULL DEFAULT 2,
                    disk INTEGER NOT NULL DEFAULT 20,
                    user TEXT NOT NULL DEFAULT 'petri',
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
                    dish_id INTEGER NOT NULL,
                    host_path TEXT NOT NULL,
                    vm_path TEXT NOT NULL,
                    mount_type TEXT NOT NULL DEFAULT '9p',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (dish_id) REFERENCES dishes(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dish_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    installed INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (dish_id) REFERENCES dishes(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS port_forwards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dish_id INTEGER NOT NULL,
                    vm_port INTEGER NOT NULL,
                    local_port INTEGER NOT NULL,
                    pid INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (dish_id) REFERENCES dishes(id)
                )
            """)

    def create_dish(self, dish: Dish) -> Dish:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO dishes (
                    name, ram, cpus, disk, user, ssh_key, network, image,
                    status, created_at, updated_at, dotfiles_source,
                    config_file, preset, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dish.name,
                    dish.ram,
                    dish.cpus,
                    dish.disk,
                    dish.user,
                    dish.ssh_key,
                    dish.network,
                    dish.image,
                    dish.status,
                    dish.created_at,
                    dish.updated_at,
                    dish.dotfiles_source,
                    dish.config_file,
                    dish.preset,
                    dish.notes,
                ),
            )
            dish.id = cursor.lastrowid
            return dish

    def get_dish(self, name: str) -> Optional[Dish]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM dishes WHERE name = ? AND status != 'destroyed'", (name,)
            ).fetchone()
            if row:
                return self._row_to_dish(row)
            return None

    def get_dish_any(self, name: str) -> Optional[Dish]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM dishes WHERE name = ?", (name,)
            ).fetchone()
            if row:
                return self._row_to_dish(row)
            return None

    def get_dish_by_id(self, dish_id: int) -> Optional[Dish]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM dishes WHERE id = ?", (dish_id,)
            ).fetchone()
            if row:
                return self._row_to_dish(row)
            return None

    def list_dishes(
        self, status: Optional[str] = None, include_destroyed: bool = False
    ) -> list[Dish]:
        with self.connect() as conn:
            if include_destroyed:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM dishes WHERE status = ?", (status,)
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM dishes").fetchall()
            else:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM dishes WHERE status = ? AND status != 'destroyed'",
                        (status,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM dishes WHERE status != 'destroyed'"
                    ).fetchall()
            return [self._row_to_dish(row) for row in rows]

    def update_status(self, name: str, status: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE dishes 
                SET status = ?, updated_at = ?
                WHERE name = ?
                """,
                (status, datetime.now().isoformat(), name),
            )
            return cursor.rowcount > 0

    def delete_dish(self, name: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE dishes
                SET status = 'destroyed', updated_at = ?
                WHERE name = ?
                """,
                (datetime.now().isoformat(), name),
            )
            return cursor.rowcount > 0

    def remove_dish(self, name: str) -> bool:
        with self.connect() as conn:
            conn.execute("DELETE FROM mounts WHERE dish_id = (SELECT id FROM dishes WHERE name = ?)", (name,))
            conn.execute("DELETE FROM packages WHERE dish_id = (SELECT id FROM dishes WHERE name = ?)", (name,))
            cursor = conn.execute("DELETE FROM dishes WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def add_mount(
        self, dish_id: int, host_path: str, vm_path: str, mount_type: str = "9p"
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO mounts (dish_id, host_path, vm_path, mount_type, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (dish_id, host_path, vm_path, mount_type, datetime.now().isoformat()),
            )
            return cursor.lastrowid

    def get_mounts(self, dish_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mounts WHERE dish_id = ?", (dish_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def add_package(self, dish_id: int, package_name: str) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO packages (dish_id, name, installed)
                VALUES (?, ?, 0)
                """,
                (dish_id, package_name),
            )
            return cursor.lastrowid

    def get_packages(self, dish_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM packages WHERE dish_id = ?", (dish_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_package_installed(self, dish_id: int, package_name: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE packages 
                SET installed = 1
                WHERE dish_id = ? AND name = ?
                """,
                (dish_id, package_name),
            )
            return cursor.rowcount > 0

    def _row_to_dish(self, row: sqlite3.Row) -> Dish:
        return Dish(
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
