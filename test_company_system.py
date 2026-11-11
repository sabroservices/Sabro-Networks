import unittest
import os
import time
import db
import app as my_app

import shutil
import tempfile

class TestCompanySystemSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db_path = db.DB_PATH
        cls._tmp_dir = tempfile.mkdtemp(prefix="sabro_comp_test_")
        db.DB_PATH = os.path.join(cls._tmp_dir, "company_test.db")
        db.init_db(force_reset=True)

        my_app.app.config["TESTING"] = True
        my_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = my_app.app.test_client()

        conn = db.get_db()
        conn.execute("INSERT INTO tariffs (name, speed_mb, price) VALUES ('15 MB', 15, 1200)")
        conn.execute("""
            INSERT INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES ('Comp Tech', 'comp.tech', 'techpw1', 'Complaint Boy', '0301-9988776', 'Sector A', 'Active', 0, date('now'))
        """)
        conn.execute("""
            INSERT INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES ('Comp Rec', 'comp.rec', 'recpw1', 'Recovery Boy', '0321-9988776', 'Sector A', 'Active', 0, date('now'))
        """)
        conn.execute("""
            INSERT INTO customers (full_name, pppoe_username, password, phone, address, area, tariff_id, status, expiry_date, created_at)
            VALUES ('Company Test Sub', 'comp.sub', 'pw1', '0300-2223344', 'Street 1', 'Sector A', 1, 'Active', date('now', '+20 days'), date('now'))
        """)
        conn.execute("""
            INSERT INTO invoices (invoice_number, customer_id, amount, month_period, status, due_date, created_at)
            VALUES ('INV-COMP-1', 1, 1200, 'November 2026', 'Unpaid', date('now', '+5 days'), date('now'))
        """)
        conn.commit()
        conn.close()

        cls.admin_user = "ahmedbaloch"
        cls.admin_pass = "adminadmin1"
        cls.rec_user = "comp.rec"
        cls.rec_pass = "recpw1"
        cls.tech_user = "comp.tech"
        cls.tech_pass = "techpw1"

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

    def test_01_dashboard_strictly_focused_on_complaints(self):
        """Verify Admin dashboard strictly shows complaints tickets only, without financial or dealer clutter."""
        self.login(self.admin_user, self.admin_pass)
        
        # 1. Admin dashboard shows Complaints tickets queue and complaints metrics
        res_dash = self.client.get("/")
        self.assertEqual(res_dash.status_code, 200)
        html_dash = res_dash.get_data(as_text=True)
        self.assertIn("Complaints Center", html_dash)
        self.assertIn("Active FTTH Subscriber Complaints Queue", html_dash)
        self.assertIn("Critical Outages", html_dash)
        self.assertIn("Open Complaints", html_dash)
        self.assertIn("In Progress (Field)", html_dash)

        # 2. Verify no financial charts, invoices or expenses tables on the dashboard
        self.assertNotIn("Recent Billing Invoices (Paid & Unpaid)", html_dash)
        self.assertNotIn("Recent Expenses (Kharcha)", html_dash)
        self.assertNotIn("id=\"adminDefaultersHub\"", html_dash)
        self.assertNotIn("id=\"tariffChart\"", html_dash)

        # 3. Dedicated Defaulters Desk ("Who Has Not Given Money") is accessed via /invoices?status=Unpaid
        res_unpaid = self.client.get("/invoices?status=Unpaid")
        self.assertEqual(res_unpaid.status_code, 200)
        html_unpaid = res_unpaid.get_data(as_text=True)
        self.assertIn("Who Has Not Given Money (Unpaid Defaulters Desk)", html_unpaid)

        # 4. Test 1-click Pay for an unpaid invoice
        conn = db.get_db()
        unpaid_inv = conn.execute("SELECT id, customer_id, amount FROM invoices WHERE status = 'Unpaid' LIMIT 1").fetchone()
        conn.close()

        if unpaid_inv:
            inv_id = unpaid_inv["id"]
            res_pay = self.client.post(f"/invoices/pay/{inv_id}", data={
                "payment_method": "Cash"
            }, follow_redirects=True)
            self.assertEqual(res_pay.status_code, 200)
            self.assertIn("PAID", res_pay.get_data(as_text=True))

        self.logout()
        print("  [PASS] Company System 01 - Dashboard Strictly Displays Complaints Tickets Only.")

    def test_02_assign_complaint_to_complaint_boy(self):
        """Verify Admin assigning each complaint ticket to a Complaint Boy."""
        self.login(self.admin_user, self.admin_pass)

        conn = db.get_db()
        tech = conn.execute("SELECT id, full_name, username FROM users WHERE role = 'Complaint Boy' LIMIT 1").fetchone()
        tech_id = tech["id"]
        tech_name = tech["full_name"]

        ticket = conn.execute("SELECT id, ticket_number FROM tickets WHERE status = 'Open' LIMIT 1").fetchone()
        if not ticket:
            cust = conn.execute("SELECT id FROM customers LIMIT 1").fetchone()
            unique_tck_num = f"TCK-TEST-{int(time.time() * 1000) % 100000}"
            conn.execute("""
                INSERT INTO tickets (ticket_number, customer_id, subject, details, priority, status, created_at)
                VALUES (?, ?, 'Fiber LOS Red Light', 'Customer has red LOS', 'High', 'Open', datetime('now'))
            """, (unique_tck_num, cust["id"]))
            conn.commit()
            ticket = conn.execute("SELECT id, ticket_number FROM tickets WHERE ticket_number = ?", (unique_tck_num,)).fetchone()

        ticket_id = ticket["id"]
        conn.close()

        # Admin assigns ticket to technician
        res_assign = self.client.post(f"/tickets/assign/{ticket_id}", data={
            "assigned_user_id": tech_id
        }, follow_redirects=True)
        self.assertEqual(res_assign.status_code, 200)
        self.assertIn(f"assigned to {tech_name}", res_assign.get_data(as_text=True))

        # Check in DB: status moved to 'In Progress' and assigned_user_id set
        conn = db.get_db()
        assigned_tck = conn.execute("SELECT assigned_user_id, status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        conn.close()
        self.assertEqual(assigned_tck["assigned_user_id"], tech_id)
        self.assertEqual(assigned_tck["status"], "In Progress")

        self.logout()

        # Now Complaint Boy logs in and sees ticket on their dashboard
        res_tech_login = self.login(self.tech_user, self.tech_pass)
        self.assertEqual(res_tech_login.status_code, 200)

        res_tech_dash = self.client.get("/")
        self.assertEqual(res_tech_dash.status_code, 200)
        tech_dash_html = res_tech_dash.get_data(as_text=True)
        self.assertIn("Technician Desk", tech_dash_html)
        self.assertIn(ticket["ticket_number"], tech_dash_html)

        # Complaint Boy marks ticket Resolved
        res_resolve = self.client.post(f"/tickets/edit/{ticket_id}", data={
            "subject": "Fiber LOS Red Light",
            "details": "Drop wire repaired",
            "priority": "High",
            "status": "Resolved",
            "assigned_user_id": tech_id,
            "resolution_notes": "Cleaned optical connector and verified signal at -19 dBm."
        }, follow_redirects=True)
        self.assertEqual(res_resolve.status_code, 200)

        # Verify ticket is Resolved in DB
        conn = db.get_db()
        resolved_tck = conn.execute("SELECT status, resolution_notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        conn.close()
        self.assertEqual(resolved_tck["status"], "Resolved")
        self.assertIn("Cleaned optical connector", resolved_tck["resolution_notes"])

        self.logout()
        print("  [PASS] Company System 02 - Direct Complaint Assignment to Complaint Boy & Resolution Verified.")

    def test_03_sober_clean_ui_no_dealer_or_mikrotik_clutter(self):
        """Verify UI is clean, elegant, and Connect Dealer Sync & MikroTik are removed from sidebar."""
        self.login(self.admin_user, self.admin_pass)

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Verify Connect Dealer Sync is NOT in sidebar navigation
        self.assertNotIn("Connect Dealer Sync", html)

        # Verify MikroTik RouterOS is NOT in sidebar navigation
        self.assertNotIn('<i class="bi bi-router-fill"></i> MikroTik RouterOS', html)
        self.assertNotIn('Network & Optical Core', html)

        # Verify no laser streamer animation line
        self.assertNotIn('<div class="fiber-laser-streamer"', html)

        # Verify sober corporate theme classes
        self.assertIn('btn-orange', html)
        self.assertIn('table-card', html)

        self.logout()
        print("  [PASS] Company System 03 - Dealer Sync & MikroTik Removed from Navigation Verified.")

    def test_04_dedicated_dashboards_role_isolation(self):
        """Verify each role has their dedicated dashboard with strict role isolation."""
        # 1. Recovery Boy Dashboard: Has field dues to collect, NO complaints clutter, NO admin config
        self.login(self.rec_user, self.rec_pass)
        res_rec = self.client.get("/")
        self.assertEqual(res_rec.status_code, 200)
        rec_html = res_rec.get_data(as_text=True)
        self.assertIn("Recovery Desk", rec_html)
        self.assertIn("Pending Field Dues", rec_html)
        self.assertNotIn("Complaints Center", rec_html)

        # Blocked from settings
        res_set = self.client.get("/settings")
        self.assertEqual(res_set.status_code, 302)
        self.logout()

        # 2. Complaint Boy Dashboard: Has technician desk, NO billing or financial amounts
        self.login(self.tech_user, self.tech_pass)
        res_cmp = self.client.get("/")
        self.assertEqual(res_cmp.status_code, 200)
        cmp_html = res_cmp.get_data(as_text=True)
        self.assertIn("Technician Desk", cmp_html)
        self.assertNotIn("Pending Field Dues", cmp_html)
        self.assertNotIn("Net Cash Profit", cmp_html)

        # Blocked from invoices
        res_inv = self.client.get("/invoices")
        self.assertEqual(res_inv.status_code, 302)
        self.logout()

        # 3. Admin: Complaints Queue
        self.login(self.admin_user, self.admin_pass)
        res_adm = self.client.get("/")
        self.assertEqual(res_adm.status_code, 200)
        adm_html = res_adm.get_data(as_text=True)
        self.assertIn("Active FTTH Subscriber Complaints Queue", adm_html)

        res_adm_set = self.client.get("/settings")
        self.assertEqual(res_adm_set.status_code, 200)
        self.logout()
        print("  [PASS] Company System 04 - Multi-Dashboard Role Isolation & Access Boundaries Verified.")

if __name__ == "__main__":
    unittest.main()
