import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.environ.get("SABRO_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "sabro_isp.db"))

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=25.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode and robust timeout for high concurrency in production
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=25000;")
    conn.execute("PRAGMA foreign_keys=ON;")
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

    # Users & Staff Logins (Admin, Recovery Boy, Complaint Boy, Staff)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL, -- Admin, Recovery Boy, Complaint Boy, Staff
        phone TEXT NOT NULL,
        assigned_area TEXT,
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

    # Tariffs / Packages (5MB: 1000, 15MB: 1200, 20MB: 1500, 25MB: 1800)
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
        onu_serial TEXT,
        db_box TEXT,
        fiber_core TEXT,
        cnic TEXT,
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

    # Support / Complaint Tickets (Assigned to Complain Boy)
    # Upstream Connect Communications Dealer Panel Integration
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dealer_sync_config (
        id INTEGER PRIMARY KEY,
        portal_name TEXT DEFAULT 'Connect Communications Dealer Portal',
        portal_url TEXT DEFAULT 'https://dealer.connect.net.pk',
        dealer_username TEXT DEFAULT 'sabro.dealer',
        dealer_password TEXT DEFAULT '',
        auto_sync_interval TEXT DEFAULT 'Manual',
        last_sync_time TEXT,
        last_sync_status TEXT DEFAULT 'Ready to Sync'
    )
    """)

    cursor.execute("""
    INSERT OR IGNORE INTO dealer_sync_config (id, portal_url, dealer_username)
    VALUES (1, 'https://dealer.connect.net.pk', 'sabro.dealer')
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
        ("onu_serial", "TEXT DEFAULT 'HWTC-10293847'"),
        ("db_box", "TEXT DEFAULT 'FDB-01, Pole #04'"),
        ("fiber_core", "TEXT DEFAULT 'Core 1 (Blue)'"),
        ("cnic", "TEXT DEFAULT '42101-1234567-1'"),
        ("installation_date", "TEXT")
    ]
    for col_name, col_def in ftth_columns:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE customers ADD COLUMN {col_name} {col_def}")
    conn.commit()

    # Update existing customers with realistic FTTH hardware identifiers if empty
    sample_ftth_specs = [
        (1, "HWTC-77218392", "FDB-04, Pole #12 (St-4)", "Core 2 (Orange)", "42101-3829103-1"),
        (2, "ZTEG-99381023", "FDB-02, Pole #07 (Royal)", "Core 1 (Blue)", "42101-7788991-3"),
        (3, "HWTC-44556677", "FDB-01, Pole #03 (Bazaar)", "Core 4 (Brown)", "42101-5544332-7"),
        (4, "FBR-11223344", "FDB-06, Pole #18 (Lane 3)", "Core 3 (Green)", "42101-8899001-5"),
        (5, "HWTC-99881122", "FDB-03, Pole #09 (Block 2)", "Core 2 (Orange)", "42101-6677889-9"),
        (6, "ZTEG-33445566", "FDB-05, Pole #15 (Street 9)", "Core 1 (Blue)", "42101-2233445-5"),
        (7, "HWTC-88776655", "FDB-07, Pole #21 (Plaza)", "Core 4 (Brown)", "42101-9988776-3"),
        (8, "FBR-55667788", "FDB-02, Pole #05 (Lane 5)", "Core 3 (Green)", "42101-1122334-7"),
        (9, "HWTC-12348765", "FDB-04, Pole #11 (Street 2)", "Core 1 (Blue)", "42101-4455667-2"),
        (10, "ZTEG-77665544", "FDB-08, Pole #24 (Comm)", "Core 2 (Orange)", "42101-3322114-8")
    ]
    for cid, onu, db_box, core, cnic in sample_ftth_specs:
        cursor.execute("""
            UPDATE customers 
            SET onu_serial = COALESCE(NULLIF(onu_serial, ''), ?),
                db_box = COALESCE(NULLIF(db_box, ''), ?),
                fiber_core = COALESCE(NULLIF(fiber_core, ''), ?),
                cnic = COALESCE(NULLIF(cnic, ''), ?),
                installation_date = COALESCE(NULLIF(installation_date, ''), '2026-09-01')
            WHERE id = ?
        """, (onu, db_box, core, cnic, cid))
    conn.commit()

    # Seed / Ensure Default Users & Staff (Admin, Tech, Recovery)
    default_users = [
        ('Ahmed Sabro (Owner)', 'admin', 'admin123', 'Admin', '0300-1234567', 'All Areas (Head Office)', 'Active', 0.0),
        ('Ahmed Baloch', 'ahmedbaloch', 'adminadmin', 'Admin', '0300-1234567', 'All Areas', 'Active', 0.0),
        ('Rashid Fiber Tech', 'rashid.tech', 'tech123', 'Complaint Boy', '0301-7788990', 'Sector A & Commercial Hub', 'Active', 0.0),
        ('Bilal Splicer', 'bilal.tech', 'tech123', 'Complaint Boy', '0333-7788991', 'Sector B & Royal Towers', 'Active', 0.0),
        ('Tariq Mehmood', 'tariq.rec', 'rec123', 'Recovery Boy', '0321-4455667', 'Sector B & Street 1-10', 'Active', 18600.0),
        ('Shahzaib Khan', 'shahzaib', 'rec123', 'Recovery Boy', '0300-1122334', 'Sector A & Main Bazaar', 'Active', 14400.0)
    ]
    for fn, un, pw, ro, ph, ar, st, tc in default_users:
        cursor.execute("SELECT id FROM users WHERE username = ?", (un,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, date('now'))
            """, (fn, un, pw, ro, ph, ar, st, tc))
    conn.commit()

    # Check if empty, seed defaults
    cursor.execute("SELECT COUNT(*) FROM tariffs")
    if cursor.fetchone()[0] == 0:
        # Settings
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('isp_name', 'Sabro Networks')")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('tagline', 'FTTH High-Speed Fiber Internet Billing & Recovery')")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('currency', 'PKR')")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('phone', '0300-1234567')")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('business_whatsapp', '923001234567')")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('email', 'info@sabronetworks.com')")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('address', 'Main Fiber Exchange Hub, Pakistan')")

        # EXACT PACKAGES
        tariffs = [
            ('5 MB FTTH Plan', 5, 1000, '5 Mbps High Speed Fiber Internet'),
            ('15 MB FTTH Plan', 15, 1200, '15 Mbps Ultra Streaming Fiber Internet'),
            ('20 MB FTTH Plan', 20, 1500, '20 Mbps Pro Fiber Internet for Gaming & HD'),
            ('25 MB FTTH Plan', 25, 1800, '25 MB Ultra Fiber Internet for Heavy Users')
        ]
        cursor.executemany("INSERT INTO tariffs (name, speed_mb, price, description) VALUES (?,?,?,?)", tariffs)

        # Customers (Customer Name + PPPoE Username)
        now = datetime.now()
        cust_list = [
            ('Muhammad Ali', 'ali.pppoe', '123456', '0301-2345678', 'House 45, Street 4', 'Sector A', 2, 'Active', (now + timedelta(days=20)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
            ('Usman Tariq', 'usman.ftth', 'usman12', '0312-9876543', 'Flat B-2, Royal Towers', 'Sector B', 3, 'Active', (now + timedelta(days=16)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
            ('Hamza Sheikh', 'hamza.sheikh', 'sheikh99', '0333-1122334', 'Shop 12, Main Market', 'Sector A', 4, 'Active', (now + timedelta(days=26)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
            ('Zubair Ahmed', 'zubair.net', 'zubair88', '0345-5544332', 'House 112, Lane 3', 'Sector C', 1, 'Expired', (now - timedelta(days=3)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
            ('Kashif Raza', 'kashif.pppoe', 'kashif77', '0321-7788990', 'House 9, Block 2', 'Sector A', 2, 'Active', (now + timedelta(days=12)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
            ('Kamran Khan', 'kamran.ftth', 'kamran321', '0300-8877665', 'House 78, Street 9', 'Sector B', 3, 'Active', (now + timedelta(days=18)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
            ('Asad Ullah', 'asad.connect', 'asad99', '0342-1234876', 'Plaza 3rd Floor', 'Sector C', 4, 'Expired', (now - timedelta(days=1)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
            ('Farhan Siddiqui', 'farhan.net', 'farhan1', '0305-6677889', 'House 22, Lane 5', 'Sector B', 2, 'Suspended', (now - timedelta(days=7)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
            ('Noman Javed', 'noman.pppoe', 'noman9', '0315-9988776', 'House 50, Street 2', 'Sector A', 1, 'Active', (now + timedelta(days=25)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
            ('Rizwan Malik', 'rizwan.fiber', 'malik2026', '0323-4433221', 'Shop 8, Commercial Area', 'Sector C', 3, 'Active', (now + timedelta(days=22)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'))
        ]
        cursor.executemany("""
        INSERT INTO customers (full_name, pppoe_username, password, phone, address, area, tariff_id, status, expiry_date, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """, cust_list)

        cursor.execute("SELECT id FROM users WHERE role = 'Recovery Boy' LIMIT 1")
        rec_user = cursor.fetchone()
        rec_id = rec_user[0] if rec_user else 1

        # Invoices (PAID & UNPAID)
        invoices = [
            ('INV-2026-001', 1, 1200, 'November 2026', 'Paid', (now + timedelta(days=5)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'), 'JazzCash', rec_id, now.strftime('%Y-%m-%d')),
            ('INV-2026-002', 2, 1500, 'November 2026', 'Paid', (now + timedelta(days=5)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'), 'EasyPaisa', rec_id, now.strftime('%Y-%m-%d')),
            ('INV-2026-003', 3, 1800, 'November 2026', 'Paid', (now + timedelta(days=5)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'), 'Cash', rec_id, now.strftime('%Y-%m-%d')),
            ('INV-2026-004', 4, 1000, 'November 2026', 'Unpaid', (now - timedelta(days=3)).strftime('%Y-%m-%d'), None, None, None, now.strftime('%Y-%m-%d')),
            ('INV-2026-005', 5, 1200, 'November 2026', 'Paid', (now + timedelta(days=8)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'), 'Cash', rec_id, now.strftime('%Y-%m-%d')),
            ('INV-2026-006', 6, 1500, 'November 2026', 'Paid', (now + timedelta(days=10)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'), 'Cash', rec_id, now.strftime('%Y-%m-%d')),
            ('INV-2026-007', 7, 1800, 'November 2026', 'Unpaid', (now - timedelta(days=1)).strftime('%Y-%m-%d'), None, None, None, now.strftime('%Y-%m-%d')),
            ('INV-2026-008', 8, 1200, 'November 2026', 'Unpaid', (now - timedelta(days=7)).strftime('%Y-%m-%d'), None, None, None, now.strftime('%Y-%m-%d')),
            ('INV-2026-009', 9, 1000, 'November 2026', 'Paid', (now + timedelta(days=15)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'), 'JazzCash', rec_id, now.strftime('%Y-%m-%d')),
            ('INV-2026-010', 10, 1500, 'November 2026', 'Paid', (now + timedelta(days=12)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'), 'Cash', rec_id, now.strftime('%Y-%m-%d'))
        ]
        cursor.executemany("""
        INSERT INTO invoices (invoice_number, customer_id, amount, month_period, status, due_date, paid_date, payment_method, collected_by_staff_id, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """, invoices)

        # Expenses
        now_str = datetime.now().strftime('%Y-%m-%d')
        expenses_data = [
            ('Upstream Bandwidth Main Fiber Link', 'Upstream Bandwidth', 15000.0, (now - timedelta(days=3)).strftime('%Y-%m-%d'), 'Admin', 'Monthly upstream fiber circuit payment', now_str),
            ('Fiber Drop Wire Roll (1000m) & Patch Cords', 'Fiber Wire & Splicing', 7500.0, (now - timedelta(days=2)).strftime('%Y-%m-%d'), 'Tariq', 'Purchased 2-core FTTH drop cable for Sector B extensions', now_str),
            ('Recovery Boys Bike Petrol Allowance', 'Petrol & Transport', 2500.0, (now - timedelta(days=1)).strftime('%Y-%m-%d'), 'Shahzaib', 'Weekly fuel allowance for recovery team', now_str),
            ('Fiber Optic Machine Splicing Charges', 'Fiber Wire & Splicing', 1800.0, now.strftime('%Y-%m-%d'), 'Admin', 'Joint enclosure splicing on main trunk line', now_str),
            ('Office Tea, Refreshments & Electricity', 'Office / Tea / Misc', 2200.0, now.strftime('%Y-%m-%d'), 'Admin', 'Monthly misc utilities and client hospitality', now_str)
        ]
        cursor.executemany("""
        INSERT INTO expenses (title, category, amount, date, paid_by, notes, created_at)
        VALUES (?,?,?,?,?,?,?)
        """, expenses_data)

        # Deposits
        deposits_data = [
            (1, 'ONU Security Deposit', 2500.0, 'Held', (now - timedelta(days=45)).strftime('%Y-%m-%d'), 'Dual-Band Gigabit XPON ONU Security', now_str),
            (2, 'Fiber Installation Fee', 1500.0, 'Held', (now - timedelta(days=30)).strftime('%Y-%m-%d'), 'Drop cable & installation labor charge', now_str),
            (3, 'ONU Security Deposit', 2500.0, 'Held', (now - timedelta(days=25)).strftime('%Y-%m-%d'), 'Huawei EchoLife HG8145V5 Security', now_str),
            (5, 'Advance Bill Deposit', 1200.0, 'Adjusted', (now - timedelta(days=20)).strftime('%Y-%m-%d'), '1-Month advance payment on booking', now_str),
            (6, 'ONU Security Deposit', 2500.0, 'Held', (now - timedelta(days=15)).strftime('%Y-%m-%d'), 'XPON WiFi ONU Security Deposit', now_str),
            (9, 'Fiber Installation Fee', 1500.0, 'Held', (now - timedelta(days=10)).strftime('%Y-%m-%d'), 'Drop fiber wire installation fee', now_str),
            (10, 'ONU Security Deposit', 2500.0, 'Held', (now - timedelta(days=5)).strftime('%Y-%m-%d'), 'Dual band ONU deposit', now_str)
        ]
        cursor.executemany("""
        INSERT INTO deposits (customer_id, deposit_type, amount, status, date, notes, created_at)
        VALUES (?,?,?,?,?,?,?)
        """, deposits_data)

        # Investments
        sample_investments = [
            ('Ahmed Sabro (Owner)', 'Main Huawei GPON OLT 8-Port Machine', 220000.0, 'Core Hardware & OLT', '2026-09-15', 'Full GPON OLT with 8x C++ SFP modules', now_str),
            ('Ahmed Sabro (Owner)', 'FTTH Optical Fiber Backbone Cables & Splice Enclosures', 130000.0, 'Fiber Distribution Network', '2026-09-22', '12-core and 24-core armored fiber cables for main lines', now_str),
            ('Ahmed Sabro (Owner)', 'Fujikura Optical Fiber Splicing Machine & OTDR Tester', 95000.0, 'Tools & Splicing Equipment', '2026-10-01', 'Complete fiber toolkit and high precision cleaver', now_str),
            ('Ahmed Sabro (Owner)', 'Central Server Room Heavy Backup UPS & Tubular Batteries', 75000.0, 'Backup Power & UPS', '2026-10-10', '24V 2.5kVA Pure Sine Wave Inverter for 10-hour backup', now_str)
        ]
        cursor.executemany("""
        INSERT INTO investments (investor_name, title, amount, category, date, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_investments)

        cursor.execute("SELECT id FROM users WHERE role = 'Complaint Boy' LIMIT 1")
        tech_user = cursor.fetchone()
        tech_id = tech_user[0] if tech_user else 1

        # Sample Tickets assigned to Complaint Boy
        sample_tickets = [
            ('TCK-2026-001', 4, 'Red LOS Light Blinking on ONU (No Internet)', 'Customer reported fiber wire got pinched during street construction. Red light blinking on Huawei ONU.', 'Critical', 'Open', tech_id, 'Technician dispatched with fiber cleaver and patch cords.', now.strftime('%Y-%m-%d %H:%M'), None),
            ('TCK-2026-002', 1, 'WiFi Speed Low & Frequent Disconnection', 'Customer requested checking signal loss (optical power rx). Currently at -28dBm.', 'Medium', 'In Progress', tech_id, 'Checking splice tray at nearest FDB box.', now.strftime('%Y-%m-%d %H:%M'), None),
            ('TCK-2026-003', 6, 'Shift Connection to New Room (Fiber Extension)', 'Customer shifted PC to upper floor, needs 15m optical patch cord routed.', 'Low', 'Resolved', tech_id, 'Patch cord laid and router tested. Speed 20MB verified.', (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M'), now.strftime('%Y-%m-%d %H:%M'))
        ]
        cursor.executemany("""
        INSERT INTO tickets (ticket_number, customer_id, subject, details, priority, status, assigned_user_id, resolution_notes, created_at, resolved_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """, sample_tickets)

        conn.commit()

    conn.close()

if __name__ == "__main__":
    init_db(force_reset=True)
    print("Database updated with Users (Logins), Tickets, and full Edit schema!")
