# --- dmme_lib/services/storage_service.py ---
import sqlite3
import logging
import json
from datetime import datetime

log = logging.getLogger("dmme.storage")


class StorageService:
    """
    Manages all interactions with the application's SQLite database.
    """

    def __init__(self, db_path: str):
        """
        Initializes the service with the path to the SQLite database.
        Args:
            db_path (str): The full file path to the database.
        """
        if not db_path:
            raise ValueError("Database path cannot be empty.")
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """
        Establishes a connection to the SQLite database.
        Enables foreign key support and sets the row factory.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """
        Creates all necessary database tables if they do not already exist.
        This method is idempotent and safe to run on every application start.
        """
        log.info("Initializing database schema...")
        conn = self._get_connection()
        try:
            with conn:
                self._create_campaigns_table(conn)
                self._create_parties_table(conn)
                self._create_characters_table(conn)
                self._create_sessions_table(conn)
            log.info("Database schema checked and is up to date.")
        except sqlite3.Error as e:
            log.error("An error occurred during DB initialization: %s", e)
            raise
        finally:
            conn.close()

    # --- Schema Creation ---
    def _create_campaigns_table(self, conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    def _create_parties_table(self, conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    def _create_characters_table(self, conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                party_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                class TEXT,
                level INTEGER DEFAULT 1,
                description TEXT,
                stats TEXT, -- Stored as JSON
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE CASCADE
            );
            """
        )

    def _create_sessions_table(self, conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                session_number INTEGER NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                journal_recap TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE
            );
            """
        )

    # --- Campaign CRUD Methods ---
    def get_all_campaigns(self):
        with self._get_connection() as conn:
            return conn.execute("SELECT * FROM campaigns ORDER BY updated_at DESC;").fetchall()

    def get_campaign(self, campaign_id: int):
        with self._get_connection() as conn:
            return conn.execute(
                "SELECT * FROM campaigns WHERE id = ?;", (campaign_id,)
            ).fetchone()

    def create_campaign(self, name: str, description: str = ""):
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO campaigns (name, description) VALUES (?, ?);", (name, description)
            )
            return cursor.lastrowid

    def update_campaign(self, campaign_id: int, name: str, description: str):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE campaigns SET name = ?, description = ?, updated_at = ? WHERE id = ?;",
                (name, description, now, campaign_id),
            )
            return cursor.rowcount > 0

    def delete_campaign(self, campaign_id: int):
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM campaigns WHERE id = ?;", (campaign_id,))
            return cursor.rowcount > 0

    # --- Party CRUD Methods ---
    def get_all_parties(self):
        with self._get_connection() as conn:
            return conn.execute("SELECT * FROM parties ORDER BY updated_at DESC;").fetchall()

    def get_party(self, party_id: int):
        with self._get_connection() as conn:
            return conn.execute("SELECT * FROM parties WHERE id = ?;", (party_id,)).fetchone()

    def create_party(self, name: str):
        with self._get_connection() as conn:
            try:
                cursor = conn.execute("INSERT INTO parties (name) VALUES (?);", (name,))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                log.warning("Attempted to create a party with a non-unique name: %s", name)
                return None

    def update_party(self, party_id: int, name: str):
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            try:
                cursor = conn.execute(
                    "UPDATE parties SET name = ?, updated_at = ? WHERE id = ?;",
                    (name, now, party_id),
                )
                return cursor.rowcount > 0
            except sqlite3.IntegrityError:
                log.warning("Attempted to update a party to a non-unique name: %s", name)
                return False

    def delete_party(self, party_id: int):
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM parties WHERE id = ?;", (party_id,))
            return cursor.rowcount > 0

    # --- Character CRUD Methods ---
    def get_characters_for_party(self, party_id: int):
        with self._get_connection() as conn:
            return conn.execute(
                "SELECT * FROM characters WHERE party_id = ? ORDER BY created_at ASC;",
                (party_id,),
            ).fetchall()

    def get_character(self, character_id: int):
        with self._get_connection() as conn:
            return conn.execute(
                "SELECT * FROM characters WHERE id = ?;", (character_id,)
            ).fetchone()

    def create_character(
        self, party_id: int, name: str, char_class: str, level: int, desc: str, stats: dict
    ):
        stats_json = json.dumps(stats)
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO characters
                    (party_id, name, class, level, description, stats)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (party_id, name, char_class, level, desc, stats_json),
            )
            return cursor.lastrowid

    def delete_character(self, character_id: int):
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM characters WHERE id = ?;", (character_id,))
            return cursor.rowcount > 0

    # --- Session & Journaling Methods ---
    def create_session(self, campaign_id: int) -> int:
        """Creates a new session record for a campaign and returns the new session ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT MAX(session_number) FROM sessions WHERE campaign_id = ?;",
                (campaign_id,),
            )
            max_session = cursor.fetchone()[0]
            new_session_number = (max_session or 0) + 1

            cursor.execute(
                "INSERT INTO sessions (campaign_id, session_number) VALUES (?, ?);",
                (campaign_id, new_session_number),
            )
            conn.commit()
            return cursor.lastrowid

    def save_journal_recap(self, session_id: int, recap_text: str):
        """Saves the journal recap and sets the end time for a given session."""
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE sessions SET journal_recap = ?, end_time = ? WHERE id = ?;",
                (recap_text, now, session_id),
            )
            return cursor.rowcount > 0
