import unittest
import os
import tempfile
import sqlite3
import db

class TestTursoDatabaseLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up isolated test database
        cls._orig_db_path = db.DB_PATH
        cls._temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._temp_path = cls._temp_file.name
        cls._temp_file.close()
        db.DB_PATH = cls._temp_path
        db.init_db(force_reset=True)

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls._orig_db_path
        if os.path.exists(cls._temp_path):
            try:
                os.remove(cls._temp_path)
            except Exception:
                pass

    def test_01_database_connection(self):
        """Verify database connection opens cleanly and reports valid storage engine."""
        conn = db.get_db()
        self.assertIsNotNone(conn)
        engine_name = db.get_storage_engine_name()
        self.assertIsInstance(engine_name, str)
        conn.close()

    def test_02_table_initialization(self):
        """Verify all 11 required system tables are initialized."""
        conn = db.get_db()
        expected_tables = {
            "settings", "users", "tariffs", "customers", "invoices",
            "expenses", "deposits", "investments", "dealer_sync_config",
            "dealer_sync_logs", "tickets"
        }
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
        actual_tables = {r[0] for r in rows}
        conn.close()
        for t in expected_tables:
            self.assertIn(t, actual_tables, f"Missing required table: {t}")

    def test_03_schema_compatibility(self):
        """Verify dynamic columns and performance indexes exist."""
        conn = db.get_db()
        # Verify users columns
        u_cols = [c[1] for c in conn.execute("PRAGMA table_info(users);").fetchall()]
        self.assertIn("pfp_image", u_cols)
        self.assertIn("technician_xp", u_cols)

        # Verify customers columns
        c_cols = [c[1] for c in conn.execute("PRAGMA table_info(customers);").fetchall()]
        for expected in ["onu_serial", "db_box", "fiber_core", "cnic", "installation_date"]:
            self.assertIn(expected, c_cols)

        # Verify indexes
        idx_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index';").fetchall()
        indexes = {r[0] for r in idx_rows}
        self.assertIn("idx_invoices_customer", indexes)
        self.assertIn("idx_tickets_customer", indexes)
        conn.close()

    def test_04_insert_and_select(self):
        """Verify parameterized INSERT and SELECT operations."""
        conn = db.get_db()
        conn.execute("INSERT INTO tariffs (name, speed_mb, price, description) VALUES (?, ?, ?, ?)",
                     ("Test 50M", 50, 3500.0, "High Speed"))
        conn.commit()

        row = conn.execute("SELECT * FROM tariffs WHERE name = ?", ("Test 50M",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["speed_mb"], 50)
        self.assertEqual(row["price"], 3500.0)
        conn.close()

    def test_05_update_and_delete(self):
        """Verify UPDATE and DELETE operations."""
        conn = db.get_db()
        conn.execute("INSERT INTO tariffs (name, speed_mb, price, description) VALUES (?, ?, ?, ?)",
                     ("Temporary Plan", 5, 500.0, "Temp"))
        conn.commit()

        conn.execute("UPDATE tariffs SET price = ? WHERE name = ?", (600.0, "Temporary Plan"))
        conn.commit()
        updated = conn.execute("SELECT price FROM tariffs WHERE name = ?", ("Temporary Plan",)).fetchone()
        self.assertEqual(updated["price"], 600.0)

        conn.execute("DELETE FROM tariffs WHERE name = ?", ("Temporary Plan",))
        conn.commit()
        deleted = conn.execute("SELECT * FROM tariffs WHERE name = ?", ("Temporary Plan",)).fetchone()
        self.assertIsNone(deleted)
        conn.close()

    def test_06_parameterized_sql(self):
        """Verify parameterized queries handle special characters and sql injection safely."""
        conn = db.get_db()
        malicious_input = "'; DROP TABLE tariffs; --"
        conn.execute("INSERT INTO tariffs (name, speed_mb, price, description) VALUES (?, ?, ?, ?)",
                     (malicious_input, 10, 1200.0, "Safe"))
        conn.commit()

        row = conn.execute("SELECT * FROM tariffs WHERE name = ?", (malicious_input,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["name"], malicious_input)

        # Tariffs table must still exist intact
        cnt = conn.execute("SELECT COUNT(*) FROM tariffs;").fetchone()[0]
        self.assertGreaterEqual(cnt, 1)
        conn.close()

    def test_07_named_row_access(self):
        """Verify named column access on LibsqlRow and sqlite3.Row."""
        row = db.LibsqlRow(["id", "username", "role", "total_collected"], [10, "test_tech", "Complaint Boy", 250.0])
        self.assertEqual(row["username"], "test_tech")
        self.assertEqual(row["role"], "Complaint Boy")
        self.assertEqual(row.get("total_collected"), 250.0)
        self.assertEqual(row.get("missing_key", "default_val"), "default_val")
        self.assertTrue("username" in row)
        self.assertTrue("role" in row.keys())
        self.assertEqual(len(row), 4)

    def test_08_positional_row_access(self):
        """Verify positional index access on LibsqlRow."""
        row = db.LibsqlRow(["id", "name", "price"], [1, "Gold 100M", 5000.0])
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], "Gold 100M")
        self.assertEqual(row[2], 5000.0)
        self.assertEqual(list(row), [1, "Gold 100M", 5000.0])

    def test_09_transactions(self):
        """Verify atomic transactions commit correctly."""
        conn = db.get_db()
        with conn:
            conn.execute("INSERT INTO expenses (title, category, amount, date) VALUES (?, ?, ?, ?)",
                         ("Router Power Adapter", "Hardware", 750.0, "2026-11-13"))
        conn.close()

        conn2 = db.get_db()
        exp = conn2.execute("SELECT * FROM expenses WHERE title = ?", ("Router Power Adapter",)).fetchone()
        self.assertIsNotNone(exp)
        self.assertEqual(exp["amount"], 750.0)
        conn2.close()

    def test_10_rollbacks(self):
        """Verify rollbacks prevent partial writes when an exception is raised."""
        conn = db.get_db()
        initial_count = conn.execute("SELECT COUNT(*) FROM expenses;").fetchone()[0]

        try:
            with conn:
                conn.execute("INSERT INTO expenses (title, category, amount, date) VALUES (?, ?, ?, ?)",
                             ("Uncommitted Expense", "Office", 5000.0, "2026-11-13"))
                raise RuntimeError("Simulated transaction failure during expense recording")
        except RuntimeError:
            pass

        after_count = conn.execute("SELECT COUNT(*) FROM expenses;").fetchone()[0]
        self.assertEqual(initial_count, after_count, "Rollback failed: partial record was written to database")
        conn.close()

    def test_11_foreign_keys(self):
        """Verify foreign key enforcement is enabled."""
        conn = db.get_db()
        # Attempt to insert customer with non-existent tariff_id
        try:
            conn.execute("""
                INSERT INTO customers (full_name, pppoe_username, password, tariff_id, created_at)
                VALUES ('Foreign Key Test', 'fk.test', 'pass123', 999999, '2026-11-13')
            """)
            conn.commit()
            fk_enforced = False
        except sqlite3.IntegrityError:
            fk_enforced = True
        except Exception:
            fk_enforced = True
        finally:
            conn.close()

        self.assertTrue(fk_enforced, "Foreign key constraint was not enforced on invalid tariff_id")

    def test_12_unique_constraints(self):
        """Verify unique constraints prevent duplicate usernames."""
        conn = db.get_db()
        conn.execute("""
            INSERT INTO users (full_name, username, password, role, created_at)
            VALUES ('Unique User 1', 'unique_staff', 'pass1', 'Staff', '2026-11-13')
        """)
        conn.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("""
                INSERT INTO users (full_name, username, password, role, created_at)
                VALUES ('Duplicate User', 'unique_staff', 'pass2', 'Staff', '2026-11-13')
            """)
            conn.commit()
        conn.close()

    def test_13_bulk_inserts(self):
        """Verify executemany and batch insertions."""
        conn = db.get_db()
        tariffs_data = [
            ("Bulk Plan 1", 10, 1000.0, "B1"),
            ("Bulk Plan 2", 20, 2000.0, "B2"),
            ("Bulk Plan 3", 30, 3000.0, "B3"),
        ]
        conn.executemany("INSERT INTO tariffs (name, speed_mb, price, description) VALUES (?, ?, ?, ?)", tariffs_data)
        conn.commit()

        rows = conn.execute("SELECT * FROM tariffs WHERE name LIKE 'Bulk Plan%'").fetchall()
        self.assertEqual(len(rows), 3)
        conn.close()

    def test_14_connection_cleanup(self):
        """Verify connection close releases resources."""
        conn = db.get_db()
        self.assertFalse(getattr(conn, "closed", False))
        conn.close()
        # In sqlite3, executing after close raises ProgrammingError
        if isinstance(conn, sqlite3.Connection):
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1;")

    def test_15_production_validation_error(self):
        """Verify production validator raises RuntimeError if TURSO config is missing when required."""
        orig_backend = db.DATABASE_BACKEND
        orig_url = db.TURSO_DATABASE_URL
        orig_token = db.TURSO_AUTH_TOKEN
        try:
            db.DATABASE_BACKEND = "turso"
            db.TURSO_DATABASE_URL = ""
            db.TURSO_AUTH_TOKEN = ""
            with self.assertRaises(RuntimeError) as ctx:
                db.validate_production_config()
            self.assertIn("Production requires persistent Turso Cloud database", str(ctx.exception))
        finally:
            db.DATABASE_BACKEND = orig_backend
            db.TURSO_DATABASE_URL = orig_url
            db.TURSO_AUTH_TOKEN = orig_token

if __name__ == "__main__":
    unittest.main()
