#!/usr/bin/env python3
"""
Database Initialization CLI for Sabro Networks ISP Portal.
Usage:
    python init_db.py         # Initializes clean tables and ensures Main Admin exists if DB is empty
    python init_db.py --reset # Force-resets the database to a clean empty state with only Main Admin
"""
import sys
import db


def main():
    force_reset = "--reset" in sys.argv
    action = "Resetting and reinitializing" if force_reset else "Initializing"
    print(f"[*] {action} clean Sabro Networks FTTH database at: {db.DB_PATH}")
    db.init_db(force_reset=force_reset)
    print("[+] Clean schema, performance indexes, and single Main Admin verified.")
    print("    - Main Admin Username: ahmedbaloch (full unrestricted access)")


if __name__ == "__main__":
    main()
