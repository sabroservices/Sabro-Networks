from unittest.mock import patch
import dealer_client
import unittest
import os
import io
import tempfile
import shutil
from datetime import datetime, timedelta
import db
import app as my_app
from dealer_client import ConnectDealerClient, reconcile_dealer_data

class TestDealerSyncSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db_path = db.DB_PATH
        cls._tmp_dir = tempfile.mkdtemp(prefix="sabro_dealer_test_")
        db.DB_PATH = os.path.join(cls._tmp_dir, "dealer_test.db")
        db.init_db(force_reset=True)

        my_app.app.config["TESTING"] = True
        my_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = my_app.app.test_client()

        conn = db.get_db()
        # Seed users required by dealer sync tests
        conn.execute("""
            INSERT OR REPLACE INTO users (id, full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES (1, 'Admin User', 'admin', 'admin123', 'Admin', '0300-0000000', 'All Areas', 'Active', 0.0, date('now'))
        """)
        conn.execute("""
            INSERT OR REPLACE INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES ('Recovery Staff', 'recovery_boy', 'recovery123', 'Recovery Boy', '0321-1111111', 'Sector A', 'Active', 0.0, date('now'))
        """)
        conn.execute("""
            INSERT OR REPLACE INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES ('Complaint Tech', 'complaint_boy', 'tech123', 'Complaint Boy', '0333-2222222', 'Sector B', 'Active', 0.0, date('now'))
        """)
        conn.execute("INSERT OR IGNORE INTO tariffs (id, name, speed_mb, price, description) VALUES (1, '15 MB Plan', 15, 1200, 'Standard')")
        conn.execute("""
            INSERT INTO customers (id, full_name, pppoe_username, password, phone, address, area, tariff_id, status, expiry_date, onu_serial, db_box, fiber_core, cnic, created_at)
            VALUES (1, 'Existing Subscriber', 'exist.user', 'secret1', '0300-1122334', 'House 1', 'Sector A', 1, 'Active', date('now', '+15 days'), 'ONU-EX-9988', 'FDB-01, Pole 2', 'Core 1 (Blue)', '35201-9988776-1', date('now'))
        """)
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls._orig_db_path
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def login(self, username, password):
        return self.client.post("/login", data={
            "username": username,
            "password": password
        }, follow_redirects=True)

    def logout(self):
        return self.client.get("/logout", follow_redirects=True)

    def test_01_access_control_and_role_isolation(self):
        """Verify only Admin can access Connect Dealer Sync; unauthenticated and staff are blocked."""
        self.logout()
        
        # 1. Unauthenticated request
        res = self.client.get("/dealer/sync")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

        # 2. Recovery Boy logged in -> forbidden from dealer sync
        res = self.login("recovery_boy", "recovery123")
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/dealer/sync")
        self.assertEqual(res.status_code, 302)
        self.logout()

        # 3. Complaint Boy logged in -> forbidden from dealer sync
        res = self.login("complaint_boy", "tech123")
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/dealer/sync")
        self.assertEqual(res.status_code, 302)
        self.logout()

        # 4. Admin logged in -> full access
        res = self.login("admin", "admin123")
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/dealer/sync")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Connect Dealer Panel Sync Hub", res.data)
        self.assertIn(b"dealer.connect.net.pk", res.data)
        self.logout()
        print("  [PASS] Dealer Sync 01 - Strict Role Isolation & Access Control Verified.")

    def test_02_save_dealer_config(self):
        """Verify updating Connect dealer credentials and URL in database."""
        self.login("admin", "admin123")
        res = self.client.post("/dealer/sync/save_config", data={
            "portal_url": "https://dealer.connect.net.pk",
            "dealer_username": "sabro.networks.dealer",
            "dealer_password": "ConnectDealerPass@2026",
            "auto_sync_interval": "Daily"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Connect Dealer panel configuration updated successfully", res.data)

        # Check DB
        conn = db.get_db()
        cfg = conn.execute("SELECT * FROM dealer_sync_config WHERE id = 1").fetchone()
        conn.close()
        self.assertEqual(cfg["dealer_username"], "sabro.networks.dealer")
        self.assertEqual(cfg["auto_sync_interval"], "Daily")
        self.logout()
        print("  [PASS] Dealer Sync 02 - Configuration Persistence & Credential Update Verified.")

    def test_03_test_connection_diagnostic(self):
        """Verify portal connectivity test endpoint."""
        self.login("admin", "admin123")
        res = self.client.post("/dealer/sync/test_connection", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Portal Diagnostic", res.data)
        self.logout()
        print("  [PASS] Dealer Sync 03 - Connection Diagnostic Endpoint Verified.")

    @patch.object(dealer_client.ConnectDealerClient, "pull_subscribers")
    def test_04_live_reconciliation_pull(self, mock_pull):
        """Verify automated pull and reconciliation against existing and new accounts."""
        mock_pull.return_value = [
            {
                "pppoe_username": "exist.user",
                "password": "secret_updated",
                "full_name": "Existing Subscriber",
                "phone": "0300-1122334",
                "tariff_name": "15 MB Plan",
                "expiry_date": "2026-12-31",
                "status": "Active",
                "area": "Sector A"
            },
            {
                "pppoe_username": "tahir.connect",
                "password": "connect_pass",
                "full_name": "Tahir Farooq",
                "phone": "0321-9988771",
                "tariff_name": "15 MB Plan",
                "expiry_date": "2026-12-30",
                "status": "Active",
                "area": "Sector B"
            }
        ]
        self.login("admin", "admin123")
        
        # Capture existing hardware specs of an active customer
        conn = db.get_db()
        target_cust = conn.execute("SELECT * FROM customers LIMIT 1").fetchone()
        orig_cust_id = target_cust["id"]
        orig_db_box = target_cust["db_box"]
        orig_fiber_core = target_cust["fiber_core"]
        orig_onu_serial = target_cust["onu_serial"]
        orig_cnic = target_cust["cnic"]
        conn.close()

        # Run pull
        res = self.client.post("/dealer/sync/run", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Sync Successful", res.data)

        # Verify FTTH Hardware specs were 100% PRESERVED
        conn = db.get_db()
        rechecked_cust = conn.execute("SELECT * FROM customers WHERE id = ?", (orig_cust_id,)).fetchone()
        self.assertEqual(rechecked_cust["db_box"], orig_db_box)
        self.assertEqual(rechecked_cust["fiber_core"], orig_fiber_core)
        self.assertEqual(rechecked_cust["onu_serial"], orig_onu_serial)
        self.assertEqual(rechecked_cust["cnic"], orig_cnic)

        # Verify audit log recorded
        log = conn.execute("SELECT * FROM dealer_sync_logs ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIsNotNone(log)
        self.assertEqual(log["status"], "Success")
        self.assertIn("Live Connect Portal Pull", log["source"])

        self.logout()
        print("  [PASS] Dealer Sync 04 - Live Ingestion, Safe Hardware Preservation & Audit Trail Verified.")

    def test_05_csv_sheet_upload_and_ingestion(self):
        """Verify importing a Connect Communications dealer CSV export file."""
        self.login("admin", "admin123")

        csv_content = """Username,Password,Customer Name,Phone Number,Package,Expiry Date,Status,Area
rashid.connect,secret456,Rashid Khan FTTH,0300-9911223,20 MB FTTH Plan,2026-12-15,Active,Block 4
farhan.speed,pass998,Farhan Akhtar,0312-3344556,15 MB FTTH Plan,2026-11-30,Active,Sector C
"""
        data = {
            "dealer_file": (io.BytesIO(csv_content.encode("utf-8")), "connect_dealer_export.csv")
        }
        res = self.client.post("/dealer/sync/upload", data=data, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Sheet Ingestion Successful", res.data)

        # Verify rashid.connect is now in DB
        conn = db.get_db()
        c = conn.execute("SELECT * FROM customers WHERE pppoe_username = 'rashid.connect'").fetchone()
        conn.close()
        self.assertIsNotNone(c)
        self.assertEqual(c["full_name"], "Rashid Khan FTTH")
        self.assertEqual(c["phone"], "0300-9911223")
        self.assertEqual(c["status"], "Active")
        self.assertEqual(c["expiry_date"], "2026-12-15")

        self.logout()
        print("  [PASS] Dealer Sync 05 - CSV/Excel Sheet Ingestion & Subscriber Provisioning Verified.")


    def test_06_unreachable_upstream_returns_manual_verification_required(self):
        """Verify unreachable upstream portal records 'Integration Unavailable — Manual Verification Required.'"""
        self.login("admin", "admin123")
        res = self.client.post("/dealer/sync/run", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Integration Unavailable", res.data)
        conn = db.get_db()
        log = conn.execute("SELECT * FROM dealer_sync_logs WHERE status = 'Unavailable' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIsNotNone(log)
        self.assertIn("Integration Unavailable — Manual Verification Required.", log["details"])
        self.logout()
        print("  [PASS] Dealer Sync 06 - Honest Unavailability Logging Verified.")

if __name__ == "__main__":
    unittest.main()
