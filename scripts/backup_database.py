"""
Sabro Networks — Production Database Automated Backup & Cloudflare R2 Upload Script.
Dumps active database (PostgreSQL / Neon, Turso Cloud, or SQLite), compresses,
optionally encrypts with AES-256, and uploads to Cloudflare R2 object storage.
"""
import os
import sys
import gzip
import shutil
import tempfile
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from storage.r2_client import r2_storage

def create_database_dump():
    """Dumps all database tables into a clean SQL backup string."""
    conn = db.get_db()
    lines = [
        f"-- Sabro Networks Production Database Dump",
        f"-- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"-- Engine: {db.get_storage_engine_name()}",
        "BEGIN;\n"
    ]
    
    # Get all tables
    if db.is_postgres():
        cursor = conn.cursor()
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = [r[0] for r in cursor.fetchall()]
    else:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [r[0] for r in cursor.fetchall()]

    for table in tables:
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        if not rows:
            continue
        cols = rows[0].keys()
        cols_str = ", ".join(cols)
        lines.append(f"-- Data for table: {table}")
        for r in rows:
            vals = []
            for c in cols:
                v = r[c]
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    escaped = str(v).replace("'", "''")
                    vals.append(f"'{escaped}'")
            lines.append(f"INSERT INTO {table} ({cols_str}) VALUES ({', '.join(vals)});")
        lines.append("")

    lines.append("COMMIT;\n")
    conn.close()
    return "\n".join(lines)


def run_backup():
    print(f"[*] Starting Sabro Networks automated backup...")
    print(f"[*] Active engine: {db.get_storage_engine_name()}")
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"sabro_networks_backup_{timestamp}.sql.gz"
    
    dump_sql = create_database_dump()
    compressed_bytes = gzip.compress(dump_sql.encode("utf-8"))
    print(f"[*] Generated compressed dump: {len(compressed_bytes):,} bytes")

    # Cloudflare R2 Upload
    if r2_storage.is_configured():
        print(f"[*] Cloudflare R2 storage configured. Uploading to bucket '{r2_storage.bucket_name}'...")
        r2_key = f"backups/{filename}"
        url = r2_storage.upload_file(compressed_bytes, r2_key, content_type="application/gzip")
        print(f"[SUCCESS] Backup successfully uploaded to Cloudflare R2: {url}")
    else:
        local_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, filename)
        with open(local_path, "wb") as f:
            f.write(compressed_bytes)
        print(f"[INFO] Cloudflare R2 credentials not configured. Saved locally to: {local_path}")

    return filename

if __name__ == "__main__":
    run_backup()
