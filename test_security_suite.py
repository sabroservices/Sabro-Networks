import os
import shutil
import tempfile
import unittest
import db
import app as flask_app


class SabroNetworksSecurityTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db_path = db.DB_PATH
        cls._tmp_dir = tempfile.mkdtemp(prefix="sabro_sec_test_")
        db.DB_PATH = os.path.join(cls._tmp_dir, "test_sabro.db")
        db.init_db(force_reset=True)

        flask_app.app.config["TESTING"] = True
        cls.client = flask_app.app.test_client()

        conn = db.get_db()
        # Insert temporary test fixtures only inside the isolated temp DB
        conn.execute(
            "INSERT INTO tariffs (name, speed_mb, price, description) VALUES ('15 MB FTTH', 15, 1200, 'Fiber Plan')"
        )
        conn.execute(
            """INSERT INTO customers (full_name, pppoe_username, password, phone, address, area, tariff_id, status, expiry_date, created_at)
               VALUES ('Test Customer', 'test.pppoe', 'pass123', '03001112233', 'House 1', 'Sector A', 1, 'Active', '2026-12-30', date('now'))"""
        )
        conn.execute(
            """INSERT INTO invoices (invoice_number, customer_id, amount, month_period, status, due_date, created_at)
               VALUES ('INV-TEST-001', 1, 1200, 'November 2026', 'Unpaid', '2026-11-30', date('now'))"""
        )
        conn.execute(
            """INSERT INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
               VALUES ('Test Tech', 'test.tech', 'techpass1', 'Complaint Boy', '03011112233', 'Sector A', 'Active', 0, date('now'))"""
        )
        conn.commit()
        cls.admin_user = "ahmedbaloch"
        cls.admin_pass = "adminadmin1"
        cls.tech_user = "test.tech"
        cls.tech_pass = "techpass1"
        cls.cust_id = 1
        conn.close()

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls._orig_db_path
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def test_00_clean_initial_db_and_single_admin_enforced(self):
        """Fresh database reset must contain zero operational data and strictly one Main Admin (ahmedbaloch)."""
        clean_db = os.path.join(self._tmp_dir, "verify_clean.db")
        prev = db.DB_PATH
        db.DB_PATH = clean_db
        try:
            db.init_db(force_reset=True)
            conn = db.get_db()
            users = conn.execute("SELECT username, role FROM users").fetchall()
            self.assertEqual(len(users), 1)
            self.assertEqual(users[0]["username"], "ahmedbaloch")
            self.assertEqual(users[0]["role"], "Admin")
            for tbl in ("customers", "tariffs", "invoices", "tickets", "expenses", "deposits", "investments"):
                cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                self.assertEqual(cnt, 0, f"Table {tbl} must be empty on clean reset")
            conn.close()

            # Legacy demo credentials must fail
            res_old = self.client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
            self.assertIn("Invalid username or password", res_old.get_data(as_text=True))

            # Main admin ahmedbaloch / adminadmin1 must authenticate
            res_new = self.client.post("/login", data={"username": "ahmedbaloch", "password": "adminadmin1"}, follow_redirects=True)
            self.assertEqual(res_new.status_code, 200)
            self.assertIn("Ahmed Baloch", res_new.get_data(as_text=True))

            # Empty DB must render every primary view cleanly with HTTP 200
            for route in ("/", "/customers", "/invoices", "/tickets", "/staff", "/investments", "/expenses", "/deposits", "/tariffs", "/settings"):
                r = self.client.get(route)
                self.assertEqual(r.status_code, 200, f"Empty state view {route} crashed with {r.status_code}")

            # Adding customer with no tariffs must work cleanly without FK crash
            r_cust = self.client.post("/customers/add", data={
                "full_name": "Clean Init Subscriber",
                "pppoe_username": "clean.sub",
                "password": "pw",
                "phone": "03009998877",
                "area": "Zone 1",
                "address": "House 5",
                "tariff_id": ""
            }, follow_redirects=True)
            self.assertEqual(r_cust.status_code, 200)
            self.assertIn("Clean Init Subscriber", r_cust.get_data(as_text=True))
            self.client.get("/logout")
        finally:
            db.DB_PATH = prev

    def test_01_unauthenticated_welcome_blocked(self):
        """Unauthenticated requests to customer_whatsapp_welcome must be blocked (302 to /login)."""
        self.client.get("/logout")
        res = self.client.get(f"/customer/{self.cust_id}/whatsapp_welcome")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    def test_02_complaint_boy_blocked_from_welcome(self):
        """Complaint Boy / technician accounts must be blocked from dumping customer welcome credentials."""
        self.client.post("/login", data={"username": self.tech_user, "password": self.tech_pass})
        res = self.client.get(f"/customer/{self.cust_id}/whatsapp_welcome")
        self.assertEqual(res.status_code, 302)
        self.client.get("/logout")

    def test_03_staff_password_masking(self):
        """Staff directory table and edit modal must never leak passwords in cleartext or display hashes."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        res = self.client.get("/staff")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("••••••••", html)
        self.assertNotIn("copyToClipboard('adminadmin1'", html)
        self.assertNotIn("copyToClipboard('techpass1'", html)
        self.assertIn("Leave blank to keep current", html)
        self.client.get("/logout")

    def test_04_admin_dashboard_focuses_on_complaints(self):
        """Admin dashboard must prominently feature FTTH complaints queue while keeping other stuff hidden."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Complaints Center", html)
        self.assertIn("Active FTTH Subscriber Complaints Queue", html)
        self.assertIn("adminOtherOverview", html)
        self.client.get("/logout")

    def test_05_clean_billing_data_no_pppoe(self):
        """Invoices and WhatsApp bills must only show Customer Name, Package, and Total Amount, with zero PPPoE or hardware details."""
        res = self.client.get("/invoice/1/print")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Customer Name", html)
        self.assertIn("Internet Package", html)
        self.assertIn("Total Amount", html)
        self.assertNotIn("PPPoE User", html)
        self.assertNotIn("ONT Serial", html)
        self.assertNotIn("Drop Core", html)

        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        res_wa = self.client.get("/invoice/1/whatsapp")
        self.assertEqual(res_wa.status_code, 302)
        wa_url = res_wa.headers.get("Location", "")
        self.assertIn("Customer%20Name", wa_url)
        self.assertIn("Internet%20Package", wa_url)
        self.assertIn("Total%20Amount", wa_url)
        self.assertNotIn("PPPoE%20Username", wa_url)
        self.client.get("/logout")

    def test_06_defensive_input_validation_and_backup_cleanup(self):
        """Verify negative inputs are defended and atomic database backup executes without resource leak."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        self.client.post("/expenses", data={
            "title": "Hardware Patch Test",
            "category": "Office",
            "amount": "-500",
            "date": "2026-11-07"
        }, follow_redirects=True)
        conn = db.get_db()
        exp = conn.execute("SELECT amount FROM expenses WHERE title = 'Hardware Patch Test'").fetchone()
        self.assertIsNotNone(exp)
        self.assertGreaterEqual(exp["amount"], 0.0)
        conn.close()

        res_bk = self.client.get("/backup/db")
        self.assertEqual(res_bk.status_code, 200)
        self.assertTrue(res_bk.data.startswith(b"SQLite format 3"))
        self.client.get("/logout")


if __name__ == "__main__":
    unittest.main()
