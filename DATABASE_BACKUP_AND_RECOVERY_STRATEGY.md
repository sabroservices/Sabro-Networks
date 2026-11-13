# Sabro Networks – Enterprise Database Backup & Disaster Recovery Strategy

## 1. Primary Strategy: Turso Cloud Managed Persistence

The production instance of Sabro Networks utilizes **Turso Cloud** (powered by libSQL) as its primary database.
- **Data Persistence:** Database files do not reside on Render's ephemeral container filesystem. Data is persisted across all container spin-downs, restarts, and redeployments.
- **High Availability & Replication:** Turso manages storage across primary cloud regions with automatic WAL syncing.
- **Zero Local Disk Dependency:** Render containers remain stateless application runners.

---

## 2. Point-in-Time Web Portal Backups

Administrators can export and download complete binary database snapshots directly from the web interface:

1. Navigate to **Settings** &rarr; **Database Storage Engine & Persistence Status**.
2. Click **Download Backup (.db)**.
3. The server generates an atomic, consistent binary SQLite snapshot (`sabro_networks_backup_YYYYMMDD_HHMMSS.db`).
4. Store the downloaded `.db` file in secure off-site storage (e.g. Google Drive, encrypted local drive).

---

## 3. Disaster Recovery & Database Restoration

If an emergency restoration is ever required:

### Method A: Web Portal 1-Click Restore
1. Open the Sabro Networks portal and sign in as Main Admin (`ahmedbaloch`).
2. Go to **Settings** &rarr; **Upload & Restore Backup**.
3. Select your verified `.db` backup file.
4. The system automatically creates a safety snapshot of the current state, runs an integrity check (`PRAGMA integrity_check`), and restores all tables, subscribers, invoices, tariffs, and tickets.

### Method B: CLI Migration & Direct Sync
If restoring from a command line:
```bash
export TURSO_DATABASE_URL="libsql://your-db.turso.io"
export TURSO_AUTH_TOKEN="your-token"
python migrate_to_turso.py /path/to/backup.db
```

---

## 4. Automated Backup Schedule Recommendation

For telecom operations with active subscribers:
- **Weekly Snapshot:** Download a manual `.db` binary backup every Sunday evening.
- **Monthly Revenue Audit:** Export subscriber and invoice CSV data from **Invoices** &rarr; **Export CSV** at month-end closing.
- **Pre-Update Snapshot:** Before running major software updates or server re-configurations, download a fresh `.db` snapshot.
