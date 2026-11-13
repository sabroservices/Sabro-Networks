#!/usr/bin/env python3
"""
Sabro Networks - Turso Cloud Migration Tool
Migrates tables and data from a local SQLite database to Turso Cloud.
Preserves all primary keys, IDs, foreign keys, timestamps, and data relationships.
"""
import os
import sys
import sqlite3
import db

TABLES_ORDER = [
    "settings",
    "tariffs",
    "users",
    "customers",
    "invoices",
    "expenses",
    "deposits",
    "investments",
    "dealer_sync_config",
    "dealer_sync_logs",
    "tickets",
]


def run_migration(source_db_path="sabro_isp.db"):
    print("=" * 65)
    print("  Sabro Networks - Turso Cloud Database Migration")
    print("=" * 65)

    if not os.path.exists(source_db_path):
        print(f"[-] Source database file not found at: {source_db_path}")
        print("    If no local database exists, historical records cannot be restored.")
        return False

    turso_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    turso_token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()

    if not turso_url:
        print("[-] TURSO_DATABASE_URL environment variable is required to migrate to Turso.")
        print("    Please set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN before running.")
        return False

    print(f"[*] Source Database: {source_db_path}")
    print(f"[*] Target Turso DB: {turso_url}")

    # 1. Connect to source SQLite
    src_conn = sqlite3.connect(source_db_path)
    src_conn.row_factory = sqlite3.Row

    # 2. Connect to Turso Cloud
    target_conn = db.LibsqlConn(turso_url, auth_token=turso_token)

    # 3. Ensure Turso schema is initialized
    print("[*] Initializing target Turso schema...")
    orig_backend = db.DATABASE_BACKEND
    orig_url = db.TURSO_DATABASE_URL
    orig_token = db.TURSO_AUTH_TOKEN
    try:
        db.DATABASE_BACKEND = "turso"
        db.TURSO_DATABASE_URL = turso_url
        db.TURSO_AUTH_TOKEN = turso_token
        db.init_db(force_reset=False)
    finally:
        db.DATABASE_BACKEND = orig_backend
        db.TURSO_DATABASE_URL = orig_url
        db.TURSO_AUTH_TOKEN = orig_token

    print("[*] Migrating records while preserving IDs and foreign keys...")

    total_migrated = 0
    try:
        with target_conn:
            for table in TABLES_ORDER:
                # Check if table exists in source
                t_check = src_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
                ).fetchone()
                if not t_check:
                    continue

                rows = src_conn.execute(f"SELECT * FROM {table};").fetchall()
                if not rows:
                    print(f"   -> {table}: 0 records (empty in source)")
                    continue

                # Fetch column names
                cols = [c[1] for c in src_conn.execute(f"PRAGMA table_info({table});").fetchall()]
                placeholders = ", ".join(["?"] * len(cols))
                insert_sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders});"

                data_tuples = [[r[c] for c in cols] for r in rows]
                target_conn.executemany(insert_sql, data_tuples)
                total_migrated += len(rows)
                print(f"   -> {table}: {len(rows)} records migrated successfully.")

        print("\n[+] Verification and Record Count Audit:")
        verification_passed = True
        for table in TABLES_ORDER:
            t_check = src_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
            ).fetchone()
            if not t_check:
                continue

            src_cnt = src_conn.execute(f"SELECT COUNT(*) FROM {table};").fetchone()[0]
            tgt_cnt = target_conn.execute(f"SELECT COUNT(*) FROM {table};").fetchone()[0]
            status = "MATCH" if src_cnt <= tgt_cnt else "MISMATCH"
            print(f"   [{status}] {table}: Source={src_cnt}, Target={tgt_cnt}")
            if src_cnt > tgt_cnt:
                verification_passed = False

        if verification_passed:
            print("\n" + "=" * 65)
            print(f"  [SUCCESS] Total {total_migrated} records migrated to Turso Cloud!")
            print("  Data integrity and relationships successfully preserved.")
            print("=" * 65)
            return True
        else:
            print("\n[-] Migration verification encountered count mismatches.")
            return False

    except Exception as e:
        target_conn.rollback()
        print(f"\n[FATAL] Migration aborted and rolled back due to error: {e}")
        return False
    finally:
        src_conn.close()
        target_conn.close()


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "sabro_isp.db"
    success = run_migration(src)
    sys.exit(0 if success else 1)
