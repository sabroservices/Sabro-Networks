#!/usr/bin/env python3
"""
Database Initialization & Seeding CLI for Sabro Networks ISP Portal.
Usage:
    python init_db.py         # Initializes tables and default seeds if missing
    python init_db.py --reset # Force-resets the database to clean fresh state
"""
import sys
import os
import db

def main():
    force_reset = "--reset" in sys.argv
    action = "Resetting and reinitializing" if force_reset else "Initializing"
    print(f"[*] {action} Sabro Networks FTTH database at: {db.DB_PATH}")
    db.init_db(force_reset=force_reset)
    print("[+] Database schema, performance indexes, and default seeds verified successfully.")
    print("    - Admin:        admin / admin123")
    print("    - Technician:   rashid.tech / tech123")
    print("    - Recovery:     tariq.rec / rec123")

if __name__ == "__main__":
    main()
