import sqlite3
import os
import re
from werkzeug.security import generate_password_hash

# ================= ENVIRONMENT & CONFIGURATION =================
DATABASE_BACKEND = os.environ.get("DATABASE_BACKEND", "").lower().strip()
TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()

# Production environment detection
IS_PRODUCTION = (
    os.environ.get("FLASK_ENV") == "production"
    or os.environ.get("RENDER") in ("true", "1", True)
    or os.environ.get("RENDER_SERVICE_ID") is not None
)

# Local SQLite fallback path (strictly for local dev & testing)
is_serverless = os.environ.get("VERCEL") == "1" or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
if is_serverless:
    DB_PATH = os.environ.get("SABRO_DB_PATH", "/tmp/sabro_isp.db")
else:
    DB_PATH = os.environ.get(
        "SABRO_DB_PATH",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "sabro_isp.db")
    )


def is_turso():
    """Returns True if the active database backend is configured for Turso Cloud."""
    if DATABASE_BACKEND == "turso":
        return True
    if TURSO_DATABASE_URL and DATABASE_BACKEND != "sqlite":
        return True
    return False


def validate_production_config():
    """
    Enforces that production environments MUST use a persistent Turso Cloud database.
    Silent fallback to ephemeral local SQLite in production is strictly forbidden.
    """
    if DATABASE_BACKEND == "turso" or (IS_PRODUCTION and DATABASE_BACKEND != "sqlite"):
        if not TURSO_DATABASE_URL or not TURSO_AUTH_TOKEN:
            raise RuntimeError(
                "CRITICAL CONFIGURATION ERROR: Production requires persistent Turso Cloud database.\n"
                "DATABASE_BACKEND is set to 'turso' (or running in production), but TURSO_DATABASE_URL "
                "or TURSO_AUTH_TOKEN is missing.\n"
                "To prevent catastrophic data loss on container restarts, please configure:\n"
                "  - TURSO_DATABASE_URL (e.g. libsql://your-db.turso.io)\n"
                "  - TURSO_AUTH_TOKEN\n"
                "in your Render Dashboard Environment Variables."
            )


def get_storage_engine_name():
    """Returns human-readable name of the active storage engine for UI diagnostics."""
    if is_turso():
        masked_url = re.sub(r"://([^@]+)@", "://***@", TURSO_DATABASE_URL) if "@" in TURSO_DATABASE_URL else TURSO_DATABASE_URL
        return f"Turso Cloud SQLite ({masked_url})"
    if os.environ.get("SABRO_DB_PATH"):
        return f"Persistent Mounted Disk ({DB_PATH})"
    return "Local SQLite Storage (sabro_isp.db)"


# ================= TURSO / LIBSQL ADAPTER LAYER =================
class LibsqlRow:
    """
    Provides full sqlite3.Row compatibility for libSQL result rows:
      - Positional integer indexing: row[0], row[1]
      - Named dictionary access: row['username'], row['price']
      - Case-insensitive fallback lookup
      - Dictionary methods: keys(), values(), items(), get()
      - 'col' in row membership testing (checks column names, not values)
      - Iterable over values: list(row), tuple(row)
      - len(row)
    """
    def __init__(self, cols, values):
        self._col_list = [str(c) for c in cols]
        self._col_map = {c: i for i, c in enumerate(self._col_list)}
        self._lower_map = {c.lower(): i for i, c in enumerate(self._col_list)}
        self._values = list(values)

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._values[item]
        if item in self._col_map:
            return self._values[self._col_map[item]]
        lower = str(item).lower()
        if lower in self._lower_map:
            return self._values[self._lower_map[lower]]
        raise KeyError(item)

    def keys(self):
        return list(self._col_list)

    def values(self):
        return list(self._values)

    def items(self):
        return [(c, self._values[i]) for c, i in self._col_map.items()]

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def __contains__(self, key):
        return key in self._col_map or str(key).lower() in self._lower_map

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __repr__(self):
        return f"LibsqlRow({dict(self.items())})"


class LibsqlCursor:
    """
    Provides standard DB-API 2.0 cursor wrapping libSQL ClientSync / TransactionSync.
    Supports execute, executemany, fetchone, fetchall, fetchmany, lastrowid, rowcount.
    """
    def __init__(self, conn):
        self.conn = conn
        self.lastrowid = None
        self.rowcount = 0
        self._rows = []
        self._idx = 0
        self.closed = False

    def execute(self, sql, params=None):
        if self.closed:
            raise RuntimeError("Cannot execute query on closed cursor.")
        p = list(params) if params is not None else []
        executor = self.conn._txn if (self.conn._txn is not None and not self.conn._txn.closed) else self.conn.client
        res = executor.execute(sql, p)
        self.lastrowid = getattr(res, "last_insert_rowid", None)
        self.rowcount = getattr(res, "rows_affected", 0)
        self._rows = [LibsqlRow(res.columns, r) for r in res.rows]
        self._idx = 0
        return self

    def executemany(self, sql, seq_of_params):
        if self.closed:
            raise RuntimeError("Cannot execute query on closed cursor.")
        total_affected = 0
        for p in seq_of_params:
            self.execute(sql, p)
            total_affected += (self.rowcount or 0)
        self.rowcount = total_affected
        return self

    def fetchone(self):
        if self._idx < len(self._rows):
            r = self._rows[self._idx]
            self._idx += 1
            return r
        return None

    def fetchall(self):
        r = self._rows[self._idx:]
        self._idx = len(self._rows)
        return r

    def fetchmany(self, size=None):
        if size is None:
            size = 1
        end = min(self._idx + size, len(self._rows))
        res = self._rows[self._idx:end]
        self._idx = end
        return res

    def __iter__(self):
        return self

    def __next__(self):
        r = self.fetchone()
        if r is None:
            raise StopIteration
        return r

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class LibsqlConn:
    """
    Provides standard DB-API 2.0 connection wrapper for Turso libSQL Cloud.
    Implements true atomic transaction management (begin, commit, rollback),
    context manager support (`with conn:`), and foreign key enforcement.
    """
    def __init__(self, url, auth_token=None):
        import libsql_client
        self.client = libsql_client.create_client_sync(url, auth_token=auth_token)
        self._txn = None
        self.row_factory = LibsqlRow  # compatibility marker
        # Enable foreign key enforcement
        try:
            self.client.execute("PRAGMA foreign_keys = ON;")
        except Exception as e:
            print(f"[TURSO WARNING] Failed to enable PRAGMA foreign_keys: {e}")

    def begin(self):
        """Starts an atomic transaction if one is not already active."""
        if self._txn is None or self._txn.closed:
            self._txn = self.client.transaction()
        return self._txn

    def cursor(self):
        return LibsqlCursor(self)

    def execute(self, sql, params=None):
        cur = self.cursor()
        return cur.execute(sql, params)

    def executemany(self, sql, seq_of_params):
        cur = self.cursor()
        return cur.executemany(sql, seq_of_params)

    def commit(self):
        """Commits the active transaction."""
        if self._txn is not None and not self._txn.closed:
            self._txn.commit()
            self._txn.close()
            self._txn = None

    def rollback(self):
        """Rolls back the active transaction."""
        if self._txn is not None and not self._txn.closed:
            self._txn.rollback()
            self._txn.close()
            self._txn = None

    def close(self):
        """Closes any active transaction and the underlying libSQL client."""
        if self._txn is not None and not self._txn.closed:
            try:
                self._txn.close()
            except Exception:
                pass
            self._txn = None
        try:
            self.client.close()
        except Exception:
            pass

    def __enter__(self):
        self.begin()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


# ================= CENTRAL DATABASE ACCESS =================
def get_db():
    """
    Central database connection provider.
    Connects to Turso Cloud when configured or required by production.
    Falls back to local SQLite only when explicitly in local development/testing.
    """
    validate_production_config()

    if is_turso():
        try:
            return LibsqlConn(TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
        except Exception as e:
            if IS_PRODUCTION or DATABASE_BACKEND == "turso":
                raise RuntimeError(
                    f"CRITICAL: Failed to connect to Turso Cloud database ({TURSO_DATABASE_URL}): {e}.\n"
                    "Ephemeral SQLite fallback is strictly blocked in production to prevent data loss."
                ) from e
            print(f"[TURSO WARNING] Local development fallback to SQLite due to connection error: {e}")

    # Local SQLite Connection (Development / Testing Only)
    conn = sqlite3.connect(DB_PATH, timeout=25.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        try:
            conn.execute("PRAGMA journal_mode=DELETE;")
        except Exception:
            pass
    try:
        conn.execute("PRAGMA busy_timeout=25000;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass
    return conn


def safe_backup_to_file(dest_path):
    """
    Safely creates a consistent, atomic binary SQLite database snapshot at dest_path.
    Works seamlessly with both Turso Cloud and local SQLite.
    """
    if is_turso():
        source_conn = get_db()
        dest_conn = sqlite3.connect(dest_path)
        tables = [
            r[0] for r in source_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for table in tables:
            row = source_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
            ).fetchone()
            if row and row[0]:
                dest_conn.execute(row[0])
                rows = source_conn.execute(f"SELECT * FROM {table}").fetchall()
                if rows:
                    cols = rows[0].keys()
                    placeholders = ", ".join(["?"] * len(cols))
                    insert_sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
                    dest_conn.executemany(insert_sql, [[r[c] for c in cols] for r in rows])
        dest_conn.commit()
        dest_conn.close()
        source_conn.close()
        return dest_path
    else:
        source_conn = get_db()
        dest_conn = sqlite3.connect(dest_path)
        with dest_conn:
            source_conn.backup(dest_conn)
        dest_conn.close()
        source_conn.close()
        return dest_path


# ================= SCHEMA INITIALIZATION & MIGRATIONS =================
def init_db(force_reset=False):
    """
    Initializes the database schema safely.
    Preserves all existing tables, columns, indexes, and records.
    Never runs destructive operations unless force_reset=True is explicitly passed in non-production.
    """
    validate_production_config()

    if force_reset:
        if IS_PRODUCTION:
            raise RuntimeError("DESTRUCTIVE ACTION BLOCKED: Cannot force reset database in production!")
        if not is_turso() and os.path.exists(DB_PATH):
            try:
                os.remove(DB_PATH)
            except Exception:
                pass

    conn = get_db()
    cursor = conn.cursor()

    # 1. System Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # 2. Users & Staff Logins
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL, -- Admin, Recovery Boy, Complaint Boy, Staff
        phone TEXT NOT NULL DEFAULT '',
        assigned_area TEXT DEFAULT '',
        status TEXT DEFAULT 'Active', -- Active, Inactive
        total_collected REAL DEFAULT 0.0,
        pfp_image TEXT DEFAULT '',
        technician_xp INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    # Dynamic column migrations for users table
    user_cols = [c[1] for c in cursor.execute("PRAGMA table_info(users)").fetchall()]
    if "pfp_image" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN pfp_image TEXT DEFAULT '';")
    if "technician_xp" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN technician_xp INTEGER DEFAULT 0;")

    # 3. Tariffs / Packages
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tariffs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        speed_mb INTEGER NOT NULL,
        price REAL NOT NULL,
        description TEXT
    )
    """)

    # 4. FTTH Subscribers / Customers
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        pppoe_username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        phone TEXT,
        address TEXT,
        area TEXT,
        tariff_id INTEGER,
        status TEXT DEFAULT 'Active', -- Active, Expired, Suspended
        expiry_date TEXT,
        onu_serial TEXT DEFAULT '',
        db_box TEXT DEFAULT '',
        fiber_core TEXT DEFAULT '',
        cnic TEXT DEFAULT '',
        installation_date TEXT,
        created_at TEXT,
        FOREIGN KEY (tariff_id) REFERENCES tariffs (id)
    )
    """)

    # Dynamic column migrations for customers table
    cust_cols = [c[1] for c in cursor.execute("PRAGMA table_info(customers)").fetchall()]
    ftth_columns = [
        ("onu_serial", "TEXT DEFAULT ''"),
        ("db_box", "TEXT DEFAULT ''"),
        ("fiber_core", "TEXT DEFAULT ''"),
        ("cnic", "TEXT DEFAULT ''"),
        ("installation_date", "TEXT")
    ]
    for col_name, col_def in ftth_columns:
        if col_name not in cust_cols:
            cursor.execute(f"ALTER TABLE customers ADD COLUMN {col_name} {col_def};")

    # 5. Invoices & Billing
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number TEXT UNIQUE NOT NULL,
        customer_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        month_period TEXT NOT NULL,
        status TEXT DEFAULT 'Unpaid', -- Paid, Unpaid, Overdue
        due_date TEXT,
        paid_date TEXT,
        payment_method TEXT, -- Cash, JazzCash, EasyPaisa, Bank Transfer
        collected_by_staff_id INTEGER,
        created_at TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers (id),
        FOREIGN KEY (collected_by_staff_id) REFERENCES users (id)
    )
    """)

    # 6. Expenses Tracker
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        date TEXT NOT NULL,
        paid_by TEXT,
        notes TEXT,
        created_at TEXT
    )
    """)

    # 7. Customer Deposits & Advances
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        deposit_type TEXT NOT NULL,
        amount REAL NOT NULL,
        status TEXT DEFAULT 'Held', -- Held, Refunded, Adjusted
        date TEXT NOT NULL,
        notes TEXT,
        created_at TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers (id)
    )
    """)

    # 8. Capital Investments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS investments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        investor_name TEXT NOT NULL,
        title TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        date TEXT NOT NULL,
        notes TEXT,
        created_at TEXT
    )
    """)

    # 9. Upstream Dealer Sync Configuration & Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dealer_sync_config (
        id INTEGER PRIMARY KEY,
        portal_name TEXT DEFAULT 'Connect Communications Dealer Portal',
        portal_url TEXT DEFAULT '',
        dealer_username TEXT DEFAULT '',
        dealer_password TEXT DEFAULT '',
        auto_sync_interval TEXT DEFAULT 'Manual',
        last_sync_time TEXT,
        last_sync_status TEXT DEFAULT 'Not Configured'
    )
    """)

    cursor.execute("""
    INSERT OR IGNORE INTO dealer_sync_config (id, portal_url, dealer_username, last_sync_status)
    VALUES (1, '', '', 'Not Configured');
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dealer_sync_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sync_time TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL,
        total_scanned INTEGER DEFAULT 0,
        updated_count INTEGER DEFAULT 0,
        created_count INTEGER DEFAULT 0,
        details TEXT
    )
    """)

    # 10. Complaint & Support Tickets
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_number TEXT UNIQUE NOT NULL,
        customer_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        details TEXT,
        priority TEXT DEFAULT 'Medium', -- Low, Medium, High, Critical
        status TEXT DEFAULT 'Open', -- Open, In Progress, Resolved
        assigned_user_id INTEGER,
        resolution_notes TEXT,
        created_at TEXT,
        resolved_at TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers (id),
        FOREIGN KEY (assigned_user_id) REFERENCES users (id)
    )
    """)

    conn.commit()

    # 11. Performance Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id, id DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_staff ON invoices(collected_by_staff_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_customer ON tickets(customer_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets(assigned_user_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deposits_customer ON deposits(customer_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_area ON customers(area);")
    conn.commit()

    # 12. Default System Settings
    default_settings = [
        ("isp_name", "Sabro Networks"),
        ("tagline", "FTTH High-Speed Fiber Internet"),
        ("currency", "PKR"),
        ("phone", ""),
        ("business_whatsapp", ""),
        ("email", ""),
        ("address", ""),
        ("jazzcash_no", ""),
        ("easypaisa_no", ""),
        ("bank_info", ""),
        ("agency_name", "Vshatkay Solutions"),
        ("agency_tagline", "Software Engineering & Telecom Solutions Agency"),
        ("agency_url", "https://vshatkaysolutions.com"),
    ]
    for k, v in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);", (k, v))

    # 13. Ensure Single Main Admin exists if database has 0 users
    user_count = cursor.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
    if user_count == 0:
        admin_username = os.environ.get("ADMIN_USERNAME", "ahmedbaloch").strip() or "ahmedbaloch"
        admin_password = os.environ.get("ADMIN_PASSWORD", "adminadmin1").strip() or "adminadmin1"
        hashed_password = generate_password_hash(admin_password)
        cursor.execute("""
            INSERT INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES (?, ?, ?, 'Admin', '', 'All Areas', 'Active', 0.0, date('now'))
        """, ("Ahmed Baloch", admin_username, hashed_password))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db(force_reset=False)
    print(f"Sabro Networks database initialized successfully via engine: {get_storage_engine_name()}")
