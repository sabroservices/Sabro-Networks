import unittest
import io
import os
import sqlite3
import csv
import tempfile
import shutil
from datetime import datetime, timedelta
import db
import app as flask_app

class SabroNetworksCRUDAndUploadLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db_path = db.DB_PATH
        cls._tmp_dir = tempfile.mkdtemp(prefix="sabro_crud_test_")
        db.DB_PATH = os.path.join(cls._tmp_dir, "crud_test.db")
        db.init_db(force_reset=True)

        flask_app.app.config['TESTING'] = True
        flask_app.app.config['WTF_CSRF_ENABLED'] = False
        cls.client = flask_app.app.test_client()

        conn = db.get_db()
        conn.execute("INSERT OR IGNORE INTO tariffs (id, name, speed_mb, price, description) VALUES (1, '10 MB FTTH', 10, 1000, 'Standard')")
        conn.execute("""
            INSERT OR IGNORE INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES ('Field Tech', 'field.tech', 'tech123', 'Complaint Boy', '0300-1234567', 'Sector A', 'Active', 0.0, date('now'))
        """)
        tech = conn.execute("SELECT id, username, password, full_name FROM users WHERE role = 'Complaint Boy' LIMIT 1").fetchone()
        conn.commit()
        conn.close()
        
        cls.admin_user = "ahmedbaloch"
        cls.admin_pass = "adminadmin1"
        cls.tech_id = tech["id"]

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls._orig_db_path
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def login_admin(self):
        res = self.client.post("/login", data={"username": self.admin_user, "password": self.admin_pass}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

    # --------------------------------------------------------------------------
    # 1. PUT DATA (CREATE)
    # --------------------------------------------------------------------------
    def test_01_put_data_across_all_modules(self):
        """PUT DATA: Create Customer, Ticket, Invoice, Expense, Deposit, Investment, Tariff, Staff."""
        self.login_admin()
        ts = int(datetime.now().timestamp())

        # 1a. Create Customer (/customers/add)
        cust_user = f"cust.{ts}"
        res = self.client.post("/customers/add", data={
            "full_name": f"CRUD Test Subscriber {ts}",
            "pppoe_username": cust_user,
            "password": "fiberPassword123",
            "phone": "0301-5554433",
            "address": "Street 12, House 45, Near Water Tank",
            "area": "Sector B",
            "tariff_id": 1,
            "db_box": "FDB-02, Pole #07",
            "fiber_core": "Core 1 (Blue)",
            "onu_serial": "HWTC88776655",
            "cnic": "35201-1234567-9",
            "expiry_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        cust = conn.execute("SELECT * FROM customers WHERE pppoe_username = ?", (cust_user,)).fetchone()
        self.assertIsNotNone(cust, "Customer must be created in DB")
        cust_id = cust["id"]

        # 1b. Create Complaint Ticket (/tickets/add)
        res = self.client.post("/tickets/add", data={
            "customer_id": cust_id,
            "subject": "Red LOS Alarm Flashing on ONT",
            "details": "Fiber optical drop line got pinched during street construction",
            "priority": "Critical",
            "assigned_user_id": self.tech_id
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        ticket = conn.execute("SELECT * FROM tickets WHERE customer_id = ?", (cust_id,)).fetchone()
        self.assertIsNotNone(ticket, "Ticket must be created in DB")

        # 1c. Create Invoice (/invoices/create_single)
        res = self.client.post("/invoices/create_single", data={
            "customer_id": cust_id,
            "amount": "1800",
            "due_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "notes": "E2E Monthly Broadband Bill"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        inv = conn.execute("SELECT * FROM invoices WHERE customer_id = ?", (cust_id,)).fetchone()
        self.assertIsNotNone(inv, "Invoice must be created in DB")

        # 1d. Create Expense (/expenses)
        res = self.client.post("/expenses", data={
            "title": f"Technician Fuel {ts}",
            "category": "Fuel / Bike Petrol",
            "amount": "850",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "notes": "Field technician bike fuel for Sector B repairs"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        exp = conn.execute("SELECT * FROM expenses WHERE title = ?", (f"Technician Fuel {ts}",)).fetchone()
        self.assertIsNotNone(exp, "Expense must be created in DB")

        # 1e. Create Deposit (/deposits)
        res = self.client.post("/deposits", data={
            "customer_id": cust_id,
            "deposit_type": "Security Deposit",
            "amount": "7000",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "notes": "Security deposit for ONT hardware installation"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        dep = conn.execute("SELECT * FROM deposits WHERE customer_id = ?", (cust_id,)).fetchone()
        self.assertIsNotNone(dep, "Deposit must be created in DB")

        # 1f. Create Investment (/investments)
        res = self.client.post("/investments", data={
            "investor_name": "Sabro Core Network",
            "title": f"Optical Time Domain Reflectometer {ts}",
            "amount": "55000",
            "category": "Splicing Machine",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "notes": "OTDR line tester for 1310/1550nm fiber wavelength"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        invest = conn.execute("SELECT * FROM investments WHERE title LIKE ?", (f"%{ts}%",)).fetchone()
        self.assertIsNotNone(invest, "Investment must be created in DB")

        # 1g. Create Tariff (/tariffs/add)
        res = self.client.post("/tariffs/add", data={
            "name": f"50MB Fiber Jet {ts}",
            "speed_mb": "50",
            "price": "3200",
            "description": "Ultra low latency FTTH gaming tier"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        tariff = conn.execute("SELECT * FROM tariffs WHERE name LIKE ?", (f"%{ts}%",)).fetchone()
        self.assertIsNotNone(tariff, "Tariff must be created in DB")

        # 1h. Create Staff (/staff/add)
        staff_user = f"tech.{ts}"
        res = self.client.post("/staff/add", data={
            "full_name": f"Kamran Splicer {ts}",
            "username": staff_user,
            "password": "splicerPassword99",
            "role": "Complaint Boy",
            "phone": "0315-7788990",
            "assigned_area": "Sector B"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        staff = conn.execute("SELECT * FROM users WHERE username = ?", (staff_user,)).fetchone()
        self.assertIsNotNone(staff, "Staff user must be created in DB")

        conn.close()
        print("  [PASS] 01 - PUT DATA: Successfully created records across Customers, Complaints, Invoices, Expenses, Deposits, Investments, Tariffs, and Staff.")

    # --------------------------------------------------------------------------
    # 2. EDIT DATA (UPDATE)
    # --------------------------------------------------------------------------
    def test_02_edit_data_across_all_modules(self):
        """EDIT DATA: Update Customer, Complaint/Ticket, Invoice, Expense, Deposit, Investment, Tariff, Staff."""
        self.login_admin()
        conn = db.get_db()
        cust = conn.execute("SELECT * FROM customers ORDER BY id DESC LIMIT 1").fetchone()
        ticket = conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 1").fetchone()
        inv = conn.execute("SELECT * FROM invoices ORDER BY id DESC LIMIT 1").fetchone()
        exp = conn.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 1").fetchone()
        dep = conn.execute("SELECT * FROM deposits ORDER BY id DESC LIMIT 1").fetchone()
        invest = conn.execute("SELECT * FROM investments ORDER BY id DESC LIMIT 1").fetchone()
        tariff = conn.execute("SELECT * FROM tariffs ORDER BY id DESC LIMIT 1").fetchone()
        staff = conn.execute("SELECT * FROM users WHERE role != 'Admin' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        # 2a. Edit Customer (/customers/edit/<id>)
        updated_cust_name = f"{cust['full_name']} (Verified)"
        res = self.client.post(f"/customers/edit/{cust['id']}", data={
            "full_name": updated_cust_name,
            "pppoe_username": cust["pppoe_username"],
            "password": "newSecurePassword123",
            "phone": "0309-9988776",
            "address": "Updated Villa 88, Street 9",
            "area": "Sector B",
            "tariff_id": cust["tariff_id"],
            "status": "Active",
            "expiry_date": cust["expiry_date"],
            "onu_serial": "HWTC-UPDATED-01",
            "db_box": "FDB-04, Pole #12",
            "fiber_core": "Core 2 (Orange)",
            "cnic": "35201-9988776-1"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        c_check = conn.execute("SELECT * FROM customers WHERE id = ?", (cust["id"],)).fetchone()
        self.assertEqual(c_check["full_name"], updated_cust_name)
        self.assertEqual(c_check["db_box"], "FDB-04, Pole #12")
        self.assertEqual(c_check["fiber_core"], "Core 2 (Orange)")
        conn.close()

        # 2b. Edit Ticket (Resolve Complaint) (/tickets/edit/<id>)
        res = self.client.post(f"/tickets/edit/{ticket['id']}", data={
            "subject": "Fiber Cable Spliced and Optical Power Restored",
            "details": "Drop cable re-routed and spliced with Fujikura machine",
            "priority": "Medium",
            "status": "Resolved",
            "assigned_user_id": self.tech_id,
            "resolution_notes": "Spliced drop fiber core 2 at Pole #12. Optical power measured at -19.5 dBm. Signal verified OK."
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        t_check = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket["id"],)).fetchone()
        self.assertEqual(t_check["status"], "Resolved")
        self.assertIn("-19.5 dBm", t_check["resolution_notes"])
        conn.close()

        # 2c. Edit Invoice (/invoices/edit/<id>) & Pay Invoice (/invoices/pay/<id>)
        res = self.client.post(f"/invoices/edit/{inv['id']}", data={
            "amount": "2100",
            "month_period": inv["month_period"],
            "due_date": inv["due_date"],
            "status": "Unpaid",
            "notes": "Updated package fee + fiber patch cord replacement"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = db.get_db()
        inv_check = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv["id"],)).fetchone()
        self.assertEqual(inv_check["amount"], 2100.0)
        conn.close()

        res = self.client.post(f"/invoices/pay/{inv['id']}", data={
            "collected_by_staff_id": self.tech_id,
            "payment_method": "Cash",
            "paid_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        conn = db.get_db()
        inv_paid = conn.execute("SELECT * FROM invoices WHERE id = ?", (inv["id"],)).fetchone()
        self.assertEqual(inv_paid["status"], "Paid")
        conn.close()

        # 2d. Edit Expense (/expenses/edit/<id>)
        res = self.client.post(f"/expenses/edit/{exp['id']}", data={
            "title": f"{exp['title']} (Updated)",
            "category": "Office Electricity / NOC UPS",
            "amount": "1250",
            "date": exp["date"],
            "paid_by": "Admin",
            "notes": "UPS battery distilled water and maintenance"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        conn = db.get_db()
        exp_check = conn.execute("SELECT * FROM expenses WHERE id = ?", (exp["id"],)).fetchone()
        self.assertEqual(exp_check["amount"], 1250.0)
        self.assertEqual(exp_check["category"], "Office Electricity / NOC UPS")
        conn.close()

        # 2e. Edit Deposit (/deposits/edit/<id>)
        res = self.client.post(f"/deposits/edit/{dep['id']}", data={
            "deposit_type": "Security Deposit",
            "amount": "8000",
            "status": "Held",
            "date": dep["date"],
            "notes": "Security deposit updated to 8000 PKR"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        conn = db.get_db()
        dep_check = conn.execute("SELECT * FROM deposits WHERE id = ?", (dep["id"],)).fetchone()
        self.assertEqual(dep_check["amount"], 8000.0)
        conn.close()

        # 2f. Edit Investment (/investments/edit/<id>)
        res = self.client.post(f"/investments/edit/{invest['id']}", data={
            "investor_name": "Sabro Core Network",
            "title": f"{invest['title']} - Upgraded Calibrated",
            "amount": "60000",
            "category": "Splicing Machine",
            "date": invest["date"],
            "notes": "Calibrated with optical power meter"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        conn = db.get_db()
        invst_check = conn.execute("SELECT * FROM investments WHERE id = ?", (invest["id"],)).fetchone()
        self.assertEqual(invst_check["amount"], 60000.0)
        conn.close()

        # 2g. Edit Tariff (/tariffs/edit/<id>)
        res = self.client.post(f"/tariffs/edit/{tariff['id']}", data={
            "name": f"{tariff['name']} (Pro Edition)",
            "speed_mb": "60",
            "price": "3500",
            "description": "Upgraded to 60 Mbps with dedicated FTTH VLAN"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        conn = db.get_db()
        tar_check = conn.execute("SELECT * FROM tariffs WHERE id = ?", (tariff["id"],)).fetchone()
        self.assertEqual(tar_check["speed_mb"], 60)
        self.assertEqual(tar_check["price"], 3500.0)
        conn.close()

        # 2h. Edit Staff (/staff/edit/<id>)
        res = self.client.post(f"/staff/edit/{staff['id']}", data={
            "full_name": f"{staff['full_name']} (Lead Technician)",
            "username": staff["username"],
            "password": "",  # preserve current password
            "role": "Complaint Boy",
            "phone": "0315-9999111",
            "assigned_area": "Sector A & B",
            "status": "Active"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        conn = db.get_db()
        st_check = conn.execute("SELECT * FROM users WHERE id = ?", (staff["id"],)).fetchone()
        self.assertEqual(st_check["phone"], "0315-9999111")
        self.assertEqual(st_check["assigned_area"], "Sector A & B")
        conn.close()

        print("  [PASS] 02 - EDIT DATA: Successfully edited and persisted changes for Customers, Complaints, Invoices, Expenses, Deposits, Investments, Tariffs, and Staff.")

    # --------------------------------------------------------------------------
    # 3. DELETE DATA
    # --------------------------------------------------------------------------
    def test_03_delete_data_across_all_modules(self):
        """DELETE DATA: Delete Ticket, Invoice, Expense, Investment, Tariff, Staff, and Customer status toggle."""
        self.login_admin()
        conn = db.get_db()
        ticket = conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 1").fetchone()
        exp = conn.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 1").fetchone()
        invest = conn.execute("SELECT * FROM investments ORDER BY id DESC LIMIT 1").fetchone()
        tariff = conn.execute("SELECT * FROM tariffs WHERE id NOT IN (SELECT tariff_id FROM customers WHERE tariff_id IS NOT NULL) ORDER BY id DESC LIMIT 1").fetchone()
        staff = conn.execute("SELECT * FROM users WHERE role != 'Admin' ORDER BY id DESC LIMIT 1").fetchone()
        cust = conn.execute("SELECT * FROM customers ORDER BY id DESC LIMIT 1").fetchone()

        # Create an unpaid invoice specifically for testing deletion
        conn.execute("INSERT INTO invoices (invoice_number, customer_id, amount, month_period, due_date, status, created_at) VALUES ('INV-TEST-DEL', ?, 1500, 'November 2026', '2026-11-15', 'Unpaid', '2026-11-01')", (cust["id"],))
        conn.commit()
        unpaid_inv = conn.execute("SELECT * FROM invoices WHERE invoice_number = 'INV-TEST-DEL'").fetchone()
        conn.close()

        # 3a. Delete Ticket (/tickets/delete/<id>)
        if ticket:
            res = self.client.post(f"/tickets/delete/{ticket['id']}", follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            conn = db.get_db()
            self.assertIsNone(conn.execute("SELECT id FROM tickets WHERE id = ?", (ticket["id"],)).fetchone())
            conn.close()

        # 3b. Delete Unpaid Invoice (/invoices/delete/<id>)
        if unpaid_inv:
            res = self.client.post(f"/invoices/delete/{unpaid_inv['id']}", follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            conn = db.get_db()
            self.assertIsNone(conn.execute("SELECT id FROM invoices WHERE id = ?", (unpaid_inv["id"],)).fetchone())
            conn.close()

        # 3c. Delete Expense (/expenses/delete/<id>)
        if exp:
            res = self.client.post(f"/expenses/delete/{exp['id']}", follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            conn = db.get_db()
            self.assertIsNone(conn.execute("SELECT id FROM expenses WHERE id = ?", (exp["id"],)).fetchone())
            conn.close()

        # 3d. Delete Investment (/investments/delete/<id>)
        if invest:
            res = self.client.post(f"/investments/delete/{invest['id']}", follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            conn = db.get_db()
            self.assertIsNone(conn.execute("SELECT id FROM investments WHERE id = ?", (invest["id"],)).fetchone())
            conn.close()

        # 3e. Delete Tariff (/tariffs/delete/<id>)
        if tariff:
            res = self.client.post(f"/tariffs/delete/{tariff['id']}", follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            conn = db.get_db()
            self.assertIsNone(conn.execute("SELECT id FROM tariffs WHERE id = ?", (tariff["id"],)).fetchone())
            conn.close()

        # 3f. Delete Staff (/staff/delete/<id>)
        if staff:
            res = self.client.post(f"/staff/delete/{staff['id']}", follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            conn = db.get_db()
            self.assertIsNone(conn.execute("SELECT id FROM users WHERE id = ?", (staff["id"],)).fetchone())
            conn.close()

        # 3g. Toggle Customer Status (/customers/toggle_status/<id>)
        if cust:
            res = self.client.post(f"/customers/toggle_status/{cust['id']}", follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            conn = db.get_db()
            toggled_cust = conn.execute("SELECT status FROM customers WHERE id = ?", (cust["id"],)).fetchone()
            self.assertEqual(toggled_cust["status"], "Suspended")
            # Toggle back to Active
            self.client.post(f"/customers/toggle_status/{cust['id']}", follow_redirects=True)
            active_cust = conn.execute("SELECT status FROM customers WHERE id = ?", (cust["id"],)).fetchone()
            self.assertEqual(active_cust["status"], "Active")
            conn.close()

        print("  [PASS] 03 - DELETE DATA: Successfully deleted records and verified removal across Tickets, Invoices, Expenses, Investments, Tariffs, Staff, and Customer status toggle.")

    # --------------------------------------------------------------------------
    # 4. UPLOAD DATA (CSV IMPORT & DATABASE RESTORE)
    # --------------------------------------------------------------------------
    def test_04_upload_data_csv_import_and_database_backup(self):
        """UPLOAD DATA: Bulk CSV import, Database Backup Download & Binary Restore Verification."""
        self.login_admin()
        ts = int(datetime.now().timestamp())

        # 4a. Upload CSV Customer Data (/import/customers)
        csv_data = f"""Customer Name,PPPoE Username,Phone,Address,Area,Plan,FDB Box,Fiber Core
Upload Subscriber Alpha {ts},up.alpha.{ts},0302-1234567,Flat 4B Crystal Towers,Sector A,15MB,FDB-01 Pole #04,Core 1 (Blue)
Upload Subscriber Beta {ts},up.beta.{ts},0302-7654321,House 89 Main Boulevard,Sector B,20MB,FDB-03 Pole #08,Core 2 (Orange)
"""
        csv_bytes = io.BytesIO(csv_data.encode('utf-8'))
        upload_res = self.client.post("/import/customers", data={
            "csv_file": (csv_bytes, f"subscribers_{ts}.csv")
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(upload_res.status_code, 200)

        conn = db.get_db()
        alpha = conn.execute("SELECT * FROM customers WHERE pppoe_username = ?", (f"up.alpha.{ts}",)).fetchone()
        beta = conn.execute("SELECT * FROM customers WHERE pppoe_username = ?", (f"up.beta.{ts}",)).fetchone()
        self.assertIsNotNone(alpha, "Uploaded customer Alpha must exist in DB")
        self.assertIsNotNone(beta, "Uploaded customer Beta must exist in DB")
        self.assertEqual(alpha["area"], "Sector A")
        self.assertEqual(beta["area"], "Sector B")
        conn.close()

        # 4b. Download SQLite Database Backup (/backup/db)
        backup_res = self.client.get("/backup/db")
        self.assertEqual(backup_res.status_code, 200)
        self.assertEqual(backup_res.content_type, "application/octet-stream")
        backup_data = backup_res.data
        self.assertTrue(backup_data.startswith(b"SQLite format 3\x00"), "Backup file must be authentic SQLite 3 binary")

        # 4c. Upload & Restore Database Backup (/restore/db)
        restore_bytes = io.BytesIO(backup_data)
        restore_res = self.client.post("/restore/db", data={
            "backup_file": (restore_bytes, f"restore_test_{ts}.db")
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(restore_res.status_code, 200)

        # 4d. Verify DB integrity after restore
        conn = db.get_db()
        integrity = conn.execute("PRAGMA integrity_check;").fetchone()
        self.assertEqual(integrity[0], "ok", "Database PRAGMA integrity_check must return 'ok'")

        # Clean up the upload test subscribers
        conn.execute("DELETE FROM customers WHERE pppoe_username LIKE 'up.%'")
        conn.commit()
        conn.close()

        print("  [PASS] 04 - UPLOAD DATA: Successfully uploaded CSV customer records, verified DB insertion, generated SQLite backup, and uploaded/restored database backup safely.")

if __name__ == '__main__':
    unittest.main()
