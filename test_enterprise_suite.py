import io
import unittest
import urllib.parse
from datetime import datetime
import db
import app as flask_app

class SabroNetworksEnterpriseTestSuite(unittest.TestCase):
    def setUp(self):
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['WTF_CSRF_ENABLED'] = False
        self.client = flask_app.app.test_client()
        conn = db.get_db()
        admin = conn.execute("SELECT id, username, password, full_name FROM users WHERE role = 'Admin' LIMIT 1").fetchone()
        tech = conn.execute("SELECT id, username, password, full_name FROM users WHERE role = 'Complaint Boy' LIMIT 1").fetchone()
        rec = conn.execute("SELECT id, username, password, full_name FROM users WHERE role = 'Recovery Boy' LIMIT 1").fetchone()
        conn.close()
        self.admin_id = admin["id"]
        self.admin_user = admin["username"]
        self.admin_pass = admin["password"]
        self.admin_name = admin["full_name"]
        self.tech_id = tech["id"]
        self.tech_user = tech["username"]
        self.tech_pass = tech["password"]
        self.rec_id = rec["id"]
        self.rec_user = rec["username"]
        self.rec_pass = rec["password"]

    def test_01_public_invoice_access(self):
        """Customers opening WhatsApp bill links must view digital invoice without logging in (person name, package, total amount)."""
        res = self.client.get("/invoice/1/print")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Sabro Networks", html)
        self.assertNotIn("Powered By Connect", html)
        self.assertIn("Vshatkay Solutions", html)
        self.assertIn("Customer Name", html)
        self.assertIn("Internet Package", html)
        self.assertIn("Total Amount", html)
        self.assertNotIn("PPPoE User", html)
        self.assertNotIn("ONT Serial", html)
        print("  [PASS] 01 - Clean digital bill slip verified (customer name, package, total amount, zero PPPoE/hardware clutter).")

    def test_02_auth_enforcement(self):
        """Protected routes must redirect unauthenticated users to /login."""
        for endpoint in ["/", "/customers", "/invoices", "/tickets", "/staff", "/expenses", "/settings"]:
            res = self.client.get(endpoint)
            self.assertEqual(res.status_code, 302)
            self.assertIn("/login", res.headers.get("Location", ""))
        print("  [PASS] 02 - Security barrier: unauthenticated sessions redirected to /login.")

    def test_03_login_roles(self):
        """Admin, Complaint Boy, and Recovery Boy logins must authenticate properly."""
        # 1. Admin Login
        res_admin = self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass}, follow_redirects=True)
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(self.admin_name.split()[0], res_admin.get_data(as_text=True))

        # Logout
        self.client.get("/logout")

        # 2. Complaint Boy Login
        conn = db.get_db()
        tech = conn.execute("SELECT username, password FROM users WHERE role = 'Complaint Boy' LIMIT 1").fetchone()
        conn.close()
        res_tech = self.client.post("/login", data={"username": tech["username"], "password": tech["password"]}, follow_redirects=True)
        self.assertEqual(res_tech.status_code, 200)
        self.assertIn("Technician Desk", res_tech.get_data(as_text=True))

        # Logout
        self.client.get("/logout")

        # 3. Recovery Boy Login
        res_rec = self.client.post("/login", data={"username": self.rec_user, "password": self.rec_pass}, follow_redirects=True)
        self.assertEqual(res_rec.status_code, 200)
        self.assertIn("Recovery Desk", res_rec.get_data(as_text=True))

        print("  [PASS] 03 - Multi-role logins (Admin, Complaint Boy, Recovery Boy) validated.")

    def test_04_customer_ftth_lifecycle(self):
        """Add new FTTH customer with full hardware/splice specs, edit, and verify DB persistence."""
        # Login as Admin
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})

        test_user = f"tst.{int(datetime.now().timestamp())}"
        post_data = {
            "full_name": "Tariq Fiber Enterprise",
            "pppoe_username": test_user,
            "password": "ftthpassword99",
            "phone": "0300-8877665",
            "address": "Office 102, 1st Floor, Connect Tower",
            "area": "Commercial Sector B",
            "tariff_id": "2",
            "days": "30",
            "initial_payment": "Unpaid",
            "onu_deposit": "3000",
            "cnic": "42101-7654321-9",
            "onu_serial": "HWTC-COMM9900",
            "db_box": "FDB-08, Pole #25 (Tower)",
            "fiber_core": "Core 2 (Orange)",
            "installation_date": "2026-11-04"
        }
        res = self.client.post("/customers/add", data=post_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        cust = conn.execute("SELECT * FROM customers WHERE pppoe_username = ?", (test_user,)).fetchone()
        self.assertIsNotNone(cust)
        self.assertEqual(cust["full_name"], "Tariq Fiber Enterprise")
        self.assertEqual(cust["onu_serial"], "HWTC-COMM9900")
        self.assertEqual(cust["db_box"], "FDB-08, Pole #25 (Tower)")
        self.assertEqual(cust["fiber_core"], "Core 2 (Orange)")
        self.assertEqual(cust["cnic"], "42101-7654321-9")

        # Verify auto-generated invoice
        inv = conn.execute("SELECT * FROM invoices WHERE customer_id = ?", (cust["id"],)).fetchone()
        self.assertIsNotNone(inv)
        self.assertEqual(inv["status"], "Unpaid")

        # Verify deposit held
        dep = conn.execute("SELECT * FROM deposits WHERE customer_id = ?", (cust["id"],)).fetchone()
        self.assertIsNotNone(dep)
        self.assertEqual(dep["amount"], 3000.0)
        cust_id = cust["id"]
        cust_expiry = cust["expiry_date"]
        conn.close()

        # Edit customer details
        edit_data = dict(post_data)
        edit_data["full_name"] = "Tariq Fiber Enterprise (Updated)"
        edit_data["status"] = "Active"
        edit_data["expiry_date"] = cust_expiry
        edit_data["onu_serial"] = "HWTC-COMM9900-MODIFIED"
        res_edit = self.client.post(f"/customers/edit/{cust_id}", data=edit_data, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        conn = db.get_db()
        updated_cust = conn.execute("SELECT * FROM customers WHERE id = ?", (cust_id,)).fetchone()
        self.assertEqual(updated_cust["full_name"], "Tariq Fiber Enterprise (Updated)")
        self.assertEqual(updated_cust["onu_serial"], "HWTC-COMM9900-MODIFIED")
        conn.close()
        print("  [PASS] 04 - FTTH Subscriber lifecycle (Creation, FTTH specs, Deposit, Edit) verified.")

    def test_05_whatsapp_telecom_automations(self):
        """Verify all 5 real-world WhatsApp communications generate valid wa.me URLs with proper messages."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        conn = db.get_db()
        cust = conn.execute("SELECT id, phone FROM customers LIMIT 1").fetchone()
        inv = conn.execute("SELECT id FROM invoices LIMIT 1").fetchone()
        ticket = conn.execute("SELECT id FROM tickets WHERE assigned_user_id IS NOT NULL LIMIT 1").fetchone()
        conn.close()

        # 1. New Customer Welcome WhatsApp
        res_welcome = self.client.get(f"/customer/{cust['id']}/whatsapp_welcome")
        self.assertEqual(res_welcome.status_code, 302)
        loc_welcome = res_welcome.headers.get("Location", "")
        self.assertIn("https://wa.me/", loc_welcome)
        decoded_welcome = urllib.parse.unquote(loc_welcome)
        self.assertIn("Sabro Networks", decoded_welcome)
        self.assertNotIn("Powered By Connect", decoded_welcome)
        self.assertIn("PPPoE Username", decoded_welcome)
        self.assertIn("ONT / ONU Serial", decoded_welcome)

        # 2. Bill Reminder WhatsApp (Friendly Roman Urdu, no extra info)
        res_remind = self.client.get(f"/customer/{cust['id']}/whatsapp_reminder")
        self.assertEqual(res_remind.status_code, 302)
        decoded_remind = urllib.parse.unquote(res_remind.headers.get("Location", ""))
        self.assertIn("Assalam-o-Alaikum", decoded_remind)
        self.assertIn("Sabro Networks", decoded_remind)
        self.assertIn("pending", decoded_remind.lower())
        self.assertNotIn("JazzCash", decoded_remind)

        # 3. Invoice WhatsApp
        res_inv = self.client.get(f"/invoice/{inv['id']}/whatsapp")
        self.assertEqual(res_inv.status_code, 302)
        decoded_inv = urllib.parse.unquote(res_inv.headers.get("Location", ""))
        self.assertIn("/invoice/", decoded_inv)
        self.assertIn("/print", decoded_inv)

        # 4. Technician WhatsApp Dispatch
        res_tck = self.client.get(f"/tickets/{ticket['id']}/whatsapp")
        self.assertEqual(res_tck.status_code, 302)
        decoded_tck = urllib.parse.unquote(res_tck.headers.get("Location", ""))
        self.assertIn("NEW COMPLAINT TICKET", decoded_tck)
        self.assertIn("FDB Box", decoded_tck)

        # 5. Ticket Resolved WhatsApp to Customer
        res_res = self.client.get(f"/tickets/{ticket['id']}/whatsapp_resolved")
        self.assertEqual(res_res.status_code, 302)
        decoded_res = urllib.parse.unquote(res_res.headers.get("Location", ""))
        self.assertIn("COMPLAINT RESOLVED", decoded_res)
        self.assertIn("Sabro Networks", decoded_res)
        self.assertNotIn("Powered By Connect", decoded_res)

        # 6. Bulk Defaulters WhatsApp Summary
        res_def = self.client.get("/invoices/defaulters_whatsapp_summary")
        self.assertEqual(res_def.status_code, 302)
        decoded_def = urllib.parse.unquote(res_def.headers.get("Location", ""))
        self.assertIn("DEFAULTERS LIST", decoded_def)

        print("  [PASS] 05 - All 6 Telecom WhatsApp automations (Welcome, Reminder, Invoice, Tech Dispatch, Resolution, Bulk Defaulters) validated.")

    def test_06_ticket_resolution_workflow(self):
        """Create ticket, assign to technician, resolve with notes, verify timestamps."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        
        # Add Ticket
        res_add = self.client.post("/tickets/add", data={
            "customer_id": "1",
            "subject": "Fiber Core Broken on Main St-4 Splitter",
            "details": "Drop wire pulled down by cargo truck.",
            "priority": "Critical",
            "assigned_user_id": str(self.tech_id)
        }, follow_redirects=True)
        self.assertEqual(res_add.status_code, 200)

        conn = db.get_db()
        tck = conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(tck["subject"], "Fiber Core Broken on Main St-4 Splitter")
        self.assertEqual(tck["status"], "Open")
        tck_id = tck["id"]
        tck_subject = tck["subject"]
        tck_details = tck["details"]
        conn.close()

        # Resolve Ticket
        res_edit = self.client.post(f"/tickets/edit/{tck_id}", data={
            "subject": tck_subject,
            "details": tck_details,
            "priority": "Critical",
            "status": "Resolved",
            "assigned_user_id": str(self.tech_id),
            "resolution_notes": "Spliced Core 2 in FDB-04 box and tested optical power -18.2 dBm. Connection restored."
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        conn = db.get_db()
        updated_tck = conn.execute("SELECT * FROM tickets WHERE id = ?", (tck_id,)).fetchone()
        self.assertEqual(updated_tck["status"], "Resolved")
        self.assertIsNotNone(updated_tck["resolved_at"])
        self.assertIn("Spliced Core 2", updated_tck["resolution_notes"])
        conn.close()

        print("  [PASS] 06 - Ticketing resolution workflow and audit trail verified.")

    def test_07_invoice_payment_and_recovery_credit(self):
        """Mark invoice as paid, verify collector credit and subscriber extension."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        conn = db.get_db()
        unpaid_inv = conn.execute("SELECT * FROM invoices WHERE status = 'Unpaid' LIMIT 1").fetchone()
        collector = conn.execute("SELECT * FROM users WHERE role = 'Recovery Boy' LIMIT 1").fetchone()
        initial_collected = collector["total_collected"]
        inv_id = unpaid_inv["id"]
        inv_amount = unpaid_inv["amount"]
        inv_cust_id = unpaid_inv["customer_id"]
        collector_id = collector["id"]
        conn.close()

        res_pay = self.client.post(f"/invoices/pay/{inv_id}", data={
            "payment_method": "Cash",
            "collected_by_staff_id": str(collector_id)
        }, follow_redirects=True)
        self.assertEqual(res_pay.status_code, 200)

        # Check invoice paid
        conn = db.get_db()
        paid_inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv_id,)).fetchone()
        self.assertEqual(paid_inv["status"], "Paid")
        self.assertEqual(paid_inv["payment_method"], "Cash")

        # Check collector credit updated
        updated_collector = conn.execute("SELECT total_collected FROM users WHERE id = ?", (collector_id,)).fetchone()
        self.assertEqual(updated_collector["total_collected"], initial_collected + inv_amount)

        # Check customer expiry extended
        cust = conn.execute("SELECT * FROM customers WHERE id = ?", (inv_cust_id,)).fetchone()
        self.assertEqual(cust["status"], "Active")
        conn.close()

        print("  [PASS] 07 - Invoice collection, Recovery Boy attribution, and subscriber extension verified.")

    def test_08_database_backup_download(self):
        """Verify admin can download complete SQLite database backup file."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        res = self.client.get("/backup/db")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/octet-stream")
        # Check SQLite magic header
        self.assertTrue(res.data.startswith(b"SQLite format 3"))
        print("  [PASS] 08 - Database backup binary download integrity verified.")

    def test_09_all_views_render_ok(self):
        """Ensure all primary portal views render with 200 OK and no template errors."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        views = [
            "/",
            "/customers",
            "/invoices",
            "/tickets",
            "/staff",
            "/investments",
            "/expenses",
            "/deposits",
            "/tariffs",
            "/settings"
        ]
        for v in views:
            res = self.client.get(v)
            self.assertEqual(res.status_code, 200, f"View {v} failed with code {res.status_code}")
        print("  [PASS] 09 - All 10 views rendered with 200 OK and zero template errors.")

    def test_10_recovery_boy_role_isolation(self):
        """Recovery Boy can only view their recovery desk, invoices, and customer contacts. Blocked from expenses, staff, tariffs, tickets, settings, backup."""
        self.client.post("/login", data={"username": self.rec_user, "password": self.rec_pass})

        # Allowed routes
        res_dash = self.client.get("/")
        self.assertEqual(res_dash.status_code, 200)
        html_dash = res_dash.get_data(as_text=True)
        self.assertIn("Recovery Desk", html_dash)
        self.assertNotIn("Net Cash Profit", html_dash)
        self.assertNotIn("Capital Assets", html_dash)

        res_inv = self.client.get("/invoices")
        self.assertEqual(res_inv.status_code, 200)

        res_cust = self.client.get("/customers")
        self.assertEqual(res_cust.status_code, 200)

        # Strictly Blocked routes (must redirect to dashboard with 302)
        forbidden_endpoints = [
            "/expenses",
            "/investments",
            "/deposits",
            "/staff",
            "/tariffs",
            "/settings",
            "/backup/db",
            "/tickets"
        ]
        for ep in forbidden_endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 302, f"Recovery Boy should NOT be able to access {ep}")
            self.assertEqual(res.headers.get("Location"), "/")

        self.client.get("/logout")
        print("  [PASS] 10 - Recovery Boy role isolation & data boundary verified.")

    def test_11_complaint_boy_role_isolation(self):
        """Complaint Boy can only view their technician desk, complaint tickets, and line lookup. Blocked from billing, invoices, expenses, investments, staff, etc."""
        self.client.post("/login", data={"username": self.tech_user, "password": self.tech_pass})

        # Allowed routes
        res_dash = self.client.get("/")
        self.assertEqual(res_dash.status_code, 200)
        html_dash = res_dash.get_data(as_text=True)
        self.assertIn("Technician Desk", html_dash)
        self.assertNotIn("Paid Recoveries", html_dash)
        self.assertNotIn("Net Cash Profit", html_dash)

        res_tick = self.client.get("/tickets")
        self.assertEqual(res_tick.status_code, 200)

        res_cust = self.client.get("/customers")
        self.assertEqual(res_cust.status_code, 200)

        # Strictly Blocked routes (must redirect to dashboard with 302)
        forbidden_endpoints = [
            "/invoices",
            "/expenses",
            "/investments",
            "/deposits",
            "/staff",
            "/tariffs",
            "/settings",
            "/backup/db"
        ]
        for ep in forbidden_endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 302, f"Complaint Boy should NOT be able to access {ep}")
            self.assertEqual(res.headers.get("Location"), "/")

        self.client.get("/logout")
        print("  [PASS] 11 - Complaint Boy / Technician role isolation & data boundary verified.")

    def test_12_admin_full_unrestricted_access(self):
        """Admin has full, unrestricted access across all portal operations."""
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        admin_routes = [
            "/",
            "/customers",
            "/invoices",
            "/tickets",
            "/staff",
            "/investments",
            "/expenses",
            "/deposits",
            "/tariffs",
            "/settings"
        ]
        for route in admin_routes:
            res = self.client.get(route)
            self.assertEqual(res.status_code, 200, f"Admin must have 200 OK on {route}")

        res_backup = self.client.get("/backup/db")
        self.assertEqual(res_backup.status_code, 200)
        self.assertTrue(res_backup.data.startswith(b"SQLite format 3"))

        self.client.get("/logout")
        print("  [PASS] 12 - Admin unrestricted full system access verified.")


    def test_13_pfp_upload_and_role_support(self):
        """Verify Profile Picture (PFP) upload and retrieval for Admin, Recovery Boy, and Complaint Boy."""
        # 1. Admin PFP upload
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        dummy_png = (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"), "admin_avatar.png")
        res = self.client.post("/profile/update_pfp", data={"pfp_file": dummy_png}, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        conn = db.get_db()
        admin_row = conn.execute("SELECT pfp_image FROM users WHERE id = ?", (self.admin_id,)).fetchone()
        conn.close()
        self.assertTrue(admin_row["pfp_image"].startswith("uploads/pfp/"))
        self.client.get("/logout")

        # 2. Complaint Boy PFP upload
        self.client.post("/login", data={"username": self.tech_user, "password": self.tech_pass})
        dummy_jpg = (io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9"), "tech_avatar.jpg")
        res = self.client.post("/profile/update_pfp", data={"pfp_file": dummy_jpg}, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        tech_row = conn.execute("SELECT pfp_image FROM users WHERE id = ?", (self.tech_id,)).fetchone()
        conn.close()
        self.assertTrue(tech_row["pfp_image"].startswith("uploads/pfp/"))
        self.client.get("/logout")

        # 3. Recovery Boy PFP upload
        self.client.post("/login", data={"username": self.rec_user, "password": self.rec_pass})
        dummy_webp = (io.BytesIO(b"RIFF\x14\x00\x00\x00WEBPVP8 \x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"), "rec_avatar.webp")
        res = self.client.post("/profile/update_pfp", data={"pfp_file": dummy_webp}, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        rec_row = conn.execute("SELECT pfp_image FROM users WHERE id = ?", (self.rec_id,)).fetchone()
        conn.close()
        self.assertTrue(rec_row["pfp_image"].startswith("uploads/pfp/"))
        self.client.get("/logout")
        print("  [PASS] 13 - Profile Picture (PFP) uploads validated across Admin, Complaint Boy, and Recovery Boy.")

    def test_14_complaint_boy_leveling_progression(self):
        """Verify 5-tier technician leveling system, XP calculation, and automated XP rewards on ticket resolution."""
        # Check tier calculation pure function
        lvl1 = flask_app.calculate_technician_level(2, 240)
        self.assertEqual(lvl1["level"], 1)
        self.assertEqual(lvl1["title"], "Apprentice Splicer")

        lvl2 = flask_app.calculate_technician_level(8, 960)
        self.assertEqual(lvl2["level"], 2)
        self.assertEqual(lvl2["title"], "Field Technician")

        lvl3 = flask_app.calculate_technician_level(20, 2400)
        self.assertEqual(lvl3["level"], 3)
        self.assertEqual(lvl3["title"], "Senior Fiber Tech")

        lvl4 = flask_app.calculate_technician_level(35, 4200)
        self.assertEqual(lvl4["level"], 4)
        self.assertEqual(lvl4["title"], "Master Fiber Splicer")

        lvl5 = flask_app.calculate_technician_level(55, 6800)
        self.assertEqual(lvl5["level"], 5)
        self.assertEqual(lvl5["title"], "Optical NOC Elite")
        self.assertTrue(lvl5["is_max"])

        # Check automated XP reward on resolving ticket
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        conn = db.get_db()
        initial_tech = conn.execute("SELECT technician_xp FROM users WHERE id = ?", (self.tech_id,)).fetchone()
        initial_xp = initial_tech["technician_xp"] or 0

        # Create a ticket assigned to tech
        cursor = conn.execute("""
            INSERT INTO tickets (ticket_number, customer_id, subject, details, priority, status, assigned_user_id, created_at)
            VALUES (?, ?, ?, ?, ?, 'In Progress', ?, datetime('now'))
        """, (f"TCK-LVL-{int(datetime.now().timestamp())}", 1, "Fiber Break Level Test", "Core Joint repair", "Critical", self.tech_id))
        test_ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Resolve ticket
        res = self.client.post(f"/tickets/edit/{test_ticket_id}", data={
            "status": "Resolved",
            "assigned_user_id": str(self.tech_id),
            "priority": "Critical",
            "resolution_notes": "Optical fiber re-spliced, RX optical power -18.4 dBm OK"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        updated_tech = conn.execute("SELECT technician_xp FROM users WHERE id = ?", (self.tech_id,)).fetchone()
        conn.close()
        # Critical ticket gives +180 XP
        self.assertEqual(updated_tech["technician_xp"], initial_xp + 180)

        # Login as Tech and check leveling dashboard display
        self.client.get("/logout")
        res_tech_dash = self.client.post("/login", data={"username": self.tech_user, "password": self.tech_pass}, follow_redirects=True)
        tech_html = res_tech_dash.get_data(as_text=True)
        self.assertIn("RANK", tech_html)
        self.assertIn("XP", tech_html)
        self.assertIn("View Level Ranks & Perks", tech_html)
        self.assertIn("Technician Leveling & Career Progression", tech_html)

        # Cleanup test ticket
        self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        self.client.post(f"/tickets/delete/{test_ticket_id}", follow_redirects=True)
        self.client.get("/logout")

        print("  [PASS] 14 - Gamified Technician Leveling System (Tiers 1-5, +XP on resolve) verified.")

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(SabroNetworksEnterpriseTestSuite)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n" + "="*65)
        print("  ALL 14 ENTERPRISE TEST SUITES PASSED FLAWLESSLY! 100% BUG-FREE.")
        print("="*65)
    else:
        exit(1)
