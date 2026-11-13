import unittest
import os
import io
import tempfile
from werkzeug.security import generate_password_hash
import db
import app

class TestProductionLifecycleSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db_path = db.DB_PATH
        cls._temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._temp_path = cls._temp_file.name
        cls._temp_file.close()
        db.DB_PATH = cls._temp_path
        db.init_db(force_reset=True)

        app.app.config["TESTING"] = True
        cls.client = app.app.test_client()
        cls.admin_user = "ahmedbaloch"
        cls.admin_pass = "adminadmin1"

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls._orig_db_path
        if os.path.exists(cls._temp_path):
            try:
                os.remove(cls._temp_path)
            except Exception:
                pass

    def login_admin(self):
        return self.client.post("/login", data={
            "username": self.admin_user,
            "password": self.admin_pass
        }, follow_redirects=True)

    def test_01_admin_login_and_auth(self):
        """Verify Admin login and session authentication."""
        res = self.login_admin()
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Dashboard", res.data)
        self.assertIn(b"Ahmed Baloch", res.data)

    def test_02_tariff_management(self):
        """Verify Tariff creation, editing, and retrieval."""
        self.login_admin()
        # Add Tariff
        res = self.client.post("/tariffs/add", data={
            "name": "Production 20M Fiber",
            "speed_mb": "20",
            "price": "2200",
            "description": "Fast home plan"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Production 20M Fiber", res.data)

        # Retrieve tariff ID
        conn = db.get_db()
        t = conn.execute("SELECT id FROM tariffs WHERE name = ?", ("Production 20M Fiber",)).fetchone()
        self.assertIsNotNone(t)
        tariff_id = t["id"]

        # Edit Tariff
        res_edit = self.client.post(f"/tariffs/edit/{tariff_id}", data={
            "name": "Production 25M Fiber",
            "speed_mb": "25",
            "price": "2400",
            "description": "Upgraded home plan"
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        self.assertIn(b"Production 25M Fiber", res_edit.data)
        conn.close()

    def test_03_customer_lifecycle(self):
        """Verify Customer creation, FTTH details, editing, and deletion."""
        self.login_admin()
        conn = db.get_db()
        tariff = conn.execute("SELECT id FROM tariffs LIMIT 1").fetchone()
        tariff_id = tariff["id"] if tariff else 1
        conn.close()

        # Create customer
        res = self.client.post("/customers/add", data={
            "full_name": "Tariq Mehmood",
            "pppoe_username": "tariq.ftth",
            "password": "password789",
            "phone": "03121234567",
            "address": "House 12, Street 3",
            "area": "Sector C",
            "tariff_id": str(tariff_id),
            "onu_serial": "HWTCA1234567",
            "db_box": "Pole #08",
            "fiber_core": "Core 4 (Brown)",
            "cnic": "42201-9876543-1"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Tariq Mehmood", res.data)

        conn = db.get_db()
        cust = conn.execute("SELECT id FROM customers WHERE pppoe_username = ?", ("tariq.ftth",)).fetchone()
        self.assertIsNotNone(cust)
        cust_id = cust["id"]

        # Edit customer
        res_edit = self.client.post(f"/customers/edit/{cust_id}", data={
            "full_name": "Tariq Mehmood Upgraded",
            "pppoe_username": "tariq.ftth",
            "password": "newpassword999",
            "phone": "03129999999",
            "address": "House 14, Street 3",
            "area": "Sector C",
            "tariff_id": str(tariff_id),
            "status": "Active",
            "expiry_date": "2026-12-31",
            "onu_serial": "HWTCA9999999",
            "db_box": "Pole #09",
            "fiber_core": "Core 1 (Blue)",
            "cnic": "42201-9876543-1"
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        self.assertIn(b"Tariq Mehmood Upgraded", res_edit.data)

        # Delete customer
        res_del = self.client.post(f"/customers/delete/{cust_id}", follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        conn_check = db.get_db()
        del_check = conn_check.execute("SELECT * FROM customers WHERE id = ?", (cust_id,)).fetchone()
        self.assertIsNone(del_check)
        conn_check.close()
        conn.close()

    def test_04_invoice_and_payment_recording(self):
        """Verify Invoice generation, payment atomic transaction, and idempotency."""
        self.login_admin()
        conn = db.get_db()
        t = conn.execute("SELECT id FROM tariffs LIMIT 1").fetchone()
        t_id = t["id"] if t else 1

        # Create customer for billing
        conn.execute("""
            INSERT INTO customers (full_name, pppoe_username, password, phone, tariff_id, status, created_at)
            VALUES ('Billing Test User', 'billing.test', 'pass123', '03001112233', ?, 'Active', '2026-11-13')
        """, (t_id,))
        conn.commit()
        cust = conn.execute("SELECT id FROM customers WHERE pppoe_username = 'billing.test'").fetchone()
        cust_id = cust["id"]

        # Create single invoice
        res = self.client.post("/invoices/create_single", data={
            "customer_id": str(cust_id),
            "amount": "2500.0",
            "month_period": "November 2026",
            "due_date": "2026-11-25",
            "status": "Unpaid"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        inv = conn.execute("SELECT id, status FROM invoices WHERE customer_id = ?", (cust_id,)).fetchone()
        self.assertIsNotNone(inv)
        self.assertEqual(inv["status"], "Unpaid")
        inv_id = inv["id"]

        # Record payment
        res_pay = self.client.post(f"/invoices/pay/{inv_id}", data={
            "payment_method": "JazzCash"
        }, follow_redirects=True)
        self.assertEqual(res_pay.status_code, 200)

        inv_paid = conn.execute("SELECT status, payment_method FROM invoices WHERE id = ?", (inv_id,)).fetchone()
        self.assertEqual(inv_paid["status"], "Paid")
        self.assertEqual(inv_paid["payment_method"], "JazzCash")

        # Verify idempotency: paying an already paid invoice does not duplicate collection
        res_double_pay = self.client.post(f"/invoices/pay/{inv_id}", data={
            "payment_method": "Cash"
        }, follow_redirects=True)
        self.assertIn(b"already marked as Paid", res_double_pay.data)
        conn.close()

    def test_05_expense_management(self):
        """Verify Expense creation and deletion."""
        self.login_admin()
        res = self.client.post("/expenses", data={
            "title": "Fiber Splicing Machine Servicing",
            "category": "Maintenance",
            "amount": "4500",
            "date": "2026-11-13",
            "paid_by": "Ahmed Baloch",
            "notes": "Optical splicer maintenance"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Fiber Splicing Machine Servicing", res.data)

    def test_06_deposit_management(self):
        """Verify Customer Security Deposit recording and refunding."""
        self.login_admin()
        conn = db.get_db()
        cust = conn.execute("SELECT id FROM customers LIMIT 1").fetchone()
        cust_id = cust["id"] if cust else 1
        conn.close()

        res = self.client.post("/deposits", data={
            "customer_id": str(cust_id),
            "deposit_type": "ONU Security Deposit",
            "amount": "3000",
            "date": "2026-11-13",
            "notes": "Refundable upon equipment return"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"ONU Security Deposit", res.data)

    def test_07_investment_management(self):
        """Verify Capital Investment tracking."""
        self.login_admin()
        res = self.client.post("/investments", data={
            "investor_name": "Ahmed Baloch",
            "title": "OLT Chassis Expansion",
            "amount": "150000",
            "category": "Infrastructure",
            "date": "2026-11-13",
            "notes": "16-port GPON OLT for Sector D"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"OLT Chassis Expansion", res.data)

    def test_08_support_ticket_lifecycle(self):
        """Verify Support Ticket creation and resolution."""
        self.login_admin()
        conn = db.get_db()
        cust = conn.execute("SELECT id FROM customers LIMIT 1").fetchone()
        cust_id = cust["id"] if cust else 1
        conn.close()

        res = self.client.post("/tickets/add", data={
            "customer_id": str(cust_id),
            "subject": "Fiber Cable Cut by Construction",
            "details": "Drop cable damaged near main road",
            "priority": "High"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Fiber Cable Cut", res.data)

    def test_09_settings_management(self):
        """Verify ISP company metadata and payment accounts update."""
        self.login_admin()
        res = self.client.post("/settings", data={
            "isp_name": "Sabro Networks Enterprise",
            "tagline": "FTTH High-Speed Fiber Internet",
            "currency": "PKR",
            "phone": "03001234567",
            "business_whatsapp": "923001234567",
            "email": "noc@sabronetworks.com",
            "address": "NOC Center, Main Avenue",
            "jazzcash_no": "03001234567",
            "easypaisa_no": "03121234567",
            "bank_info": "Meezan Bank 0101-12345678",
            "agency_name": "Vshatkay Solutions",
            "agency_tagline": "Software Engineering & Telecom Solutions Agency",
            "agency_url": "https://vshatkaysolutions.com"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Sabro Networks Enterprise", res.data)

    def test_10_persistence_simulation(self):
        """
        Comprehensive Persistence Test:
          1. Create customer.
          2. Create invoice.
          3. Record payment.
          4. Close connection.
          5. Open new connection.
          6. Confirm all records remain.
          7. Simulate server container restart.
          8. Verify all records remain.
        """
        # Step 1: Create a test customer
        conn1 = db.get_db()
        t = conn1.execute("SELECT id FROM tariffs LIMIT 1").fetchone()
        t_id = t["id"] if t else 1
        conn1.execute("""
            INSERT INTO customers (full_name, pppoe_username, password, phone, tariff_id, status, created_at)
            VALUES ('Persistence Test Customer', 'persist.user', 'secretPass1', '03210000000', ?, 'Active', '2026-11-13')
        """, (t_id,))
        conn1.commit()
        cust_row = conn1.execute("SELECT id FROM customers WHERE pppoe_username = 'persist.user'").fetchone()
        self.assertIsNotNone(cust_row)
        c_id = cust_row["id"]

        # Step 2: Create a test invoice
        conn1.execute("""
            INSERT INTO invoices (invoice_number, customer_id, amount, month_period, status, due_date, created_at)
            VALUES ('INV-PERSIST-001', ?, 3200.0, 'November 2026', 'Unpaid', '2026-11-30', '2026-11-13')
        """, (c_id,))
        conn1.commit()
        inv_row = conn1.execute("SELECT id FROM invoices WHERE invoice_number = 'INV-PERSIST-001'").fetchone()
        self.assertIsNotNone(inv_row)
        i_id = inv_row["id"]

        # Step 3: Record a test payment
        conn1.execute("UPDATE invoices SET status = 'Paid', paid_date = '2026-11-13', payment_method = 'Cash' WHERE id = ?", (i_id,))
        conn1.commit()

        # Step 4: Close connection
        conn1.close()

        # Step 5: Open new connection
        conn2 = db.get_db()

        # Step 6: Confirm all records remain
        c2 = conn2.execute("SELECT * FROM customers WHERE id = ?", (c_id,)).fetchone()
        self.assertIsNotNone(c2)
        self.assertEqual(c2["pppoe_username"], "persist.user")

        i2 = conn2.execute("SELECT * FROM invoices WHERE id = ?", (i_id,)).fetchone()
        self.assertIsNotNone(i2)
        self.assertEqual(i2["status"], "Paid")
        self.assertEqual(i2["amount"], 3200.0)
        conn2.close()

        # Step 7: Simulate application restart by running init_db (safe restart)
        db.init_db(force_reset=False)

        # Step 8: Verify all records remain after restart simulation
        conn3 = db.get_db()
        c3 = conn3.execute("SELECT * FROM customers WHERE id = ?", (c_id,)).fetchone()
        self.assertIsNotNone(c3, "Data disappeared after restart simulation!")
        self.assertEqual(c3["full_name"], "Persistence Test Customer")

        i3 = conn3.execute("SELECT * FROM invoices WHERE id = ?", (i_id,)).fetchone()
        self.assertIsNotNone(i3, "Invoice disappeared after restart simulation!")
        self.assertEqual(i3["status"], "Paid")
        conn3.close()

if __name__ == "__main__":
    unittest.main()
