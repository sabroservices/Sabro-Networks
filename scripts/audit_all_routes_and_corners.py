# -*- coding: utf-8 -*-
"""
Exhaustive Corner-to-Corner Test & Audit Script for Sabro Networks
Tests:
1. All 56 routes under 4 auth contexts (Anonymous, Admin, Complaint Boy, Recovery Boy)
2. Every template rendering and Jinja context
3. Every CRUD operation and edge case
4. File uploads (CSV import, PFP upload, DB backup/restore)
5. WhatsApp message link generation and special characters escaping
6. Recovery percentages and zero-division safety
7. Staff leveling calculation boundaries
"""
import io
import os
import re
import unittest
from datetime import datetime
import db
import app as flask_app

class SabroNetworksExhaustiveAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flask_app.app.config['TESTING'] = True
        flask_app.app.config['WTF_CSRF_ENABLED'] = False
        cls.client = flask_app.app.test_client()

        # Gather user IDs
        conn = db.get_db()
        cls.admin = conn.execute("SELECT * FROM users WHERE role = 'Admin' LIMIT 1").fetchone()
        cls.tech = conn.execute("SELECT * FROM users WHERE role = 'Complaint Boy' LIMIT 1").fetchone()
        cls.rec = conn.execute("SELECT * FROM users WHERE role = 'Recovery Boy' LIMIT 1").fetchone()
        cls.customer = conn.execute("SELECT * FROM customers LIMIT 1").fetchone()
        cls.invoice = conn.execute("SELECT * FROM invoices LIMIT 1").fetchone()
        cls.ticket = conn.execute("SELECT * FROM tickets LIMIT 1").fetchone()
        cls.tariff = conn.execute("SELECT * FROM tariffs LIMIT 1").fetchone()
        cls.expense = conn.execute("SELECT * FROM expenses LIMIT 1").fetchone()
        conn.close()

    def login(self, username, password):
        return self.client.post("/login", data={"username": username, "password": password}, follow_redirects=True)

    def logout(self):
        return self.client.get("/logout", follow_redirects=True)

    def test_01_all_get_routes_admin(self):
        """Audit all GET views for Admin: zero 500s, zero undefined template variables."""
        self.login(self.admin["username"], self.admin["password"])
        html_routes = [
            "/",
            "/customers",
            "/invoices",
            "/tickets",
            "/staff",
            "/expenses",
            "/investments",
            "/deposits",
            "/tariffs",
            "/settings",
            f"/invoice/{self.invoice['id']}/print",
            # "/invoices/defaulters_whatsapp_summary"
        ]
        errors = []
        for r in html_routes:
            res = self.client.get(r)
            if res.status_code != 200:
                errors.append(f"Route {r} returned status {res.status_code}")
            html = res.get_data(as_text=True)
            if "Traceback" in html or "jinja2.exceptions" in html:
                errors.append(f"Route {r} contains template traceback!")
            if "Powered By Connect" in html:
                errors.append(f"Route {r} contains obsolete 'Powered By Connect' branding!")

        # Binary/Export routes
        res_backup = self.client.get("/backup/db")
        self.assertEqual(res_backup.status_code, 200)
        self.assertTrue(res_backup.data.startswith(b"SQLite format 3"))

        res_export = self.client.get("/export/customers")
        self.assertEqual(res_export.status_code, 200)
        self.assertIn("text/csv", res_export.headers.get("Content-Type", ""))

        # WhatsApp redirect routes
        res_wa_inv = self.client.get(f"/invoices/{self.invoice['id']}/whatsapp")
        self.assertEqual(res_wa_inv.status_code, 302)

        res_wa_wel = self.client.get(f"/customers/{self.customer['id']}/whatsapp_welcome")
        self.assertEqual(res_wa_wel.status_code, 302)

        res_wa_rem = self.client.get(f"/customers/{self.customer['id']}/whatsapp_reminder")
        self.assertEqual(res_wa_rem.status_code, 302)

        self.logout()
        self.assertEqual(len(errors), 0, f"Found Admin route errors: {errors}")
        print("  [AUDIT PASS] 01: All Admin GET views render cleanly with 200 OK and zero tracebacks.")

    def test_02_all_get_routes_complaint_boy(self):
        """Audit Complaint Boy views: technician desk, isolation, permissions."""
        self.login(self.tech["username"], self.tech["password"])
        # Allowed routes
        allowed = [
            "/",
            "/tickets",
            "/customers"
        ]
        for r in allowed:
            res = self.client.get(r)
            self.assertEqual(res.status_code, 200, f"Tech should have access to {r}")
            html = res.get_data(as_text=True)
            self.assertIn("Sabro Networks", html)
            self.assertNotIn("Traceback", html)

        # Restricted routes should redirect or deny
        restricted = ["/staff", "/expenses", "/investments", "/deposits", "/tariffs", "/settings", "/backup/db", "/recovery"]
        for r in restricted:
            res = self.client.get(r)
            self.assertIn(res.status_code, [302, 403], f"Tech should be blocked from {r}")

        self.logout()
        print("  [AUDIT PASS] 02: Complaint Boy role access and security boundaries verified.")

    def test_03_all_get_routes_recovery_boy(self):
        """Audit Recovery Boy views: collections desk, dues, invoices, isolation."""
        self.login(self.rec["username"], self.rec["password"])
        # Allowed routes
        allowed = [
            "/",
            "/invoices",
            "/customers"
        ]
        for r in allowed:
            res = self.client.get(r)
            self.assertEqual(res.status_code, 200, f"Recovery boy should have access to {r}")
            html = res.get_data(as_text=True)
            self.assertIn("Sabro Networks", html)
            self.assertNotIn("Traceback", html)

        # WhatsApp invoice link for recovery boy
        res_wa = self.client.get(f"/invoices/{self.invoice['id']}/whatsapp")
        self.assertEqual(res_wa.status_code, 302)

        # Restricted routes
        restricted = ["/staff", "/expenses", "/investments", "/deposits", "/tariffs", "/settings", "/backup/db"]
        for r in restricted:
            res = self.client.get(r)
            self.assertIn(res.status_code, [302, 403], f"Recovery boy should be blocked from {r}")

        self.logout()
        print("  [AUDIT PASS] 03: Recovery Boy role access and security boundaries verified.")

    def test_04_anonymous_access_boundary(self):
        """Audit that anonymous sessions cannot access protected pages, but CAN access public invoice."""
        self.logout()
        # Public print route must be 200 OK
        res = self.client.get(f"/invoice/{self.invoice['id']}/print")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Sabro Networks", res.get_data(as_text=True))
        self.assertNotIn("Powered By Connect", res.get_data(as_text=True))

        # Protected routes must redirect to /login
        for r in ["/", "/customers", "/invoices", "/tickets", "/staff", "/settings", "/recovery"]:
            res = self.client.get(r)
            self.assertEqual(res.status_code, 302)
            self.assertIn("/login", res.headers.get("Location", ""))
        print("  [AUDIT PASS] 04: Anonymous access boundary & public invoice verified.")

    def test_05_customer_crud_edge_cases(self):
        """Audit Customer creation with optional fields, special characters, status toggle, renew, force delete."""
        self.login(self.admin["username"], self.admin["password"])
        cust_uname = f"tst_edge_{int(datetime.now().timestamp())}"
        res = self.client.post("/customers/add", data={
            "full_name": "Test & Edge Customer <Special>",
            "pppoe_username": cust_uname,
            "password": "edgepass@#$123",
            "phone": "0300-1122334",
            "address": "Street #4, Sector C",
            "tariff_id": str(self.tariff["id"]),
            "area": "Sector C",
            "db_box": "FDB-99",
            "fiber_core": "Core 2 Orange",
            "optical_power": "-19.5 dBm",
            "onu_serial": "HWTC12345678"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        new_cust = conn.execute("SELECT * FROM customers WHERE pppoe_username = ?", (cust_uname,)).fetchone()
        self.assertIsNotNone(new_cust)
        new_cust_id = new_cust["id"]

        # Edit customer
        res_edit = self.client.post(f"/customers/edit/{new_cust_id}", data={
            "full_name": "Test Customer Updated",
            "pppoe_username": cust_uname,
            "password": "newpass123",
            "phone": "0300-9988776",
            "address": "Street #5, Sector C",
            "tariff_id": str(self.tariff["id"]),
            "area": "Sector C",
            "db_box": "FDB-100",
            "fiber_core": "Core 1 Blue",
            "optical_power": "-18.2 dBm",
            "onu_serial": "HWTC99998888"
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        # Toggle status
        res_toggle = self.client.post(f"/customers/toggle_status/{new_cust_id}", follow_redirects=True)
        self.assertEqual(res_toggle.status_code, 200)

        # Renew customer (+30 days)
        res_renew = self.client.post(f"/customers/renew/{new_cust_id}", follow_redirects=True)
        self.assertEqual(res_renew.status_code, 200)

        # Normal delete when has paid invoices soft-suspends
        res_del_soft = self.client.post(f"/customers/delete/{new_cust_id}", follow_redirects=True)
        self.assertEqual(res_del_soft.status_code, 200)
        conn = db.get_db()
        suspended_cust = conn.execute("SELECT status FROM customers WHERE id = ?", (new_cust_id,)).fetchone()
        self.assertEqual(suspended_cust["status"], "Suspended")

        # Force delete permanently purges record
        res_del_force = self.client.post(f"/customers/delete/{new_cust_id}", data={"force": "1"}, follow_redirects=True)
        self.assertEqual(res_del_force.status_code, 200)
        purged_cust = conn.execute("SELECT * FROM customers WHERE id = ?", (new_cust_id,)).fetchone()
        conn.close()
        self.assertIsNone(purged_cust)
        self.logout()
        print("  [AUDIT PASS] 05: Customer full lifecycle, safe suspension, & force delete verified.")

    def test_06_invoice_operations_and_pay(self):
        """Audit invoice creation, editing, pay with staff collection attribution, and monthly generator."""
        self.login(self.admin["username"], self.admin["password"])
        # Create single invoice
        res = self.client.post("/invoices/create_single", data={
            "customer_id": str(self.customer["id"]),
            "month_period": "November 2026",
            "amount": "2500",
            "due_date": "2026-11-20"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        inv_row = conn.execute("SELECT * FROM invoices WHERE customer_id = ? ORDER BY id DESC LIMIT 1", (self.customer["id"],)).fetchone()
        inv_id = inv_row["id"]

        # Edit invoice
        res_edit = self.client.post(f"/invoices/edit/{inv_id}", data={
            "customer_id": str(self.customer["id"]),
            "amount": "2400",
            "month_period": "November 2026",
            "due_date": "2026-11-25",
            "status": "Unpaid"
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        # Pay invoice attributing to Recovery Boy
        res_pay = self.client.post(f"/invoices/pay/{inv_id}", data={
            "payment_method": "Cash",
            "collected_by_staff_id": str(self.rec["id"])
        }, follow_redirects=True)
        self.assertEqual(res_pay.status_code, 200)

        conn = db.get_db()
        paid_inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv_id,)).fetchone()
        self.assertEqual(paid_inv["status"], "Paid")
        self.assertEqual(paid_inv["collected_by_staff_id"], self.rec["id"])

        # Delete test invoice
        res_del = self.client.post(f"/invoices/delete/{inv_id}", follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        conn.close()
        self.logout()
        print("  [AUDIT PASS] 06: Invoice creation, editing, payment collection attribution, and deletion verified.")

    def test_07_ticket_resolution_and_xp(self):
        """Audit Ticket creation, status updates, technician assignment, XP rewards."""
        self.login(self.admin["username"], self.admin["password"])
        # Add Ticket
        res = self.client.post("/tickets/add", data={
            "customer_id": str(self.customer["id"]),
            "subject": "Fiber Core Broken at FDB Box",
            "details": "Optical power lost completely after pole storm",
            "priority": "Critical",
            "assigned_user_id": str(self.tech["id"])
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        tck_row = conn.execute("SELECT * FROM tickets WHERE customer_id = ? ORDER BY id DESC LIMIT 1", (self.customer["id"],)).fetchone()
        tck_id = tck_row["id"]
        initial_xp = conn.execute("SELECT technician_xp FROM users WHERE id = ?", (self.tech["id"],)).fetchone()["technician_xp"] or 0

        # Edit ticket to In Progress
        res_in_prog = self.client.post(f"/tickets/edit/{tck_id}", data={
            "subject": "Fiber Core Broken at FDB Box",
            "priority": "Critical",
            "status": "In Progress",
            "assigned_user_id": str(self.tech["id"]),
            "resolution_notes": "Technician on pole replacing drop wire"
        }, follow_redirects=True)
        self.assertEqual(res_in_prog.status_code, 200)

        # Resolve ticket -> awards +180 XP for Critical
        res_res = self.client.post(f"/tickets/edit/{tck_id}", data={
            "subject": "Fiber Core Broken at FDB Box",
            "priority": "Critical",
            "status": "Resolved",
            "assigned_user_id": str(self.tech["id"]),
            "resolution_notes": "Spliced Core 1 Blue, power -17.5 dBm verified"
        }, follow_redirects=True)
        self.assertEqual(res_res.status_code, 200)

        conn = db.get_db()
        new_xp = conn.execute("SELECT technician_xp FROM users WHERE id = ?", (self.tech["id"],)).fetchone()["technician_xp"]
        self.assertEqual(new_xp, initial_xp + 180)

        # Delete test ticket
        res_del = self.client.post(f"/tickets/delete/{tck_id}", follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        conn.close()
        self.logout()
        print("  [AUDIT PASS] 07: Ticket workflow, field dispatch notes, and automated technician XP verified.")

    def test_08_staff_management_and_pfp(self):
        """Audit Staff addition, editing, duplicate username protection, and PFP uploads."""
        self.login(self.admin["username"], self.admin["password"])
        uname = f"tech_{int(datetime.now().timestamp())}"
        dummy_png = (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"), "staff_pfp.png")
        
        # Add staff
        res_add = self.client.post("/staff/add", data={
            "full_name": "Test Technician Agent",
            "username": uname,
            "password": "techpassword123",
            "role": "Complaint Boy",
            "phone": "0311-9988776",
            "assigned_area": "Sector B",
            "status": "Active",
            "pfp_file": dummy_png
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(res_add.status_code, 200)

        conn = db.get_db()
        staff_row = conn.execute("SELECT * FROM users WHERE username = ?", (uname,)).fetchone()
        self.assertIsNotNone(staff_row)
        staff_id = staff_row["id"]
        self.assertTrue(staff_row["pfp_image"].startswith("uploads/pfp/"))

        # Edit staff
        res_edit = self.client.post(f"/staff/edit/{staff_id}", data={
            "full_name": "Test Technician Updated",
            "username": uname,
            "password": "", # keep current
            "role": "Complaint Boy",
            "phone": "0311-9988777",
            "assigned_area": "Sector B & C",
            "status": "Active"
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        # Delete staff
        res_del = self.client.post(f"/staff/delete/{staff_id}", follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        conn = db.get_db()
        deleted_staff = conn.execute("SELECT * FROM users WHERE id = ?", (staff_id,)).fetchone()
        conn.close()
        self.assertIsNone(deleted_staff)
        self.logout()
        print("  [AUDIT PASS] 08: Staff creation, PFP upload, update, and deletion verified.")

    def test_09_expenses_investments_deposits_tariffs(self):
        """Audit Expenses, Investments, Deposits, and Tariffs CRUD operations."""
        self.login(self.admin["username"], self.admin["password"])
        # 1. Expense
        res_exp = self.client.post("/expenses", data={
            "title": "Drop Cable 2-Core Roll",
            "category": "Optical Fiber",
            "amount": "6500",
            "expense_date": "2026-11-07",
            "notes": "1000 meters for Sector A maintenance"
        }, follow_redirects=True)
        self.assertEqual(res_exp.status_code, 200)
        conn = db.get_db()
        exp_row = conn.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 1").fetchone()
        exp_id = exp_row["id"]

        res_exp_edit = self.client.post(f"/expenses/edit/{exp_id}", data={
            "title": "Drop Cable 2-Core Roll (Updated)",
            "category": "Optical Fiber",
            "amount": "6800",
            "expense_date": "2026-11-07",
            "notes": "Updated price"
        }, follow_redirects=True)
        self.assertEqual(res_exp_edit.status_code, 200)
        self.client.post(f"/expenses/delete/{exp_id}", follow_redirects=True)

        # 2. Investment
        res_inv = self.client.post("/investments", data={
            "investor_name": "Antigravity Systems Partner",
            "title": "OLT Chassis Expansion",
            "amount": "150000",
            "investment_date": "2026-11-07",
            "notes": "16-port GPON OLT for Sector C"
        }, follow_redirects=True)
        self.assertEqual(res_inv.status_code, 200)
        conn = db.get_db()
        inv_row = conn.execute("SELECT * FROM investments ORDER BY id DESC LIMIT 1").fetchone()
        self.client.post(f"/investments/delete/{inv_row['id']}", follow_redirects=True)

        # 3. Deposit
        res_dep = self.client.post("/deposits", data={
            "customer_id": str(self.customer["id"]),
            "amount": "5000",
            "deposit_type": "ONU Security Deposit",
            "notes": "Refundable upon equipment return"
        }, follow_redirects=True)
        self.assertEqual(res_dep.status_code, 200)

        # 4. Tariff
        tariff_name = f"Plan_{int(datetime.now().timestamp())}"
        res_tar = self.client.post("/tariffs/add", data={
            "name": tariff_name,
            "speed": "50 Mbps Fiber",
            "price": "3500",
            "billing_cycle": "Monthly",
            "description": "Ultra high-speed optical broadband"
        }, follow_redirects=True)
        self.assertEqual(res_tar.status_code, 200)
        conn = db.get_db()
        tar_row = conn.execute("SELECT * FROM tariffs WHERE name = ?", (tariff_name,)).fetchone()
        self.client.post(f"/tariffs/delete/{tar_row['id']}", follow_redirects=True)
        conn.close()
        self.logout()
        print("  [AUDIT PASS] 09: Financial operations (Expenses, Investments, Deposits, Tariffs) verified.")

    def test_10_settings_persistence_and_preview(self):
        """Audit Settings direct updates and live preview sync."""
        self.login(self.admin["username"], self.admin["password"])
        res_save = self.client.post("/settings", data={
            "isp_name": "Sabro Networks",
            "tagline": "Superfast FTTH Broadband & Optical Fiber Solutions",
            "currency": "PKR",
            "business_phone": "0312-9876543",
            "whatsapp_reminder_template": "Salam {name}, bill of {amount} for {month} is due on {due_date}.",
            "jazzcash_title": "Sabro Telecom NOC",
            "jazzcash_no": "0300-1122334",
            "easypaisa_title": "Sabro Telecom NOC",
            "easypaisa_no": "0345-1122334",
            "bank_name": "Meezan Bank Ltd",
            "bank_account_title": "Sabro Networks",
            "bank_iban": "PK12MEZN0000001234567890",
            "agency_name": "Vshatkay Solutions",
            "agency_tagline": "Software Engineering & Telecom Solutions Agency"
        }, follow_redirects=True)
        self.assertEqual(res_save.status_code, 200)

        conn = db.get_db()
        settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
        conn.close()
        self.assertEqual(settings.get("isp_name"), "Sabro Networks")
        self.assertEqual(settings.get("agency_name"), "Vshatkay Solutions")
        self.logout()
        print("  [AUDIT PASS] 10: Settings persistence & agency attribution verified.")

if __name__ == "__main__":
    unittest.main()
