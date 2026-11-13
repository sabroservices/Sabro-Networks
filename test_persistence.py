import unittest
import os
import db
import app

class TestPersistenceAndResilience(unittest.TestCase):
    def test_storage_engine_detection(self):
        engine = db.get_storage_engine_name()
        self.assertIsInstance(engine, str)
        self.assertFalse(db.is_turso())

    def test_libsql_adapter_components(self):
        row = db.LibsqlRow(["id", "username", "role"], [1, "ahmedbaloch", "Admin"])
        self.assertEqual(row["username"], "ahmedbaloch")
        self.assertEqual(row[1], "ahmedbaloch")
        self.assertEqual(row.get("role"), "Admin")
        self.assertEqual(row.get("missing", "default"), "default")
        self.assertTrue("username" in row)
        self.assertEqual(row.keys(), ["id", "username", "role"])

    def test_standalone_error_templates_render_cleanly(self):
        with app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = 1
                sess["user_role"] = "Admin"
                sess["user_name"] = "ahmedbaloch"

            res_404 = client.get("/non_existent_route_404_test")
            self.assertEqual(res_404.status_code, 404)
            self.assertIn(b"404", res_404.data)
            self.assertIn(b"Endpoint Not Found", res_404.data)

            # Test 500 error handler directly
            with app.app.test_request_context():
                resp, code = app.internal_server_error(Exception("Test exception"))
                self.assertEqual(code, 500)
                html = resp.get_data(as_text=True) if hasattr(resp, "get_data") else str(resp)
                self.assertIn("500", html)
                self.assertIn("Temporary Operational Notice", html)

if __name__ == "__main__":
    unittest.main()
