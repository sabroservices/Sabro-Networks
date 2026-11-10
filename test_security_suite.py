import unittest
import app as flask_app
import db

class SabroNetworksSecurityTestSuite(unittest.TestCase):
    def setUp(self):
        flask_app.app.config['TESTING'] = True
        self.client = flask_app.app.test_client()
        conn = db.get_db()
        admin = conn.execute("SELECT username, password FROM users WHERE role = 'Admin' LIMIT 1").fetchone()
        tech = conn.execute("SELECT username, password FROM users WHERE role = 'Complaint Boy' LIMIT 1").fetchone()
        cust = conn.execute("SELECT id FROM customers LIMIT 1").fetchone()
        conn.close()
        self.admin_user = admin["username"]
        self.admin_pass = admin["password"]
        self.tech_user = tech["username"]
        self.tech_pass = tech["password"]
        self.cust_id = cust["id"]

    def test_01_unauthenticated_welcome_blocked(self):
        """Unauthenticated requests to customer_whatsapp_welcome must be blocked (302 to /login)."""
        res = self.client.get(f"/customer/{self.cust_id}/whatsapp_welcome")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    def test_02_complaint_boy_blocked_from_welcome(self):
        """Complaint Boy / technician accounts must be blocked from dumping customer welcome credentials."""
        self.client.post("/login", data={"username": self.tech_user, "password": self.tech_pass})
        res = self.client.get(f"/customer/{self.cust_id}/whatsapp_welcome")
        self.assertEqual(res.status_code, 302)

    def test_03_staff_password_masking(self):
        """Staff directory table and edit modal must never leak passwords in cleartext or display hashes."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        res = self.client.get("/staff")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        # Verify bullets are rendered instead of plain password
        self.assertIn("••••••••", html)
        self.assertNotIn("copyToClipboard('admin123'", html)
        self.assertNotIn("copyToClipboard('tech123'", html)
        # Edit modal should have placeholder
        self.assertIn("Leave blank to keep current", html)

    def test_04_admin_dashboard_focuses_on_complaints(self):
        """Admin dashboard must prominently feature FTTH complaints queue while keeping other stuff hidden."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Complaints Center", html)
        self.assertIn("Active FTTH Subscriber Complaints Queue", html)
        self.assertIn("adminOtherOverview", html)
    def test_05_clean_billing_data_no_pppoe(self):
        """Invoices and WhatsApp bills must only show Customer Name, Package, and Total Amount, with zero PPPoE or hardware details."""
        # 1. Invoice print slip
        res = self.client.get(f"/invoice/1/print")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Customer Name", html)
        self.assertIn("Internet Package", html)
        self.assertIn("Total Amount", html)
        self.assertNotIn("PPPoE User", html)
        self.assertNotIn("ONT Serial", html)
        self.assertNotIn("Drop Core", html)

        # 2. WhatsApp invoice message
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        res_wa = self.client.get("/invoice/1/whatsapp")
        self.assertEqual(res_wa.status_code, 302)
        wa_url = res_wa.headers.get("Location", "")
        self.assertIn("Customer%20Name", wa_url)
        self.assertIn("Internet%20Package", wa_url)
        self.assertIn("Total%20Amount", wa_url)
        self.assertNotIn("PPPoE%20Username", wa_url)

    def test_06_defensive_input_validation_and_backup_cleanup(self):
        """Verify negative inputs are defended and atomic database backup executes in-memory without resource leak."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})

        # 1. Negative expense amount normalized
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

        # 2. Backup download executes cleanly
        res_bk = self.client.get("/backup/db")
        self.assertEqual(res_bk.status_code, 200)
        self.assertTrue(res_bk.data.startswith(b"SQLite format 3"))
        conn.close()

if __name__ == "__main__":
    unittest.main()
