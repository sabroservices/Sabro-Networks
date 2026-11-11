import sqlite3
import os
from werkzeug.security import generate_password_hash

# Detect serverless execution environment (e.g., Vercel, AWS Lambda)
is_serverless = os.environ.get("VERCEL") == "1" or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
if is_serverless:
    DB_PATH = os.environ.get("SABRO_DB_PATH", "/tmp/sabro_isp.db")
else:
    DB_PATH = os.environ.get("SABRO_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "sabro_isp.db"))

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=25.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode if supported, fallback to DELETE mode on restricted serverless filesystems
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
    """Safely creates an atomic, consistent database backup using SQLite backup API."""
    source_conn = get_db()
    dest_conn = sqlite3.connect(dest_path)
    with dest_conn:
        source_conn.backup(dest_conn)
    dest_conn.close()
    source_conn.close()
    return dest_path

def init_db(force_reset=False):
    if force_reset and os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass

    conn = get_db()
    cursor = conn.cursor()

    # Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Users & Staff Logins (Main Admin + Optional Staff Created Later)
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

    # Dynamic column migration for users
    user_cols = [c[1] for c in cursor.execute("PRAGMA table_info(users)").fetchall()]
    if "pfp_image" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN pfp_image TEXT DEFAULT '';")
    if "technician_xp" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN technician_xp INTEGER DEFAULT 0;")

    # Tariffs / Packages
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tariffs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        speed_mb INTEGER NOT NULL,
        price REAL NOT NULL,
        description TEXT
    )
    """)

    # Customers (FTTH Subscriber details: ONU Serial, FDB Box, Fiber Core, CNIC)
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

    # Invoices / Billing (Paid & Unpaid)
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

    # Expenses (Daily Kharcha Tracker)
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

    # Deposits & Advances (ONU Security Deposit, Installation Fee, Advance)
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

    # Capital Investments (Invested amounts tracked separately)
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

    # Upstream Dealer Sync Configuration (clean schema, no sample credentials)
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
    VALUES (1, '', '', 'Not Configured')
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

    # Support / Complaint Tickets
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

    # Performance Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id, id DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invoices_staff ON invoices(collected_by_staff_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_customer ON tickets(customer_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets(assigned_user_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deposits_customer ON deposits(customer_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_area ON customers(area);")
    conn.commit()

    # Dynamic Column Migration for existing databases
    cursor.execute("PRAGMA table_info(customers)")
    existing_cols = [r[1] for r in cursor.fetchall()]
    ftth_columns = [
        ("onu_serial", "TEXT DEFAULT ''"),
        ("db_box", "TEXT DEFAULT ''"),
        ("fiber_core", "TEXT DEFAULT ''"),
        ("cnic", "TEXT DEFAULT ''"),
        ("installation_date", "TEXT")
    ]
    for col_name, col_def in ftth_columns:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE customers ADD COLUMN {col_name} {col_def}")
    conn.commit()

    # Clean default company metadata (no demo numbers, no fake payment accounts)
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
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Single Main Admin login only (zero demo staff, zero sample operational data)
    user_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
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
    init_db(force_reset=True)
    print("Clean Sabro Networks database initialized with single Main Admin (ahmedbaloch) and zero sample data.")
