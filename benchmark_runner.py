import time
import statistics
import concurrent.futures
import urllib.request
import urllib.parse
import http.cookiejar
import json
import sqlite3
import db
import app as flask_app

BASE_URL = "http://127.0.0.1:5000"

def get_authenticated_session(username, password):
    """Creates an authenticated urllib opener with session cookies."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    login_data = urllib.parse.urlencode({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/login", data=login_data, method="POST")
    opener.open(req)
    return opener

def measure_request(opener, url, method="GET", data=None):
    """Measures a single request duration in milliseconds."""
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, data=data, method=method)
        with opener.open(req, timeout=10) as resp:
            content = resp.read()
            dt = (time.perf_counter() - t0) * 1000.0
            return {
                "status": resp.status,
                "duration_ms": dt,
                "bytes": len(content),
                "error": None
            }
    except Exception as e:
        dt = (time.perf_counter() - t0) * 1000.0
        return {
            "status": getattr(e, "code", 500),
            "duration_ms": dt,
            "bytes": 0,
            "error": str(e)
        }

def run_endpoint_benchmark(name, opener, url, iterations=50):
    """Runs a series of requests to calculate statistical percentiles."""
    durations = []
    statuses = []
    sizes = []
    errors = 0

    for _ in range(iterations):
        res = measure_request(opener, url)
        durations.append(res["duration_ms"])
        statuses.append(res["status"])
        sizes.append(res["bytes"])
        if res["error"] or res["status"] >= 400:
            errors += 1

    durations.sort()
    p50 = statistics.median(durations)
    p95 = durations[int(len(durations) * 0.95)]
    p99 = durations[int(len(durations) * 0.99)]
    avg = statistics.mean(durations)
    stdev = statistics.stdev(durations) if len(durations) > 1 else 0.0

    return {
        "name": name,
        "url": url,
        "iterations": iterations,
        "avg_ms": round(avg, 2),
        "min_ms": round(min(durations), 2),
        "max_ms": round(max(durations), 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "stdev_ms": round(stdev, 2),
        "avg_bytes": int(statistics.mean(sizes)),
        "error_rate_pct": round((errors / iterations) * 100.0, 2)
    }

def run_concurrency_stress_test(opener, url, concurrency=25, total_requests=100):
    """Simulates simultaneous concurrent requests using a thread pool."""
    t_start = time.perf_counter()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(measure_request, opener, url) for _ in range(total_requests)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    total_time_s = time.perf_counter() - t_start
    durations = [r["duration_ms"] for r in results]
    durations.sort()
    errors = sum(1 for r in results if r["error"] or r["status"] >= 400)
    rps = total_requests / total_time_s if total_time_s > 0 else 0

    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "total_time_s": round(total_time_s, 3),
        "rps": round(rps, 1),
        "avg_ms": round(statistics.mean(durations), 2),
        "p50_ms": round(statistics.median(durations), 2),
        "p95_ms": round(durations[int(len(durations) * 0.95)], 2),
        "p99_ms": round(durations[int(len(durations) * 0.99)], 2),
        "min_ms": round(min(durations), 2),
        "max_ms": round(max(durations), 2),
        "error_count": errors,
        "error_rate_pct": round((errors / total_requests) * 100.0, 2)
    }

def run_database_benchmark():
    """Direct SQLite WAL mode latency and concurrency benchmark."""
    conn = db.get_db()
    
    # 1. Indexed lookup latency
    t0 = time.perf_counter()
    for _ in range(100):
        conn.execute("SELECT * FROM invoices WHERE customer_id = 1").fetchall()
    indexed_query_ms = ((time.perf_counter() - t0) / 100.0) * 1000.0

    # 2. Join query latency (Dashboard data)
    t0 = time.perf_counter()
    for _ in range(100):
        conn.execute("""
            SELECT t.*, c.full_name as customer_name, c.phone as customer_phone,
                   c.area as customer_area, c.db_box, c.fiber_core, u.full_name as tech_name
            FROM tickets t
            JOIN customers c ON t.customer_id = c.id
            LEFT JOIN users u ON t.assigned_user_id = u.id
            ORDER BY CASE WHEN t.priority = 'Critical' THEN 1 ELSE 2 END, t.id DESC
            LIMIT 50
        """).fetchall()
    join_query_ms = ((time.perf_counter() - t0) / 100.0) * 1000.0

    # 3. Write transaction commit speed in WAL mode
    t0 = time.perf_counter()
    for i in range(50):
        conn.execute("UPDATE settings SET value = ? WHERE key = 'app_version'", (f"v3.5.{i}",))
        conn.commit()
    write_commit_ms = ((time.perf_counter() - t0) / 50.0) * 1000.0

    conn.close()

    return {
        "indexed_lookup_ms": round(indexed_query_ms, 3),
        "dashboard_join_ms": round(join_query_ms, 3),
        "wal_write_commit_ms": round(write_commit_ms, 3)
    }

def main():
    print("=" * 70)
    print("  SABRO NETWORKS - PERFORMANCE BENCHMARKING & SLA ASSESSMENT")
    print("=" * 70)

    # 1. Authenticate sessions
    print("[1/5] Authenticating Admin session...")
    admin_opener = get_authenticated_session("admin", "admin123")
    public_opener = urllib.request.build_opener()

    # 2. Warm up
    print("[2/5] Warming up connection pool...")
    for _ in range(10):
        measure_request(admin_opener, f"{BASE_URL}/")

    # 3. Endpoint Latency Tests (50 iterations each)
    print("[3/5] Measuring endpoint latencies (p50, p95, p99, throughput)...")
    endpoints = [
        ("Login Page (Public)", public_opener, f"{BASE_URL}/login"),
        ("Public Digital Bill Slip (Clean)", public_opener, f"{BASE_URL}/invoice/1/print"),
        ("Admin FTTH Complaints Dashboard", admin_opener, f"{BASE_URL}/"),
        ("Customers & PPPoE Directory", admin_opener, f"{BASE_URL}/customers"),
        ("Invoices & Billing Ledger", admin_opener, f"{BASE_URL}/invoices"),
        ("Optical Tickets Queue", admin_opener, f"{BASE_URL}/tickets"),
        ("Staff & Logins Desk", admin_opener, f"{BASE_URL}/staff"),
        ("Daily Expenses (Kharcha)", admin_opener, f"{BASE_URL}/expenses"),
        ("Deposits & Advances", admin_opener, f"{BASE_URL}/deposits")
    ]

    endpoint_results = []
    for name, opener, url in endpoints:
        res = run_endpoint_benchmark(name, opener, url, iterations=40)
        endpoint_results.append(res)
        print(f"  [OK] {name:32} | Avg: {res['avg_ms']:5.1f}ms | p95: {res['p95_ms']:5.1f}ms | p99: {res['p99_ms']:5.1f}ms | {res['avg_bytes']/1024:4.1f} KB")

    # 4. Concurrency Stress Tests
    print("\n[4/5] Executing concurrency stress tests...")
    stress_10 = run_concurrency_stress_test(admin_opener, f"{BASE_URL}/", concurrency=10, total_requests=100)
    print(f"  [OK] 10 Workers (Normal Load)    | RPS: {stress_10['rps']:5.1f} | Avg: {stress_10['avg_ms']:5.1f}ms | p95: {stress_10['p95_ms']:5.1f}ms | Errors: {stress_10['error_rate_pct']}%")

    stress_25 = run_concurrency_stress_test(admin_opener, f"{BASE_URL}/", concurrency=25, total_requests=100)
    print(f"  [OK] 25 Workers (Peak Busy Hour) | RPS: {stress_25['rps']:5.1f} | Avg: {stress_25['avg_ms']:5.1f}ms | p95: {stress_25['p95_ms']:5.1f}ms | Errors: {stress_25['error_rate_pct']}%")

    stress_50 = run_concurrency_stress_test(public_opener, f"{BASE_URL}/invoice/1/print", concurrency=50, total_requests=150)
    print(f"  [OK] 50 Workers (Bill Slip Spike)| RPS: {stress_50['rps']:5.1f} | Avg: {stress_50['avg_ms']:5.1f}ms | p95: {stress_50['p95_ms']:5.1f}ms | Errors: {stress_50['error_rate_pct']}%")

    # 5. Database Performance
    print("\n[5/5] Benchmarking SQLite WAL database engine...")
    db_metrics = run_database_benchmark()
    print(f"  [OK] Indexed Customer Lookup  : {db_metrics['indexed_lookup_ms']:.3f} ms / query")
    print(f"  [OK] Multi-Table Join Query   : {db_metrics['dashboard_join_ms']:.3f} ms / query")
    print(f"  [OK] WAL Commit Transaction   : {db_metrics['wal_write_commit_ms']:.3f} ms / commit")

    # Output full JSON summary for reporting
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoints": endpoint_results,
        "concurrency_tests": {
            "normal_load_10": stress_10,
            "peak_load_25": stress_25,
            "spike_bill_print_50": stress_50
        },
        "database": db_metrics
    }

    with open("performance_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\nBenchmark complete! Results written to performance_benchmark_results.json")

if __name__ == "__main__":
    main()
