# --- dmme_lib/services/storage_service.py ---
import sqlite3
import logging

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
