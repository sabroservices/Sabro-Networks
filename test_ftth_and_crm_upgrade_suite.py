import unittest
import os
import io
import json
import tempfile
import shutil
from datetime import datetime, timedelta
import db
import app as my_app
import ftth_engine
import mikrotik_client

class TestFTTHAndCRMUpgradeSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db_path = db.DB_PATH
        cls._tmp_dir = tempfile.mkdtemp(prefix="sabro_ftth_test_")
        db.DB_PATH = os.path.join(cls._tmp_dir, "ftth_upgrade_test.db")
        db.init_db(force_reset=True)

        my_app.app.config["TESTING"] = True
        my_app.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = my_app.app.test_client()

        # Seed initial test fixtures
        conn = db.get_db()
        conn.execute("INSERT INTO tariffs (name, speed_mb, price, description) VALUES ('20 MB FTTH Fiber', 20, 1500, 'Fiber High Speed')")
        conn.execute("""
            INSERT INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES ('Splicer Tech', 'splicer.tech', 'techpass1', 'Complaint Boy', '0300-1122334', 'Sector A', 'Active', 0.0, date('now'))
        """)
        conn.execute("""
            INSERT INTO customers (full_name, pppoe_username, password, phone, address, area, tariff_id, status, expiry_date, onu_serial, db_box, fiber_core, lat, lng, created_at)
            VALUES ('Tariq Baloch', 'tariq.baloch', 'fiber123', '0301-7788990', 'House 22 Street 5', 'Sector A', 1, 'Active', date('now', '+25 days'), 'HWTC11223344', 'FDB-01', 'Core 1 (Blue)', 24.8607, 67.0011, date('now'))
        """)
        cls.cust_id = conn.execute("SELECT id FROM customers WHERE pppoe_username = 'tariq.baloch'").fetchone()[0]
        cls.tech_id = conn.execute("SELECT id FROM users WHERE username = 'splicer.tech'").fetchone()[0]
        conn.execute("""
            INSERT INTO invoices (invoice_number, customer_id, amount, month_period, status, due_date, created_at)
            VALUES ('INV-TEST-001', ?, 1500, 'November 2026', 'Unpaid', date('now', '+5 days'), date('now'))
        """, (cls.cust_id,))
        conn.commit()
        conn.close()

        cls.admin_user = "ahmedbaloch"
        cls.admin_pass = "adminadmin1"

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls._orig_db_path
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def login_admin(self):
        return self.client.post("/login", data={
            "username": self.admin_user,
            "password": self.admin_pass
        }, follow_redirects=True)

    def logout(self):
        return self.client.get("/logout", follow_redirects=True)

    # --------------------------------------------------------------------------
    # 1. MIKROTIK ROUTEROS GATEWAY
    # --------------------------------------------------------------------------
    def test_01_mikrotik_router_management(self):
        """Verify MikroTik multi-router management, session querying, and cutoff."""
        self.login_admin()
        
        # Access routers page
        res = self.client.get("/routers")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Router Operations", res.data)

        # Add a secondary router
        res_add = self.client.post("/routers/add", data={
            "name": "Distribution Router RB4011",
            "ip_address": "192.168.10.1",
            "api_port": 8728,
            "username": "admin",
            "password": "RouterPassword123",
            "location": "Sector A Sub-Station"
        }, follow_redirects=True)
        self.assertEqual(res_add.status_code, 200)

        # Verify added in DB
        conn = db.get_db()
        r = conn.execute("SELECT * FROM routers WHERE name = 'Distribution Router RB4011'").fetchone()
        conn.close()
        self.assertIsNotNone(r)
        self.assertEqual(r["ip_address"], "192.168.10.1")

        # Test Sync All Users to MikroTik
        res_sync = self.client.post("/routers/sync_all", follow_redirects=True)
        self.assertEqual(res_sync.status_code, 200)
        self.assertIn(b"synchronized", res_sync.data)

        # Test Cutoff Expired
        res_cutoff = self.client.post("/routers/cutoff_expired", follow_redirects=True)
        self.assertEqual(res_cutoff.status_code, 200)
        self.assertIn(b"Cutoff", res_cutoff.data)

        # Test Kick Session
        res_kick = self.client.post("/routers/kick/tariq.baloch", follow_redirects=True)
        self.assertEqual(res_kick.status_code, 200)

        # Test Traffic API
        res_api = self.client.get(f"/api/routers/{r['id']}/traffic")
        self.assertEqual(res_api.status_code, 200)
        data = res_api.get_json()
        self.assertTrue(data["success"])
        self.assertIn("interfaces", data)

        self.logout()
        print("  [PASS] 01 - MikroTik RouterOS Gateway Operations & Live Emulation Verified.")

    # --------------------------------------------------------------------------
    # 2. FTTH OPTICAL INFRASTRUCTURE & LINK BUDGET
    # --------------------------------------------------------------------------
    def test_02_ftth_optical_infrastructure(self):
        """Verify OLT management, PON ports allocation, and optical budget calculations."""
        self.login_admin()

        # Access FTTH topology
        res = self.client.get("/ftth/topology")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Optical Line Terminals", res.data)

        # Add OLT
        res_olt = self.client.post("/ftth/olts/add", data={
            "name": "NOC Core GPON 16-Port",
            "model": "Huawei MA5608T",
            "ip_address": "10.0.0.5",
            "pon_ports_count": 16,
            "location": "Main Rack B"
        }, follow_redirects=True)
        self.assertEqual(res_olt.status_code, 200)

        # Verify OLT & PON ports created
        conn = db.get_db()
        olt = conn.execute("SELECT * FROM olts WHERE name = 'NOC Core GPON 16-Port'").fetchone()
        self.assertIsNotNone(olt)
        pon_count = conn.execute("SELECT COUNT(*) FROM pon_ports WHERE olt_id = ?", (olt["id"],)).fetchone()[0]
        self.assertEqual(pon_count, 16)

        # Add Splitter / FDB
        res_sp = self.client.post("/ftth/splitters/add", data={
            "name": "FDB-09 Sector B",
            "ratio": "1:8",
            "max_ports": 8,
            "location": "Pole 25 Main Boulevard",
            "lat": 24.8710,
            "lng": 67.0120
        }, follow_redirects=True)
        self.assertEqual(res_sp.status_code, 200)

        sp = conn.execute("SELECT * FROM splitters WHERE name = 'FDB-09 Sector B'").fetchone()
        self.assertIsNotNone(sp)
        self.assertEqual(sp["ratio"], "1:8")
        conn.close()

        # Test Optical Budget Calculation API
        res_calc = self.client.get("/api/ftth/calculate_budget?tx=3.5&distance=1500&ratio=1:8")
        self.assertEqual(res_calc.status_code, 200)
        cdata = res_calc.get_json()
        self.assertIn("estimated_rx_power_dbm", cdata)
        self.assertIn("quality", cdata)

        self.logout()
        print("  [PASS] 02 - FTTH Optical Core, PON Ports & Link Budget Calculator Verified.")

    # --------------------------------------------------------------------------
    # 3. NETWORK GIS MAP
    # --------------------------------------------------------------------------
    def test_03_network_gis_map(self):
        """Verify $0 OpenStreetMap Leaflet integration and GIS endpoints."""
        self.login_admin()

        res_map = self.client.get("/network/map")
        self.assertEqual(res_map.status_code, 200)
        self.assertIn(b"gisMap", res_map.data)
        self.assertIn(b"OpenStreetMap", res_map.data)

        res_api = self.client.get("/api/network/map_data")
        self.assertEqual(res_api.status_code, 200)
        mdata = res_api.get_json()
        self.assertIn("olts", mdata)
        self.assertIn("splitters", mdata)
        self.assertIn("customers", mdata)
        self.assertTrue(len(mdata["customers"]) > 0)

        self.logout()
        print("  [PASS] 03 - Network GIS OpenStreetMap ($0 Free-Tier) & Markers Verified.")

    # --------------------------------------------------------------------------
    # 4. OPTICAL INVENTORY & ASSETS
    # --------------------------------------------------------------------------
    def test_04_inventory_and_hardware_assets(self):
        """Verify warehouse hardware tracking, stock in/out, and reorder alerts."""
        self.login_admin()

        res_inv = self.client.get("/inventory")
        self.assertEqual(res_inv.status_code, 200)
        self.assertIn(b"Warehouse Stock Ledger", res_inv.data)

        # Add Hardware Item
        res_add_itm = self.client.post("/inventory/add", data={
            "name": "Fiber Optic Fast Connectors SC/UPC",
            "category": "Fast Connector",
            "unit": "pack",
            "quantity": 20,
            "unit_cost": 350,
            "retail_price": 500,
            "supplier": "Karachi Telecom Market",
            "min_alert_threshold": 5
        }, follow_redirects=True)
        self.assertEqual(res_add_itm.status_code, 200)

        conn = db.get_db()
        itm = conn.execute("SELECT * FROM inventory_items WHERE name = 'Fiber Optic Fast Connectors SC/UPC'").fetchone()
        self.assertIsNotNone(itm)
        itm_id = itm["id"]
        conn.close()

        # Transact Outbound (Assign to Technician)
        res_tx = self.client.post("/inventory/transact", data={
            "item_id": itm_id,
            "transaction_type": "Outbound",
            "quantity": 3,
            "notes": "Issued to Splicer Tech for New Installs"
        }, follow_redirects=True)
        self.assertEqual(res_tx.status_code, 200)

        conn = db.get_db()
        updated_itm = conn.execute("SELECT quantity FROM inventory_items WHERE id = ?", (itm_id,)).fetchone()
        self.assertEqual(updated_itm["quantity"], 17)
        conn.close()

        self.logout()
        print("  [PASS] 04 - Optical Inventory, Hardware Tracking & Movement Ledger Verified.")

    # --------------------------------------------------------------------------
    # 5. FIELD INSTALLATION WORKFLOWS
    # --------------------------------------------------------------------------
    def test_05_field_installations_workflow(self):
        """Verify field connection work orders, optical power testing, and activation."""
        self.login_admin()

        res_inst_page = self.client.get("/installations")
        self.assertEqual(res_inst_page.status_code, 200)

        # Dispatch installation work order
        res_dispatch = self.client.post("/installations/add", data={
            "customer_id": self.cust_id,
            "technician_id": self.tech_id,
            "scheduled_date": datetime.now().strftime("%Y-%m-%d"),
            "notes": "Route 80m drop wire from FDB-01"
        }, follow_redirects=True)
        self.assertEqual(res_dispatch.status_code, 200)

        conn = db.get_db()
        order = conn.execute("SELECT id FROM installations WHERE customer_id = ? ORDER BY id DESC LIMIT 1", (self.cust_id,)).fetchone()
        self.assertIsNotNone(order)
        order_id = order["id"]
        conn.close()

        # Technician updates work order with tested optical power & completes
        res_update = self.client.post(f"/installations/update/{order_id}", data={
            "status": "Completed",
            "drop_cable_length": 85.0,
            "optical_power_dbm": -19.4,
            "onu_mac": "HWTC-99887766",
            "router_model": "Tenda F3 300M",
            "notes": "Spliced on core 1, link tested at -19.4 dBm."
        }, follow_redirects=True)
        self.assertEqual(res_update.status_code, 200)

        conn = db.get_db()
        completed_order = conn.execute("SELECT * FROM installations WHERE id = ?", (order_id,)).fetchone()
        self.assertEqual(completed_order["status"], "Completed")
        self.assertEqual(completed_order["optical_power_dbm"], -19.4)
        
        # Verify customer was automatically activated and hardware updated
        cust = conn.execute("SELECT status, onu_serial, router_model FROM customers WHERE id = ?", (self.cust_id,)).fetchone()
        self.assertEqual(cust["status"], "Active")
        self.assertEqual(cust["onu_serial"], "HWTC-99887766")
        conn.close()

        self.logout()
        print("  [PASS] 05 - Field Installation Lifecycle, Optical dBm & Auto-Activation Verified.")

    # --------------------------------------------------------------------------
    # 6. CUSTOMER 360° PROFILE & STATEMENT
    # --------------------------------------------------------------------------
    def test_06_customer_360_profile_and_statement(self):
        """Verify Customer 360° tabbed dashboard and printable financial statement."""
        self.login_admin()

        res_view = self.client.get(f"/customers/{self.cust_id}/view")
        self.assertEqual(res_view.status_code, 200)
        self.assertIn(b"Customer 360", res_view.data)
        self.assertIn(b"tariq.baloch", res_view.data)
        self.assertIn(b"FTTH & Optical Link", res_view.data)

        # Statement view
        res_stmt = self.client.get(f"/customers/{self.cust_id}/statement")
        self.assertEqual(res_stmt.status_code, 200)
        self.assertIn(b"Account Statement", res_stmt.data)
        self.assertIn(b"Tariq Baloch", res_stmt.data)

        # Toggle customer status
        res_toggle = self.client.post(f"/customers/toggle_status/{self.cust_id}", follow_redirects=True)
        self.assertEqual(res_toggle.status_code, 200)

        conn = db.get_db()
        c = conn.execute("SELECT status FROM customers WHERE id = ?", (self.cust_id,)).fetchone()
        self.assertEqual(c["status"], "Suspended")
        # Toggle back to Active
        conn.execute("UPDATE customers SET status = 'Active' WHERE id = ?", (self.cust_id,))
        conn.commit()
        conn.close()

        self.logout()
        print("  [PASS] 06 - Customer 360° Profile, Statement & Status Control Verified.")

    # --------------------------------------------------------------------------
    # 7. FINANCIAL CASHBOOK & P&L
    # --------------------------------------------------------------------------
    def test_07_financial_cashbook(self):
        """Verify daily cashbook ledger, collections vs expenses, and CSV exports."""
        self.login_admin()

        res_cashbook = self.client.get("/financials/cashbook")
        self.assertEqual(res_cashbook.status_code, 200)
        self.assertIn(b"Daily Cashbook", res_cashbook.data)

        res_csv = self.client.get("/financials/cashbook/export")
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("text/csv", res_csv.headers["Content-Type"])

        self.logout()
        print("  [PASS] 07 - Financial Cashbook, Net Inflow & Accounting CSV Export Verified.")

    # --------------------------------------------------------------------------
    # 8. CUSTOMER SELF-SERVICE PORTAL
    # --------------------------------------------------------------------------
    def test_08_customer_self_service_portal(self):
        """Verify subscriber portal authentication, dashboard view, and ticket creation."""
        # 1. Unauthenticated subscriber login page
        res_login_page = self.client.get("/customer/login")
        self.assertEqual(res_login_page.status_code, 200)
        self.assertIn(b"Subscriber Portal Sign In", res_login_page.data)

        # 2. Login with Tariq Baloch's PPPoE credentials
        res_login = self.client.post("/customer/login", data={
            "username": "tariq.baloch",
            "password": "fiber123"
        }, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b"Tariq Baloch", res_login.data)
        self.assertIn(b"Subscriber Portal", res_login.data)

        # 3. Access customer dashboard
        res_dash = self.client.get("/customer/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"Invoices & Bills", res_dash.data)

        # 4. Submit support complaint from subscriber portal
        res_tck = self.client.post("/customer/tickets/new", data={
            "subject": "Red LOS Light on Router/ONU",
            "details": "Optical red light blinking since storm last night."
        }, follow_redirects=True)
        self.assertEqual(res_tck.status_code, 200)
        self.assertIn(b"submitted", res_tck.data)

        # Verify in DB
        conn = db.get_db()
        tck = conn.execute("SELECT * FROM tickets WHERE customer_id = ? ORDER BY id DESC LIMIT 1", (self.cust_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(tck)
        self.assertEqual(tck["subject"], "Red LOS Light on Router/ONU")

        # 5. Sign out of customer portal
        res_out = self.client.get("/customer/logout", follow_redirects=True)
        self.assertEqual(res_out.status_code, 200)
        self.assertIn(b"Subscriber Portal Sign In", res_out.data)

        print("  [PASS] 08 - Customer Self-Service Portal Auth, Bills & Complaint Dispatch Verified.")

if __name__ == "__main__":
    unittest.main()
