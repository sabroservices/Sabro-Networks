import db
import sqlite3

# 1. Update active database sabro_isp.db directly
conn = db.get_db()
cursor = conn.cursor()
cols = [c[1] for c in cursor.execute("PRAGMA table_info(users)").fetchall()]
if "pfp_image" not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN pfp_image TEXT DEFAULT ''")
    print("Added pfp_image column to users table")
if "technician_xp" not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN technician_xp INTEGER DEFAULT 0")
    print("Added technician_xp column to users table")
conn.commit()
conn.close()

# 2. Update db.py init_db to ensure columns are always added in future
with open('db.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = '''    cursor.execute("""
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
        created_at TEXT
    )
    """)'''

replacement = '''    cursor.execute("""
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
        cursor.execute("ALTER TABLE users ADD COLUMN technician_xp INTEGER DEFAULT 0;")'''

if target in text:
    text = text.replace(target, replacement)
    with open('db.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Updated db.py init_db schema")
else:
    print("Target not found in db.py")
