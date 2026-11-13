import base64
import sqlite3
import os
import secrets
import urllib.parse
import re
import csv
import io
import tempfile
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response, send_file, g
from werkzeug.security import generate_password_hash, check_password_hash
import db
import dealer_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)
# Cryptographically secure session key & cookie policies
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

# Ensure DB initialized
db.init_db(force_reset=False)

@app.teardown_appcontext
def close_db_connection(exception=None):
    """Ensures request-bound database connection is cleanly closed to prevent connection leaks."""
    db_conn = g.pop('db_conn', None)
    if db_conn is not None:
        try:
            db_conn.close()
        except Exception:
            pass


def get_settings():
    conn = db.get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    settings_dict = {r["key"]: r["value"] for r in rows}
    settings_dict.setdefault("isp_name", "Sabro Networks")
    settings_dict.setdefault("tagline", "FTTH High-Speed Fiber Internet")
    settings_dict.setdefault("agency_name", "Vshatkay Solutions")
    settings_dict.setdefault("agency_tagline", "Software Engineering & Telecom Solutions Agency")
    settings_dict.setdefault("agency_url", "https://vshatkaysolutions.com")
    settings_dict.setdefault("currency", "PKR")
    settings_dict.setdefault("phone", "")
    settings_dict.setdefault("business_whatsapp", "")
    settings_dict.setdefault("email", "")
    settings_dict.setdefault("address", "")
    settings_dict.setdefault("jazzcash_no", "")
    settings_dict.setdefault("easypaisa_no", "")
    settings_dict.setdefault("bank_info", "")
    return settings_dict

def resolve_tariff_id(conn, raw_tariff_id):
    """Returns a valid tariff ID from DB or None when packages are empty or unselected."""
    if not raw_tariff_id:
        return None
    try:
        tid = int(raw_tariff_id)
    except (ValueError, TypeError):
        return None
    row = conn.execute("SELECT id FROM tariffs WHERE id = ?", (tid,)).fetchone()
    return row["id"] if row else None

def clean_whatsapp_phone(phone_str):
    """Formats local Pakistani / international phone numbers to digits-only 923xxxxxxxxx for WhatsApp API."""
    if not phone_str:
        return ""
    digits = re.sub(r'\D', '', str(phone_str))
    if not digits:
        return ""
    if digits.startswith('0092'):
        digits = digits[2:]
    elif digits.startswith('92'):
        pass
    elif digits.startswith('0') and len(digits) >= 10:
        digits = '92' + digits[1:]
    elif len(digits) == 10 and digits.startswith('3'):
        digits = '92' + digits
    if digits.startswith('920') and len(digits) == 13:
        digits = '92' + digits[3:]
    return digits

def generate_unique_invoice_number(conn, customer_id, suffix=""):
    """Generates a collision-proof unique invoice number across all creation vectors."""
    year_month = datetime.now().strftime('%Y%m')
    base = f"INV-{year_month}-{customer_id:04d}"
    candidate = f"{base}-{suffix}" if suffix else base
    seq = 1
    while conn.execute("SELECT 1 FROM invoices WHERE invoice_number = ?", (candidate,)).fetchone():
        candidate = f"{base}-{suffix}{seq}" if suffix else f"{base}-{seq}"
        seq += 1
    return candidate

def generate_unique_ticket_number(conn):
    """Generates a collision-proof unique ticket number even if prior tickets were pruned."""
    year = datetime.now().strftime('%Y')
    count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] + 1
    candidate = f"TCK-{year}-{count:03d}"
    while conn.execute("SELECT 1 FROM tickets WHERE ticket_number = ?", (candidate,)).fetchone():
        count += 1
        candidate = f"TCK-{year}-{count:03d}"
    return candidate

ALLOWED_PFP_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

def calculate_technician_level(resolved_count, xp=None):
    """
    Gamified leveling system for FTTH Field Technicians (Complaint Boys):
    Level 1: Apprentice Splicer (0-4 tickets)
    Level 2: Field Technician (5-14 tickets)
    Level 3: Senior Fiber Tech (15-29 tickets)
    Level 4: Master Fiber Splicer (30-49 tickets)
    Level 5: Optical NOC Elite (50+ tickets)
    """
    resolved_count = max(0, int(resolved_count or 0))
    if resolved_count < 5:
        lvl = 1
        title = "Apprentice Splicer"
        badge_color = "secondary"
        current_req = 0
        next_req = 5
        icon = "bi-tools"
    elif resolved_count < 15:
        lvl = 2
        title = "Field Technician"
        badge_color = "info"
        current_req = 5
        next_req = 15
        icon = "bi-lightning-charge-fill"
    elif resolved_count < 30:
        lvl = 3
        title = "Senior Fiber Tech"
        badge_color = "warning"
        current_req = 15
        next_req = 30
        icon = "bi-award-fill"
    elif resolved_count < 50:
        lvl = 4
        title = "Master Fiber Splicer"
        badge_color = "danger"
        current_req = 30
        next_req = 50
        icon = "bi-fire"
    else:
        lvl = 5
        title = "Optical NOC Elite"
        badge_color = "success"
        current_req = 50
        next_req = 50
        icon = "bi-trophy-fill"

    if lvl == 5:
        progress_pct = 100
        tickets_to_next = 0
    else:
        progress_pct = int(((resolved_count - current_req) / (next_req - current_req)) * 100)
        tickets_to_next = next_req - resolved_count

    calculated_xp = (resolved_count * 120) if xp is None or xp == 0 else xp

    next_tier_titles = {
        1: "Field Technician",
        2: "Senior Fiber Tech",
        3: "Master Fiber Splicer",
        4: "Optical NOC Elite",
        5: "Max Tier"
    }
    next_tier_title = next_tier_titles.get(lvl, "Next Tier")

    return {
        "level": lvl,
        "title": title,
        "badge_color": badge_color,
        "icon": icon,
        "resolved_count": resolved_count,
        "progress_pct": min(100, max(0, progress_pct)),
        "needed_for_next": tickets_to_next,
        "tickets_to_next": tickets_to_next,
        "next_level_req": next_req,
        "next_tier_title": next_tier_title,
        "xp": calculated_xp,
        "is_max": (lvl >= 5)
    }

def get_user_avatar(user_dict_or_row):
    """Returns avatar URL: persistent base64 data URI, external URL, local file, or role SVG."""
    if not user_dict_or_row:
        return url_for('static', filename='img/avatar_admin.svg')
    
    pfp = ""
    role = ""
    if isinstance(user_dict_or_row, dict):
        pfp = user_dict_or_row.get("pfp_image", "")
        role = user_dict_or_row.get("role", "")
    else:
        try:
            pfp = user_dict_or_row["pfp_image"] if "pfp_image" in user_dict_or_row.keys() else ""
            role = user_dict_or_row["role"] if "role" in user_dict_or_row.keys() else ""
        except Exception:
            pass

    if pfp:
        # 1. Base64 Data URI or external URL (100% persistent across Render container restarts)
        if pfp.startswith("data:image/") or pfp.startswith("http://") or pfp.startswith("https://"):
            return pfp
        # 2. Local relative filesystem path
        full_path = os.path.join(app.root_path, "static", pfp.replace("/", os.sep))
        if os.path.exists(full_path):
            return url_for('static', filename=pfp)

    if role == "Complaint Boy":
        return url_for('static', filename='img/avatar_complaint.svg')
    elif role == "Recovery Boy":
        return url_for('static', filename='img/avatar_recovery.svg')
    return url_for('static', filename='img/avatar_admin.svg')

def save_pfp_upload(file_storage, user_id):
    """
    Saves uploaded PFP image:
      - Validates extension and file size.
      - Saves to static/uploads/pfp/ and returns relative path ('uploads/pfp/...').
      - Compatible with persistent disks, S3-compatible cloud storage, and local serving.
    """
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext not in ALLOWED_PFP_EXTENSIONS:
        return None
    
    try:
        raw_bytes = file_storage.read()
        if not raw_bytes or len(raw_bytes) > 2 * 1024 * 1024:  # max 2MB
            return None
        
        upload_dir = os.path.join(app.root_path, "static", "uploads", "pfp")
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"pfp_{user_id}_{int(datetime.now().timestamp())}.{ext}"
        dest_path = os.path.join(upload_dir, filename)
        with open(dest_path, "wb") as f:
            f.write(raw_bytes)
        
        return f"uploads/pfp/{filename}"
    except Exception as e:
        print(f"[PFP UPLOAD ERROR]: {e}")
        return None

@app.context_processor
def inject_globals():
    settings = get_settings()
    current_user = None
    if "user_id" in session:
        uid = session.get("user_id")
        role = session.get("user_role")
        pfp_image = ""
        tech_xp = 0
        resolved_count = 0
        try:
            conn = db.get_db()
            row = conn.execute("SELECT pfp_image, technician_xp FROM users WHERE id = ?", (uid,)).fetchone()
            if row:
                if "pfp_image" in row.keys() and row["pfp_image"]:
                    pfp_image = row["pfp_image"]
                if "technician_xp" in row.keys() and row["technician_xp"]:
                    tech_xp = row["technician_xp"]
            if role == "Complaint Boy":
                resolved_count = conn.execute(
                    "SELECT COUNT(*) FROM tickets WHERE assigned_user_id = ? AND status = 'Resolved'",
                    (uid,)
                ).fetchone()[0]
            conn.close()
        except Exception:
            pass

        user_dict = {
            "id": uid,
            "name": session.get("user_name"),
            "username": session.get("username"),
            "role": role,
            "area": session.get("user_area"),
            "pfp_image": pfp_image,
            "technician_xp": tech_xp
        }
        user_dict["avatar_url"] = get_user_avatar(user_dict)
        if role == "Complaint Boy":
            user_dict["level_info"] = calculate_technician_level(resolved_count, tech_xp)
        else:
            user_dict["level_info"] = None
        current_user = user_dict

    return dict(
        settings=settings,
        now_year=datetime.now().year,
        current_user=current_user,
        clean_whatsapp_phone=clean_whatsapp_phone,
        get_user_avatar=get_user_avatar,
        calculate_technician_level=calculate_technician_level
    )

@app.before_request
def require_login():
    # Allow login, static files, and public invoice print views without authentication
    allowed_endpoints = ['login', 'static', 'print_invoice', 'health_diagnostic']
    if request.endpoint not in allowed_endpoints and not session.get('user_id'):
        return redirect(url_for('login'))

@app.after_request
def add_performance_and_security_headers(response):
    """Blistering-fast browser caching for static assets & security headers."""
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
    else:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

def role_required(*allowed_roles):
    """Enforces that current user belongs to one of allowed roles or is Admin."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login"))
            role = session.get("user_role")
            if role != "Admin" and role not in allowed_roles:
                flash(f"Access Denied: Only Admin or {', '.join(allowed_roles)} can access this section.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_only(f):
    """Restricts route exclusively to Admin users."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        role = session.get("user_role")
        if role != "Admin":
            flash("Access Denied: Only Admin has full access to this section.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function

# ================= AUTHENTICATION (LOGIN / LOGOUT) =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = db.get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ? AND status = 'Active'",
                            (username,)).fetchone()

        is_authenticated = False
        if user:
            # 1. Direct match (covers legacy plaintext records and raw test submissions)
            if user["password"] == password:
                is_authenticated = True
            else:
                # 2. Cryptographic hash verification (Werkzeug scrypt / pbkdf2)
                try:
                    if check_password_hash(user["password"], password):
                        is_authenticated = True
                except Exception:
                    pass

        if is_authenticated:
            # Upgrade legacy plaintext password to secure hash upon successful login
            if user["password"] == password and not (password.startswith("scrypt:") or password.startswith("pbkdf2:")):
                try:
                    new_hash = generate_password_hash(password)
                    conn.execute("UPDATE users SET password = ? WHERE id = ?", (new_hash, user["id"]))
                    conn.commit()
                except Exception:
                    pass

            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            session["username"] = user["username"]
            session["user_role"] = user["role"]
            session["user_area"] = user["assigned_area"]
            conn.close()
            flash(f"Welcome back, {user['full_name']}! Logged in as {user['role']}.", "success")
            return redirect(url_for("dashboard"))
        else:
            conn.close()
            flash("Invalid username or password. Please try again.", "danger")

    return render_template("login.html")

@app.route("/health")
def health_diagnostic():
    login_path = os.path.join(app.template_folder, "login.html")
    templates_list = os.listdir(app.template_folder) if os.path.exists(app.template_folder) else []
    return {
        "status": "online",
        "system": "Sabro Networks FTTH",
        "base_dir": BASE_DIR,
        "template_folder": app.template_folder,
        "templates_found": len(templates_list),
        "login_html_exists": os.path.exists(login_path)
    }

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("login"))

# ================= DASHBOARD =================
@app.route("/dashboard")
@app.route("/")
def dashboard():
    user_id = session.get("user_id")
    user_role = session.get("user_role")
    user_area = session.get("user_area")
    conn = db.get_db()

    # 1. Recovery Boy Desk (Only recovery data, zero company financials)
    if user_role == "Recovery Boy":
        my_collections_sum = conn.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE collected_by_staff_id = ? AND status = 'Paid'
        """, (user_id,)).fetchone()[0]

        my_collections_count = conn.execute("""
            SELECT COUNT(*) FROM invoices WHERE collected_by_staff_id = ? AND status = 'Paid'
        """, (user_id,)).fetchone()[0]

        recent_my_collections = conn.execute("""
            SELECT i.*, c.full_name, c.pppoe_username, c.phone, c.address, c.area
            FROM invoices i
            JOIN customers c ON i.customer_id = c.id
            WHERE i.collected_by_staff_id = ? AND i.status = 'Paid'
            ORDER BY i.id DESC LIMIT 8
        """, (user_id,)).fetchall()

        if user_area:
            pending_invoices = conn.execute("""
                SELECT i.*, c.full_name, c.pppoe_username, c.phone, c.address, c.area, c.db_box, t.name as plan_name
                FROM invoices i
                JOIN customers c ON i.customer_id = c.id
                LEFT JOIN tariffs t ON c.tariff_id = t.id
                WHERE i.status IN ('Unpaid', 'Overdue') AND c.area LIKE ?
                ORDER BY i.id DESC LIMIT 30
            """, (f"%{user_area}%",)).fetchall()

            pending_sum = conn.execute("""
                SELECT COALESCE(SUM(i.amount), 0) FROM invoices i
                JOIN customers c ON i.customer_id = c.id
                WHERE i.status IN ('Unpaid', 'Overdue') AND c.area LIKE ?
            """, (f"%{user_area}%",)).fetchone()[0]

            pending_count = conn.execute("""
                SELECT COUNT(*) FROM invoices i
                JOIN customers c ON i.customer_id = c.id
                WHERE i.status IN ('Unpaid', 'Overdue') AND c.area LIKE ?
            """, (f"%{user_area}%",)).fetchone()[0]
        else:
            pending_invoices = conn.execute("""
                SELECT i.*, c.full_name, c.pppoe_username, c.phone, c.address, c.area, c.db_box, t.name as plan_name
                FROM invoices i
                JOIN customers c ON i.customer_id = c.id
                LEFT JOIN tariffs t ON c.tariff_id = t.id
                WHERE i.status IN ('Unpaid', 'Overdue')
                ORDER BY i.id DESC LIMIT 30
            """).fetchall()

            pending_sum = conn.execute("""
                SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status IN ('Unpaid', 'Overdue')
            """).fetchone()[0]

            pending_count = conn.execute("""
                SELECT COUNT(*) FROM invoices WHERE status IN ('Unpaid', 'Overdue')
            """).fetchone()[0]

        conn.close()
        return render_template("dashboard.html",
                               my_collections_sum=my_collections_sum,
                               my_collections_count=my_collections_count,
                               recent_my_collections=recent_my_collections,
                               pending_invoices=pending_invoices,
                               pending_sum=pending_sum,
                               pending_count=pending_count)

    # 2. Complaint Boy Desk (Only technical complaints & line data, zero billing/financials)
    elif user_role == "Complaint Boy":
        my_assigned_tickets = conn.execute("""
            SELECT t.*, c.full_name as customer_name, c.phone as customer_phone, c.address, c.area,
                   c.pppoe_username, c.db_box, c.fiber_core, c.onu_serial
            FROM tickets t
            JOIN customers c ON t.customer_id = c.id
            WHERE t.assigned_user_id = ? AND t.status != 'Resolved'
            ORDER BY t.id DESC
        """, (user_id,)).fetchall()

        my_resolved_count = conn.execute("""
            SELECT COUNT(*) FROM tickets WHERE assigned_user_id = ? AND status = 'Resolved'
        """, (user_id,)).fetchone()[0]

        if user_area:
            open_field_tickets = conn.execute("""
                SELECT t.*, c.full_name as customer_name, c.phone as customer_phone, c.address, c.area,
                       c.pppoe_username, c.db_box, c.fiber_core, c.onu_serial
                FROM tickets t
                JOIN customers c ON t.customer_id = c.id
                WHERE t.status = 'Open' AND (t.assigned_user_id IS NULL OR t.assigned_user_id != ?) AND c.area LIKE ?
                ORDER BY t.id DESC LIMIT 15
            """, (user_id, f"%{user_area}%")).fetchall()
        else:
            open_field_tickets = conn.execute("""
                SELECT t.*, c.full_name as customer_name, c.phone as customer_phone, c.address, c.area,
                       c.pppoe_username, c.db_box, c.fiber_core, c.onu_serial
                FROM tickets t
                JOIN customers c ON t.customer_id = c.id
                WHERE t.status = 'Open' AND (t.assigned_user_id IS NULL OR t.assigned_user_id != ?)
                ORDER BY t.id DESC LIMIT 15
            """, (user_id,)).fetchall()

        recent_resolved_tickets = conn.execute("""
            SELECT t.*, c.full_name as customer_name, c.phone as customer_phone, c.area, c.address
            FROM tickets t
            JOIN customers c ON t.customer_id = c.id
            WHERE t.assigned_user_id = ? AND t.status = 'Resolved'
            ORDER BY t.resolved_at DESC LIMIT 5
        """, (user_id,)).fetchall()

        u_row = conn.execute("SELECT technician_xp FROM users WHERE id = ?", (user_id,)).fetchone()
        tech_xp = u_row["technician_xp"] if u_row else 0
        tech_level_info = calculate_technician_level(my_resolved_count, tech_xp)
        conn.close()
        return render_template("dashboard.html",
                               my_assigned_tickets=my_assigned_tickets,
                               my_assigned_count=len(my_assigned_tickets),
                               my_resolved_count=my_resolved_count,
                               open_field_tickets=open_field_tickets,
                               recent_resolved_tickets=recent_resolved_tickets,
                               tech_level_info=tech_level_info)

    # 3. Admin Executive Master Dashboard (Full business financial & operations access)
    else:
        total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        active_customers = conn.execute("SELECT COUNT(*) FROM customers WHERE status = 'Active'").fetchone()[0]
        expired_customers = conn.execute("SELECT COUNT(*) FROM customers WHERE status = 'Expired'").fetchone()[0]
        suspended_customers = conn.execute("SELECT COUNT(*) FROM customers WHERE status = 'Suspended'").fetchone()[0]
        
        paid_sum = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status = 'Paid'").fetchone()[0]
        unpaid_sum = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status IN ('Unpaid', 'Overdue')").fetchone()[0]
        unpaid_count = conn.execute("SELECT COUNT(*) FROM invoices WHERE status IN ('Unpaid', 'Overdue')").fetchone()[0]
        
        total_expenses = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses").fetchone()[0]
        net_profit = paid_sum - total_expenses
        total_investments = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM investments").fetchone()[0]
        total_deposits = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE status = 'Held'").fetchone()[0]
        
        total_staff = conn.execute("SELECT COUNT(*) FROM users WHERE role != 'Admin'").fetchone()[0]
        open_tickets = conn.execute("SELECT COUNT(*) FROM tickets WHERE status != 'Resolved'").fetchone()[0]
        
        recent_invoices = conn.execute("""
            SELECT i.*, c.full_name, c.pppoe_username, c.phone, u.full_name as collector_name
            FROM invoices i
            JOIN customers c ON i.customer_id = c.id
            LEFT JOIN users u ON i.collected_by_staff_id = u.id
            ORDER BY i.id DESC LIMIT 6
        """).fetchall()

        recent_expenses = conn.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 5").fetchall()

        expiring_customers = conn.execute("""
            SELECT c.*, t.name as plan_name, t.speed_mb, t.price
            FROM customers c
            LEFT JOIN tariffs t ON c.tariff_id = t.id
            WHERE c.status != 'Active' OR date(c.expiry_date) <= date('now', '+7 days')
            ORDER BY c.expiry_date ASC LIMIT 6
        """).fetchall()

        tariff_stats = conn.execute("""
            SELECT t.name, t.price, COUNT(c.id) as user_count 
            FROM tariffs t
            LEFT JOIN customers c ON c.tariff_id = t.id
            GROUP BY t.id
        """).fetchall()

        # Comprehensive FTTH Complaints, Outages & Technician Dispatch
        all_active_complaints = conn.execute("""
            SELECT t.*, c.full_name as customer_name, c.phone as customer_phone, c.area, c.address,
                   c.pppoe_username, c.db_box, c.fiber_core, c.onu_serial,
                   u.full_name as tech_name, u.phone as tech_phone
            FROM tickets t
            JOIN customers c ON t.customer_id = c.id
            LEFT JOIN users u ON t.assigned_user_id = u.id
            WHERE t.status != 'Resolved'
            ORDER BY CASE t.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, t.id DESC
        """).fetchall()

        # Defaulters / Customers who have not paid money
        defaulters_list = conn.execute("""
            SELECT i.*, c.full_name, c.pppoe_username, c.phone, c.area, c.address, c.db_box, t.name as plan_name,
                   CAST((julianday('now') - julianday(i.due_date)) AS INTEGER) as overdue_days
            FROM invoices i
            JOIN customers c ON i.customer_id = c.id
            LEFT JOIN tariffs t ON c.tariff_id = t.id
            WHERE i.status IN ('Unpaid', 'Overdue')
            ORDER BY i.amount DESC, i.id DESC
            LIMIT 20
        """).fetchall()

        recent_tickets = all_active_complaints[:6]

        tech_rows = conn.execute("""
            SELECT id, full_name, phone, role, assigned_area, pfp_image FROM users WHERE status = 'Active' AND role IN ('Complaint Boy', 'Staff', 'Admin') ORDER BY full_name ASC
        """).fetchall()
        all_technicians = []
        for tr in tech_rows:
            td = dict(tr)
            td["avatar_url"] = get_user_avatar(td)
            all_technicians.append(td)

        all_active_cust_list = conn.execute("""
            SELECT id, full_name, pppoe_username, phone, area, db_box, fiber_core FROM customers WHERE status = 'Active' ORDER BY full_name ASC
        """).fetchall()

        critical_complaints_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status != 'Resolved' AND priority = 'Critical'").fetchone()[0]
        open_complaints_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Open'").fetchone()[0]
        in_progress_complaints_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'In Progress'").fetchone()[0]
        resolved_today_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Resolved' AND date(resolved_at) = date('now')").fetchone()[0]

        conn.close()

        return render_template("dashboard.html",
                               total_customers=total_customers,
                               active_customers=active_customers,
                               expired_customers=expired_customers,
                               suspended_customers=suspended_customers,
                               paid_sum=paid_sum,
                               unpaid_sum=unpaid_sum,
                               unpaid_count=unpaid_count,
                               total_expenses=total_expenses,
                               net_profit=net_profit,
                               total_investments=total_investments,
                               total_deposits=total_deposits,
                               total_staff=total_staff,
                               open_tickets=open_tickets,
                               recent_invoices=recent_invoices,
                               recent_expenses=recent_expenses,
                               expiring_customers=expiring_customers,
                               tariff_stats=tariff_stats,
                               recent_tickets=recent_tickets,
                               defaulters_list=defaulters_list,
                               all_active_complaints=all_active_complaints,
                               all_technicians=all_technicians,
                               all_active_cust_list=all_active_cust_list,
                               critical_complaints_count=critical_complaints_count,
                               open_complaints_count=open_complaints_count,
                               in_progress_complaints_count=in_progress_complaints_count,
                               resolved_today_count=resolved_today_count)

# ================= CUSTOMERS (ADD & FULL EDIT) =================
@app.route("/customers")
def customers_list():
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    payment_status = request.args.get("payment", "").strip()
    
    conn = db.get_db()
    query = """
        SELECT c.*, t.name as plan_name, t.price as plan_price, t.speed_mb,
               (SELECT i.status FROM invoices i WHERE i.customer_id = c.id ORDER BY i.id DESC LIMIT 1) as latest_bill_status,
               (SELECT i.id FROM invoices i WHERE i.customer_id = c.id ORDER BY i.id DESC LIMIT 1) as latest_invoice_id
        FROM customers c
        LEFT JOIN tariffs t ON c.tariff_id = t.id
        WHERE 1=1
    """
    params = []
    if search:
        query += " AND (c.full_name LIKE ? OR c.pppoe_username LIKE ? OR c.phone LIKE ? OR c.address LIKE ? OR c.area LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term, term])
    
    if status_filter:
        query += " AND c.status = ?"
        params.append(status_filter)
        
    query += " ORDER BY c.id DESC"
    all_customers = conn.execute(query, params).fetchall()
    
    if payment_status:
        customers = [c for c in all_customers if (c['latest_bill_status'] or 'Unpaid') == payment_status]
    else:
        customers = all_customers

    tariffs = conn.execute("SELECT * FROM tariffs ORDER BY price ASC").fetchall()
    conn.close()

    return render_template("customers.html", customers=customers, tariffs=tariffs, 
                           search=search, status_filter=status_filter, payment_status=payment_status)

@app.route("/customers/add", methods=["POST"])
@admin_only
def add_customer():
    full_name = (request.form.get("full_name") or "").strip()
    pppoe_username = (request.form.get("pppoe_username") or "").strip()
    password = (request.form.get("password") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    address = (request.form.get("address") or "").strip()
    area = (request.form.get("area") or "").strip()
    raw_tariff_id = request.form.get("tariff_id")
    try:
        days = int(request.form.get("days", 30) or 30)
    except (ValueError, TypeError):
        days = 30
    initial_payment = request.form.get("initial_payment", "Unpaid")
    try:
        onu_deposit = max(0.0, float(request.form.get("onu_deposit", 0) or 0))
    except (ValueError, TypeError):
        onu_deposit = 0.0

    if not full_name or not pppoe_username or not password:
        flash("Customer name, PPPoE username, and password are required.", "danger")
        return redirect(url_for("customers_list"))
    
    # FTTH Carrier Details (stored clean without synthetic placeholders)
    onu_serial = (request.form.get("onu_serial") or "").strip()
    db_box = (request.form.get("db_box") or "").strip()
    fiber_core = (request.form.get("fiber_core") or "").strip() or "Core 1 (Blue)"
    cnic = (request.form.get("cnic") or "").strip()
    installation_date = (request.form.get("installation_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")

    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    created_at = datetime.now().strftime("%Y-%m-%d")

    conn = db.get_db()
    try:
        tariff_id = resolve_tariff_id(conn, raw_tariff_id)
        conn.execute("""
            INSERT INTO customers (full_name, pppoe_username, password, phone, address, area, tariff_id, status, expiry_date, 
                                   onu_serial, db_box, fiber_core, cnic, installation_date, created_at)
            VALUES (?,?,?,?,?,?,?, 'Active', ?, ?, ?, ?, ?, ?, ?)
        """, (full_name, pppoe_username, password, phone, address, area, tariff_id, expiry_date,
              onu_serial, db_box, fiber_core, cnic, installation_date, created_at))
        cust_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        tariff = conn.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,)).fetchone() if tariff_id else None
        if tariff:
            inv_number = generate_unique_invoice_number(conn, cust_id)
            is_paid = (initial_payment == "Paid")
            paid_date = created_at if is_paid else None
            conn.execute("""
                INSERT INTO invoices (invoice_number, customer_id, amount, month_period, status, due_date, paid_date, payment_method, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (inv_number, cust_id, tariff['price'], datetime.now().strftime("%B %Y"),
                  'Paid' if is_paid else 'Unpaid', expiry_date, paid_date, 'Cash' if is_paid else None, created_at))

        if onu_deposit > 0:
            conn.execute("""
                INSERT INTO deposits (customer_id, deposit_type, amount, status, date, notes, created_at)
                VALUES (?, 'ONU Security Deposit', ?, 'Held', ?, 'New Connection Device Security', ?)
            """, (cust_id, onu_deposit, created_at, created_at))

        conn.commit()
        flash(f"Customer '{full_name}' (@{pppoe_username}) registered successfully! Connection is Active.", "success")
    except Exception as e:
        flash(f"Error adding customer: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("customers_list"))

@app.route("/customers/edit/<int:id>", methods=["POST"])
@admin_only
def edit_customer(id):
    full_name = (request.form.get("full_name") or "").strip()
    pppoe_username = (request.form.get("pppoe_username") or "").strip()
    password = (request.form.get("password") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    address = (request.form.get("address") or "").strip()
    area = (request.form.get("area") or "").strip()
    raw_tariff_id = request.form.get("tariff_id")
    status = request.form.get("status", "Active")
    expiry_date = request.form.get("expiry_date")
    
    # FTTH Carrier Details
    onu_serial = (request.form.get("onu_serial") or "").strip()
    db_box = (request.form.get("db_box") or "").strip()
    fiber_core = (request.form.get("fiber_core") or "").strip()
    cnic = (request.form.get("cnic") or "").strip()
    installation_date = (request.form.get("installation_date") or "").strip()

    conn = db.get_db()
    tariff_id = resolve_tariff_id(conn, raw_tariff_id)
    cust = conn.execute("SELECT id FROM customers WHERE id = ?", (id,)).fetchone()
    if not cust:
        conn.close()
        flash("Customer not found.", "danger")
        return redirect(url_for("customers_list"))

    if not full_name or not pppoe_username or not password:
        conn.close()
        flash("Customer name, PPPoE username, and password are required.", "danger")
        return redirect(url_for("customers_list"))

    try:
        conn.execute("""
            UPDATE customers 
            SET full_name = ?, pppoe_username = ?, password = ?, phone = ?, address = ?, area = ?, tariff_id = ?, status = ?, expiry_date = ?,
                onu_serial = ?, db_box = ?, fiber_core = ?, cnic = ?, installation_date = ?
            WHERE id = ?
        """, (full_name, pppoe_username, password, phone, address, area, tariff_id, status, expiry_date,
              onu_serial, db_box, fiber_core, cnic, installation_date, id))
        conn.commit()
        flash(f"Customer '{full_name}' (@{pppoe_username}) details updated successfully!", "success")
    except Exception as e:
        flash(f"Error updating customer: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("customers_list"))

@app.route("/customers/renew/<int:id>", methods=["POST"])
@admin_only
def renew_customer(id):
    try:
        days = int(request.form.get("days", 30) or 30)
    except (ValueError, TypeError):
        days = 30
    conn = db.get_db()
    cust = conn.execute("SELECT * FROM customers WHERE id = ?", (id,)).fetchone()
    if not cust:
        conn.close()
        flash("Customer not found.", "danger")
        return redirect(url_for("customers_list"))

    current_exp = cust['expiry_date']
    try:
        curr_dt = datetime.strptime(current_exp, "%Y-%m-%d")
        base_date = max(curr_dt, datetime.now())
    except Exception:
        base_date = datetime.now()
        
    new_exp = (base_date + timedelta(days=days)).strftime("%Y-%m-%d")
    conn.execute("UPDATE customers SET status = 'Active', expiry_date = ? WHERE id = ?", (new_exp, id))
    
    tariff = conn.execute("SELECT * FROM tariffs WHERE id = ?", (cust['tariff_id'],)).fetchone()
    if tariff:
        inv_num = generate_unique_invoice_number(conn, id, suffix='R')
        conn.execute("""
            INSERT INTO invoices (invoice_number, customer_id, amount, month_period, status, due_date, paid_date, payment_method, created_at)
            VALUES (?, ?, ?, ?, 'Paid', ?, ?, 'Cash', ?)
        """, (inv_num, id, tariff['price'], datetime.now().strftime("%B %Y"), new_exp, datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d")))
    
    conn.commit()
    flash(f"Customer '{cust['full_name']}' (@{cust['pppoe_username']}) renewed for {days} days until {new_exp}!", "success")
    conn.close()
    return redirect(url_for("customers_list"))

@app.route("/customers/toggle_status/<int:id>", methods=["POST"])
@admin_only
def toggle_customer_status(id):
    conn = db.get_db()
    cust = conn.execute("SELECT * FROM customers WHERE id = ?", (id,)).fetchone()
    if not cust:
        conn.close()
        flash("Customer not found.", "danger")
        return redirect(url_for("customers_list"))

    new_status = "Suspended" if cust["status"] == "Active" else "Active"
    conn.execute("UPDATE customers SET status = ? WHERE id = ?", (new_status, id))
    conn.commit()
    flash(f"Subscriber '{cust['pppoe_username']}' status set to {new_status}.", "warning")
    conn.close()
    return redirect(url_for("customers_list"))

@app.route("/customers/delete/<int:id>", methods=["POST"])
@admin_only
def delete_customer(id):
    force = request.form.get('force') in ['1', 'true', 'True']
    conn = db.get_db()
    cust = conn.execute("SELECT id, pppoe_username FROM customers WHERE id = ?", (id,)).fetchone()
    if not cust:
        conn.close()
        flash("Customer not found.", "danger")
        return redirect(url_for("customers_list"))

    paid_invoices_count = conn.execute(
        "SELECT COUNT(*) FROM invoices WHERE customer_id = ? AND status = 'Paid'", (id,)
    ).fetchone()[0]

    if paid_invoices_count > 0 and not force:
        # Prevent wiping accounting records; soft-suspend instead
        conn.execute("UPDATE customers SET status = 'Suspended' WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        flash(f"Cannot permanently delete subscriber '{cust['pppoe_username']}' because they have {paid_invoices_count} paid invoice(s). Status has been set to Suspended to preserve company financial history.", "warning")
        return redirect(url_for("customers_list"))

    conn.execute("DELETE FROM invoices WHERE customer_id = ?", (id,))
    conn.execute("DELETE FROM deposits WHERE customer_id = ?", (id,))
    conn.execute("DELETE FROM tickets WHERE customer_id = ?", (id,))
    conn.execute("DELETE FROM customers WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash(f"Customer '{cust['pppoe_username']}' record deleted.", "info")
    return redirect(url_for("customers_list"))

# ================= BILLING & INVOICES (PAID, UNPAID, EDIT) =================
@app.route("/invoices")
@role_required("Recovery Boy")
def invoices_list():
    filter_status = request.args.get("status", "")
    user_id = session.get("user_id")
    user_role = session.get("user_role")
    
    conn = db.get_db()
    query = """
        SELECT i.*, c.full_name, c.pppoe_username, c.phone, c.address, c.area, c.onu_serial, c.db_box,
               t.name as plan_name, t.speed_mb, u.full_name as collector_name
        FROM invoices i
        JOIN customers c ON i.customer_id = c.id
        LEFT JOIN tariffs t ON c.tariff_id = t.id
        LEFT JOIN users u ON i.collected_by_staff_id = u.id
        WHERE 1=1
    """
    params = []
    if filter_status:
        query += " AND i.status = ?"
        params.append(filter_status)
    query += " ORDER BY i.id DESC"
    invoices = conn.execute(query, params).fetchall()
    
    if user_role == "Recovery Boy":
        # Recovery Boy sees their personal collection total and pending recovery count
        total_paid = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE collected_by_staff_id = ? AND status = 'Paid'", (user_id,)).fetchone()[0]
        total_unpaid = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status IN ('Unpaid', 'Overdue')").fetchone()[0]
        unpaid_count = conn.execute("SELECT COUNT(*) FROM invoices WHERE status IN ('Unpaid', 'Overdue')").fetchone()[0]
        customers_dropdown = conn.execute("SELECT c.id, c.full_name, c.pppoe_username, t.price FROM customers c LEFT JOIN tariffs t ON c.tariff_id = t.id ORDER BY c.full_name ASC").fetchall()
        recovery_boys = [{"id": user_id, "name": session.get("user_name"), "full_name": session.get("user_name")}]
    else:
        total_paid = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status = 'Paid'").fetchone()[0]
        total_unpaid = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status IN ('Unpaid', 'Overdue')").fetchone()[0]
        unpaid_count = conn.execute("SELECT COUNT(*) FROM invoices WHERE status IN ('Unpaid', 'Overdue')").fetchone()[0]
        customers_dropdown = conn.execute("SELECT c.id, c.full_name, c.pppoe_username, t.price FROM customers c LEFT JOIN tariffs t ON c.tariff_id = t.id ORDER BY c.full_name ASC").fetchall()
        recovery_boys = conn.execute("SELECT id, full_name, full_name as name FROM users WHERE role IN ('Recovery Boy', 'Admin') AND status = 'Active'").fetchall()
    
    conn.close()

    return render_template("invoices.html", invoices=invoices, total_paid=total_paid, total_unpaid=total_unpaid,
                           paid_sum=total_paid, unpaid_sum=total_unpaid, unpaid_count=unpaid_count,
                           customers_dropdown=customers_dropdown, recovery_boys=recovery_boys,
                           status_filter=filter_status, month_filter="")

@app.route("/invoices/create_single", methods=["POST"])
@admin_only
def create_single_invoice():
    try:
        customer_id = int(request.form.get("customer_id", 0) or 0)
    except (ValueError, TypeError):
        customer_id = 0
    try:
        amount = float(request.form.get("amount", 0) or 0)
    except (ValueError, TypeError):
        amount = 0.0
    amount = max(0.0, amount)

    if customer_id <= 0:
        flash("Please select a valid customer.", "danger")
        return redirect(url_for("invoices_list"))

    month_period = request.form.get("month_period") or datetime.now().strftime("%B %Y")
    due_date = request.form.get("due_date") or (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
    status = request.form.get("status", "Unpaid")
    created_at = datetime.now().strftime("%Y-%m-%d")

    conn = db.get_db()
    cust = conn.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not cust:
        conn.close()
        flash("Customer not found.", "danger")
        return redirect(url_for("invoices_list"))

    inv_number = generate_unique_invoice_number(conn, customer_id, suffix='M')
    paid_date = created_at if status == "Paid" else None
    payment_method = "Cash" if status == "Paid" else None

    conn.execute("""
        INSERT INTO invoices (invoice_number, customer_id, amount, month_period, status, due_date, paid_date, payment_method, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (inv_number, customer_id, amount, month_period, status, due_date, paid_date, payment_method, created_at))
    conn.commit()
    conn.close()
    flash(f"Invoice {inv_number} created successfully!", "success")
    return redirect(url_for("invoices_list"))

@app.route("/invoices/edit/<int:id>", methods=["POST"])
@admin_only
def edit_invoice(id):
    try:
        amount = float(request.form.get("amount", 0) or 0)
    except (ValueError, TypeError):
        amount = 0.0
    amount = max(0.0, amount)
    month_period = request.form.get("month_period")
    due_date = request.form.get("due_date")
    status = request.form.get("status")
    payment_method = request.form.get("payment_method")

    conn = db.get_db()
    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (id,)).fetchone()
    if not inv:
        conn.close()
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoices_list"))

    month_period = request.form.get("month_period") or inv["month_period"] or datetime.now().strftime("%B %Y")
    due_date = request.form.get("due_date") or inv["due_date"]
    status = request.form.get("status") or inv["status"]
    payment_method = request.form.get("payment_method") or inv["payment_method"]

    paid_date = datetime.now().strftime("%Y-%m-%d") if status == "Paid" else None
    conn.execute("""
        UPDATE invoices 
        SET amount = ?, month_period = ?, due_date = ?, status = ?, payment_method = ?, paid_date = ?
        WHERE id = ?
    """, (amount, month_period, due_date, status, payment_method, paid_date, id))
    conn.commit()
    conn.close()
    flash(f"Invoice #{id} updated successfully!", "success")
    return redirect(url_for("invoices_list"))

@app.route("/invoices/pay/<int:id>", methods=["POST"])
@role_required("Recovery Boy")
def pay_invoice(id):
    payment_method = request.form.get("payment_method", "Cash")
    if session.get("user_role") == "Recovery Boy":
        staff_id = session.get("user_id")
    else:
        staff_id_raw = request.form.get("collected_by_staff_id")
        try:
            staff_id = int(staff_id_raw) if staff_id_raw else None
        except (ValueError, TypeError):
            staff_id = None
    paid_date = datetime.now().strftime("%Y-%m-%d")
    
    conn = db.get_db()
    inv = conn.execute("SELECT customer_id, amount, status FROM invoices WHERE id = ?", (id,)).fetchone()
    if not inv:
        conn.close()
        flash("Invoice not found.", "danger")
        return redirect(request.referrer or url_for("invoices_list"))

    if inv["status"] == "Paid":
        conn.close()
        flash("Notice: This invoice is already marked as Paid.", "warning")
        return redirect(request.referrer or url_for("invoices_list"))

    try:
        with conn:
            conn.execute("""
                UPDATE invoices 
                SET status = 'Paid', paid_date = ?, payment_method = ?, collected_by_staff_id = ?
                WHERE id = ?
            """, (paid_date, payment_method, staff_id, id))
            
            if staff_id:
                conn.execute("UPDATE users SET total_collected = total_collected + ? WHERE id = ?", (inv["amount"], staff_id))
            
            cust_id = inv["customer_id"]
            new_exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            conn.execute("UPDATE customers SET status = 'Active', expiry_date = ? WHERE id = ?", (new_exp, cust_id))

        flash(f"Invoice marked as PAID via {payment_method}! Customer account extended for 30 days.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Payment transaction failed: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(request.referrer or url_for("invoices_list"))

@app.route("/invoices/delete/<int:id>", methods=["POST"])
@admin_only
def delete_invoice(id):
    conn = db.get_db()
    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (id,)).fetchone()
    if not inv:
        conn.close()
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoices_list"))
    
    if inv["status"] == "Paid":
        conn.close()
        flash("Cannot delete a paid invoice. Paid invoices are permanent billing records for auditing and financial reports.", "warning")
        return redirect(url_for("invoices_list"))
    
    conn.execute("DELETE FROM invoices WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash(f"Invoice #{inv['invoice_number']} deleted successfully.", "success")
    return redirect(url_for("invoices_list"))

@app.route("/invoices/generate_monthly", methods=["POST"])
@admin_only
def generate_monthly_invoices():
    month_name = datetime.now().strftime("%B %Y")
    due_date = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
    created_at = datetime.now().strftime("%Y-%m-%d")

    conn = db.get_db()
    active_customers = conn.execute("""
        SELECT c.id, c.pppoe_username, t.price 
        FROM customers c
        JOIN tariffs t ON c.tariff_id = t.id
        WHERE c.status = 'Active'
    """).fetchall()

    # Pre-fetch customer IDs with bills already generated this month to eliminate N+1 queries
    existing_billed_customer_ids = {
        row[0] for row in conn.execute(
            "SELECT customer_id FROM invoices WHERE month_period = ?", (month_name,)
        ).fetchall()
    }

    created_count = 0
    try:
        with conn:
            for c in active_customers:
                if c["id"] not in existing_billed_customer_ids:
                    inv_number = generate_unique_invoice_number(conn, c['id'])
                    conn.execute("""
                        INSERT INTO invoices (invoice_number, customer_id, amount, month_period, status, due_date, created_at)
                        VALUES (?, ?, ?, ?, 'Unpaid', ?, ?)
                    """, (inv_number, c["id"], c["price"], month_name, due_date, created_at))
                    existing_billed_customer_ids.add(c["id"])
                    created_count += 1
        flash(f"Generated {created_count} monthly bills for {month_name}!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error generating monthly bills: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("invoices_list"))

@app.route("/invoice/<int:id>/print")
def print_invoice(id):
    conn = db.get_db()
    invoice = conn.execute("""
        SELECT i.*, c.full_name, c.pppoe_username, c.phone, c.address, c.area, c.onu_serial, c.db_box, c.fiber_core, c.cnic,
               t.name as plan_name, t.speed_mb, u.full_name as collector_name
        FROM invoices i
        JOIN customers c ON i.customer_id = c.id
        LEFT JOIN tariffs t ON c.tariff_id = t.id
        LEFT JOIN users u ON i.collected_by_staff_id = u.id
        WHERE i.id = ?
    """, (id,)).fetchone()
    conn.close()
    if not invoice:
        return render_template("404.html"), 404
    return render_template("invoice_print.html", invoice=invoice)

# ================= WHATSAPP TELECOM DISPATCH & NOTIFICATIONS =================
@app.route("/invoice/<int:id>/whatsapp")
@app.route("/invoices/<int:id>/whatsapp")
@role_required("Recovery Boy")
def whatsapp_invoice(id):
    conn = db.get_db()
    invoice = conn.execute("""
        SELECT i.*, c.full_name, c.pppoe_username, c.phone, c.onu_serial, c.db_box, t.name as plan_name, t.speed_mb
        FROM invoices i
        JOIN customers c ON i.customer_id = c.id
        LEFT JOIN tariffs t ON c.tariff_id = t.id
        WHERE i.id = ?
    """, (id,)).fetchone()
    conn.close()
    
    if not invoice:
        flash("Invoice not found", "danger")
        return redirect(url_for("invoices_list"))

    settings = get_settings()
    phone_clean = clean_whatsapp_phone(invoice["phone"])
    
    host_url = request.host_url.rstrip("/")
    digital_invoice_url = f"{host_url}/invoice/{invoice['id']}/print"

    status_label = "✅ PAID (Received)" if invoice["status"] == "Paid" else "⚠️ UNPAID (Due Bill)"
    plan_title = invoice["plan_name"] or "Standard FTTH Plan"
    speed_suffix = f" ({invoice['speed_mb']} Mbps)" if invoice["speed_mb"] else ""
    inv_amt = invoice["amount"] or 0
    payment_lines = []
    if settings.get('jazzcash_no'):
        payment_lines.append(f"• JazzCash: {settings.get('jazzcash_no')}")
    if settings.get('easypaisa_no'):
        payment_lines.append(f"• EasyPaisa: {settings.get('easypaisa_no')}")
    if settings.get('bank_info'):
        payment_lines.append(f"• Bank Transfer: {settings.get('bank_info')}")
    payment_info = ""
    if invoice["status"] != "Paid" and payment_lines:
        payment_info = (
            "💳 *Easy Online Payment Accounts:*\n"
            + "\n".join(payment_lines) + "\n"
            "Please share transfer slip screenshot on this chat after payment.\n"
            "----------------------------------------\n"
        )
    helpline_line = f"📞 Helpline / Support: {settings.get('phone')}\n" if settings.get('phone') else ""

    msg = (
        f"*{settings.get('isp_name', 'Sabro Networks')}*\n"
        f"⚡ *FTTH High-Speed Fiber Internet Bill*\n"
        f"----------------------------------------\n"
        f"👤 Customer Name: *{invoice['full_name']}*\n"
        f"📦 Internet Package: *{plan_title}{speed_suffix}*\n"
        f"📅 Billing Month: *{invoice['month_period']}*\n"
        f"💰 Total Amount: *{settings.get('currency', 'PKR')} {inv_amt:,.0f}*\n"
        f"📌 Status: *{status_label}*\n"
        f"⏳ Due Date: *{invoice['due_date'] or 'Immediate'}*\n"
        f"----------------------------------------\n"
        f"{payment_info}"
        f"📄 View / Print Digital Bill Slip:\n{digital_invoice_url}\n\n"
        f"{helpline_line}"
        f"Thank you for choosing {settings.get('isp_name', 'Sabro Networks')}!"
    )

    encoded_msg = urllib.parse.quote(msg)
    wa_url = f"https://wa.me/{phone_clean}?text={encoded_msg}"
    return redirect(wa_url)

@app.route("/customer/<int:id>/whatsapp_welcome")
@app.route("/customers/<int:id>/whatsapp_welcome")
@admin_only
def customer_whatsapp_welcome(id):
    conn = db.get_db()
    cust = conn.execute("""
        SELECT c.*, t.name as plan_name, t.price as plan_price, t.speed_mb
        FROM customers c
        LEFT JOIN tariffs t ON c.tariff_id = t.id
        WHERE c.id = ?
    """, (id,)).fetchone()
    conn.close()

    if not cust:
        flash("Customer not found", "danger")
        return redirect(url_for("customers_list"))

    settings = get_settings()
    phone_clean = clean_whatsapp_phone(cust["phone"])
    if not phone_clean:
        flash("Customer has no valid mobile number for WhatsApp.", "warning")
        return redirect(url_for("customers_list"))

    c_plan = cust['plan_name'] or 'Standard FTTH Plan'
    c_speed = f" ({cust['speed_mb']} Mbps)" if cust['speed_mb'] else ""
    c_price = cust['plan_price'] or 0
    pay_acct_lines = []
    if settings.get('jazzcash_no'):
        pay_acct_lines.append(f"• JazzCash: {settings.get('jazzcash_no')}")
    if settings.get('easypaisa_no'):
        pay_acct_lines.append(f"• EasyPaisa: {settings.get('easypaisa_no')}")
    if settings.get('bank_info'):
        pay_acct_lines.append(f"• Bank: {settings.get('bank_info')}")
    pay_section = (
        "----------------------------------------\n"
        "💳 *Online Payment Accounts:*\n" + "\n".join(pay_acct_lines) + "\n"
    ) if pay_acct_lines else ""
    support_lines = []
    if settings.get('phone'):
        support_lines.append(f"• Helpline: {settings.get('phone')}")
    if settings.get('address'):
        support_lines.append(f"• Office Address: {settings.get('address')}")
    support_section = (
        "----------------------------------------\n"
        "📞 *Customer Support:*\n" + "\n".join(support_lines) + "\n\n"
    ) if support_lines else "\n"

    msg = (
        f"🌐 *{settings.get('isp_name', 'Sabro Networks')}*\n"
        f"⚡ *FTTH Optical Fiber Connection Activated!*\n"
        f"----------------------------------------\n"
        f"Assalam-o-Alaikum *{cust['full_name']}*,\n"
        f"Welcome to {settings.get('isp_name', 'Sabro Networks')}! Your high-speed fiber internet connection is now active and ready to use.\n\n"
        f"📋 *Your Connection Credentials:*\n"
        f"• PPPoE Username: *{cust['pppoe_username']}*\n"
        f"• PPPoE Password: *{cust['password']}*\n"
        f"• Fiber Package: *{c_plan}{c_speed}*\n"
        f"• Monthly Tariff: *{settings.get('currency', 'PKR')} {c_price:,.0f}*\n"
        f"• Expiry Date: *{cust['expiry_date'] or 'Active'}*\n"
        f"• ONT / ONU Serial: *{cust['onu_serial'] or 'Registered'}*\n"
        f"• Distribution Box: *{cust['db_box'] or 'Assigned'}*\n"
        f"{pay_section}"
        f"{support_section}"
        f"Enjoy blazing-fast internet streaming & browsing!"
    )

    encoded_msg = urllib.parse.quote(msg)
    return redirect(f"https://wa.me/{phone_clean}?text={encoded_msg}")

@app.route("/customer/<int:id>/whatsapp_reminder")
@app.route("/customers/<int:id>/whatsapp_reminder")
@role_required("Recovery Boy")
def customer_whatsapp_reminder(id):
    conn = db.get_db()
    cust = conn.execute("""
        SELECT c.*, t.name as plan_name, t.price as plan_price
        FROM customers c
        LEFT JOIN tariffs t ON c.tariff_id = t.id
        WHERE c.id = ?
    """, (id,)).fetchone()
    
    latest_inv = conn.execute("""
        SELECT * FROM invoices WHERE customer_id = ? ORDER BY id DESC LIMIT 1
    """, (id,)).fetchone()
    conn.close()

    if not cust:
        flash("Customer not found", "danger")
        return redirect(url_for("customers_list"))

    settings = get_settings()
    phone_clean = clean_whatsapp_phone(cust["phone"])
    if not phone_clean:
        flash("Customer has no valid phone number for WhatsApp.", "warning")
        return redirect(url_for("customers_list"))

    amount_due = (latest_inv["amount"] if latest_inv else cust["plan_price"]) or 0
    isp = settings.get("isp_name", "Sabro Networks")
    helpline = settings.get("phone", "")
    rabta_line = f"\nRabta: {helpline}" if helpline else ""

    msg = (
        f"Assalam-o-Alaikum *{cust['full_name']}* bhai,\n\n"
        f"*{isp}* ki taraf se aapka internet bill *Rs. {amount_due:,.0f}* pending hai. "
        f"Baraye meherbani time pe clear kar dein taake aapka internet chalta rahe.\n\n"
        f"Shukriya!\n"
        f"*{isp}*"
        f"{rabta_line}"
    )

    encoded_msg = urllib.parse.quote(msg)
    return redirect(f"https://wa.me/{phone_clean}?text={encoded_msg}")


@app.route("/invoices/defaulters_whatsapp_summary")
@role_required("Recovery Boy")
def defaulters_whatsapp_summary():
    conn = db.get_db()
    unpaid = conn.execute("""
        SELECT i.*, c.full_name, c.pppoe_username, c.phone, c.area, c.address, c.db_box
        FROM invoices i
        JOIN customers c ON i.customer_id = c.id
        WHERE i.status IN ('Unpaid', 'Overdue')
        ORDER BY c.area ASC, i.amount DESC
    """).fetchall()
    conn.close()

    settings = get_settings()
    month_name = datetime.now().strftime("%B %Y")
    total_unpaid = sum(u["amount"] for u in unpaid)

    msg = (
        f"🚨 *{settings.get('isp_name', 'Sabro Networks')}*\n"
        f"📋 *PENDING RECOVERY / DEFAULTERS LIST - {month_name}*\n"
        f"Total Defaulters: {len(unpaid)} | Total Due: {settings.get('currency', 'PKR')} {total_unpaid:,.0f}\n"
        f"----------------------------------------\n"
    )
    current_area = None
    count = 1
    for u in unpaid:
        if u["area"] != current_area:
            current_area = u["area"]
            msg += f"\n📍 *[{current_area}]*\n"
        msg += f"{count}. *{u['full_name']}* (@{u['pppoe_username']})\n"
        msg += f"   📞 {u['phone']} | 🏠 {u['db_box'] or u['address']}\n"
        msg += f"   💰 Rs. {u['amount']:,.0f} (Due: {u['due_date']})\n"
        count += 1

    helpline_def = f"\nHelpline: {settings.get('phone')}" if settings.get('phone') else ""
    msg += (
        f"\n----------------------------------------\n"
        f"💳 Please deposit collections daily at office counter.{helpline_def}"
    )

    encoded = urllib.parse.quote(msg)
    return redirect(f"https://wa.me/?text={encoded}")

# ================= TICKETING & COMPLAINTS SYSTEM =================
@app.route("/tickets", methods=["GET"])
@role_required("Complaint Boy")
def tickets_page():
    status_filter = request.args.get("status", "")
    user_id = session.get("user_id")
    user_role = session.get("user_role")

    conn = db.get_db()
    query = """
        SELECT t.*, c.full_name as customer_name, c.pppoe_username, c.phone as customer_phone, c.address as customer_address, c.area as customer_area,
               c.onu_serial, c.db_box, c.fiber_core,
               u.full_name as tech_name, u.phone as tech_phone, u.role as tech_role
        FROM tickets t
        JOIN customers c ON t.customer_id = c.id
        LEFT JOIN users u ON t.assigned_user_id = u.id
        WHERE 1=1
    """
    params = []
    if user_role == "Complaint Boy":
        query += " AND (t.assigned_user_id = ? OR (t.assigned_user_id IS NULL AND t.status = 'Open'))"
        params.append(user_id)

    if status_filter:
        query += " AND t.status = ?"
        params.append(status_filter)
    query += " ORDER BY t.id DESC"
    tickets = conn.execute(query, params).fetchall()

    customers = conn.execute("SELECT id, full_name, pppoe_username, phone, address, area, db_box, onu_serial FROM customers ORDER BY full_name ASC").fetchall()
    
    if user_role == "Complaint Boy":
        complain_boys = [{"id": user_id, "full_name": session.get("user_name"), "phone": "", "role": "Complaint Boy", "assigned_area": session.get("user_area")}]
        open_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Open' AND (assigned_user_id = ? OR assigned_user_id IS NULL)", (user_id,)).fetchone()[0]
        in_progress_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'In Progress' AND assigned_user_id = ?", (user_id,)).fetchone()[0]
        resolved_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Resolved' AND assigned_user_id = ?", (user_id,)).fetchone()[0]
    else:
        complain_boys = conn.execute("SELECT id, full_name, phone, role, assigned_area FROM users WHERE status = 'Active' ORDER BY full_name ASC").fetchall()
        open_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Open'").fetchone()[0]
        in_progress_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'In Progress'").fetchone()[0]
        resolved_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Resolved'").fetchone()[0]
        
    conn.close()

    return render_template("tickets.html", tickets=tickets, customers=customers, complain_boys=complain_boys,
                           open_count=open_count, in_progress_count=in_progress_count, resolved_count=resolved_count,
                           status_filter=status_filter)

@app.route("/tickets/add", methods=["POST"])
@role_required("Complaint Boy")
def add_ticket():
    try:
        customer_id = int(request.form.get("customer_id", 0) or 0)
    except (ValueError, TypeError):
        customer_id = 0
    subject = (request.form.get("subject") or "").strip()
    details = (request.form.get("details") or "").strip()
    priority = request.form.get("priority", "Medium")
    assigned_user_id_raw = request.form.get("assigned_user_id")
    try:
        assigned_user_id = int(assigned_user_id_raw) if assigned_user_id_raw else None
    except (ValueError, TypeError):
        assigned_user_id = None

    if customer_id <= 0:
        flash("Please select a valid customer for the complaint ticket.", "danger")
        return redirect(url_for("tickets_page"))
    
    conn = db.get_db()
    cust = conn.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not cust:
        conn.close()
        flash("Selected customer does not exist.", "danger")
        return redirect(url_for("tickets_page"))

    if assigned_user_id:
        user_exists = conn.execute("SELECT id FROM users WHERE id = ?", (assigned_user_id,)).fetchone()
        if not user_exists:
            assigned_user_id = None

    ticket_number = generate_unique_ticket_number(conn)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn.execute("""
        INSERT INTO tickets (ticket_number, customer_id, subject, details, priority, status, assigned_user_id, created_at)
        VALUES (?, ?, ?, ?, ?, 'Open', ?, ?)
    """, (ticket_number, customer_id, subject, details, priority, assigned_user_id, created_at))
    conn.commit()
    conn.close()
    flash(f"Complaint Ticket {ticket_number} created successfully!", "success")
    return redirect(url_for("tickets_page"))

@app.route("/tickets/assign/<int:id>", methods=["POST"])
@role_required("Complaint Boy")
def assign_ticket(id):
    assigned_user_id_raw = request.form.get("assigned_user_id")
    try:
        assigned_user_id = int(assigned_user_id_raw) if assigned_user_id_raw else None
    except (ValueError, TypeError):
        assigned_user_id = None
        
    conn = db.get_db()
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (id,)).fetchone()
    if not ticket:
        conn.close()
        flash("Complaint ticket not found.", "danger")
        return redirect(request.referrer or url_for("tickets_page"))
        
    tech_name = "Unassigned"
    if assigned_user_id:
        tech = conn.execute("SELECT id, full_name, phone FROM users WHERE id = ?", (assigned_user_id,)).fetchone()
        if tech:
            tech_name = tech["full_name"]
        else:
            assigned_user_id = None
            
    new_status = "In Progress" if (assigned_user_id and ticket["status"] == "Open") else ticket["status"]
    
    conn.execute("""
        UPDATE tickets
        SET assigned_user_id = ?, status = ?
        WHERE id = ?
    """, (assigned_user_id, new_status, id))
    conn.commit()
    conn.close()
    
    if assigned_user_id:
        flash(f"Complaint {ticket['ticket_number']} assigned to {tech_name} successfully! Field technician work order ready.", "success")
    else:
        flash(f"Complaint {ticket['ticket_number']} marked as unassigned.", "info")
        
    return redirect(request.referrer or url_for("tickets_page"))

@app.route("/tickets/edit/<int:id>", methods=["POST"])
@role_required("Complaint Boy")
def edit_ticket(id):
    subject = (request.form.get("subject") or "").strip()
    details = (request.form.get("details") or "").strip()
    priority = request.form.get("priority", "Medium")
    status = request.form.get("status", "Open")
    assigned_user_id_raw = request.form.get("assigned_user_id")
    try:
        assigned_user_id = int(assigned_user_id_raw) if assigned_user_id_raw else None
    except (ValueError, TypeError):
        assigned_user_id = None
    resolution_notes = (request.form.get("resolution_notes") or "").strip()
    resolved_at = datetime.now().strftime("%Y-%m-%d %H:%M") if status == "Resolved" else None

    conn = db.get_db()
    tck = conn.execute("SELECT id FROM tickets WHERE id = ?", (id,)).fetchone()
    if not tck:
        conn.close()
        flash("Ticket not found.", "danger")
        return redirect(request.referrer or url_for("tickets_page"))

    if assigned_user_id:
        user_exists = conn.execute("SELECT id FROM users WHERE id = ?", (assigned_user_id,)).fetchone()
        if not user_exists:
            assigned_user_id = None
    old_ticket = conn.execute("SELECT status FROM tickets WHERE id = ?", (id,)).fetchone()
    conn.execute("""
        UPDATE tickets 
        SET subject = ?, details = ?, priority = ?, status = ?, assigned_user_id = ?, resolution_notes = ?, resolved_at = ?
        WHERE id = ?
    """, (subject, details, priority, status, assigned_user_id, resolution_notes, resolved_at, id))
    if status == "Resolved" and assigned_user_id and old_ticket and old_ticket["status"] != "Resolved":
        xp_gain = 180 if priority == "Critical" else 120
        conn.execute("UPDATE users SET technician_xp = technician_xp + ? WHERE id = ?", (xp_gain, assigned_user_id))
    conn.commit()
    conn.close()
    flash(f"Ticket #{id} updated successfully!", "success")
    return redirect(request.referrer or url_for("tickets_page"))

@app.route("/tickets/whatsapp/<int:id>")
@app.route("/tickets/<int:id>/whatsapp")
@role_required("Complaint Boy")
def whatsapp_ticket(id):
    conn = db.get_db()
    ticket = conn.execute("""
        SELECT t.*, c.full_name as customer_name, c.pppoe_username, c.phone as customer_phone, c.address as customer_address, c.area as customer_area,
               c.onu_serial, c.db_box, c.fiber_core,
               u.full_name as tech_name, u.phone as tech_phone
        FROM tickets t
        JOIN customers c ON t.customer_id = c.id
        LEFT JOIN users u ON t.assigned_user_id = u.id
        WHERE t.id = ?
    """, (id,)).fetchone()
    conn.close()

    if not ticket:
        flash("Ticket not found.", "danger")
        return redirect(url_for("tickets_page"))

    if not ticket["tech_phone"]:
        flash("No technician phone assigned to this ticket. Please assign a technician first.", "warning")
        return redirect(url_for("tickets_page"))

    settings = get_settings()
    tech_phone_clean = clean_whatsapp_phone(ticket["tech_phone"])
    
    msg = (
        f"🚨 *NEW COMPLAINT TICKET #{ticket['ticket_number']}*\n"
        f"⚡ *{settings.get('isp_name', 'Sabro Networks')}*\n"
        f"----------------------------------------\n"
        f"👤 Customer: *{ticket['customer_name']}*\n"
        f"🔑 PPPoE: *@{ticket['pppoe_username']}*\n"
        f"📞 Phone: *{ticket['customer_phone']}*\n"
        f"📍 Area & Address: *{ticket['customer_area']}, {ticket['customer_address']}*\n"
        f"📦 FDB Box / Pole: *{ticket['db_box'] or 'Check area'}*\n"
        f"🔌 Fiber Core: *{ticket['fiber_core'] or 'Single Drop'}*\n"
        f"📡 ONT / ONU Serial: *{ticket['onu_serial'] or 'Standard XPON'}*\n"
        f"----------------------------------------\n"
        f"⚠️ Issue: *{ticket['subject']}*\n"
        f"🔥 Priority: *{ticket['priority']}*\n"
        f"📝 Details: *{ticket['details'] or 'Customer reported fiber signal issue'}*\n"
        f"----------------------------------------\n"
        f"👷 Assigned To: *{ticket['tech_name']} (Complain Boy)*\n"
        f"Please inspect the pole splitter and resolve promptly.\n"
        f"Portal Desk: {request.host_url.rstrip('/')}/tickets"
    )

    encoded_msg = urllib.parse.quote(msg)
    wa_url = f"https://wa.me/{tech_phone_clean}?text={encoded_msg}"
    return redirect(wa_url)

@app.route("/tickets/<int:id>/whatsapp_resolved")
@app.route("/tickets/whatsapp_resolved/<int:id>")
@role_required("Complaint Boy")
def whatsapp_ticket_resolved(id):
    conn = db.get_db()
    ticket = conn.execute("""
        SELECT t.*, c.full_name as customer_name, c.phone as customer_phone, c.pppoe_username,
               u.full_name as tech_name, u.phone as tech_phone
        FROM tickets t
        JOIN customers c ON t.customer_id = c.id
        LEFT JOIN users u ON t.assigned_user_id = u.id
        WHERE t.id = ?
    """, (id,)).fetchone()
    conn.close()

    if not ticket:
        flash("Ticket not found.", "danger")
        return redirect(url_for("tickets_page"))

    settings = get_settings()
    phone_clean = clean_whatsapp_phone(ticket["customer_phone"])
    if not phone_clean:
        flash("Customer has no valid phone number for WhatsApp.", "warning")
        return redirect(url_for("tickets_page"))

    resolution_text = ticket["resolution_notes"] or "Optical fiber line checked and internet signal verified."
    tech_name = ticket["tech_name"] or "Field Support Team"
    helpline_res = f"📞 Helpline: {settings.get('phone')}\n" if settings.get('phone') else ""

    msg = (
        f"✅ *COMPLAINT RESOLVED - {settings.get('isp_name', 'Sabro Networks')}*\n"
        f"⚡ *FTTH Technical Support Desk*\n"
        f"----------------------------------------\n"
        f"Dear *{ticket['customer_name']}* (@{ticket['pppoe_username']}),\n"
        f"Your technical complaint ticket *#{ticket['ticket_number']}* has been marked *RESOLVED*.\n\n"
        f"⚠️ *Reported Issue:* {ticket['subject']}\n"
        f"👷 *Attended By:* {tech_name}\n"
        f"📝 *Resolution:* {resolution_text}\n"
        f"⏰ *Resolved At:* {ticket['resolved_at'] or datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"----------------------------------------\n"
        f"Please restart your ONU router and check your connection. If you still encounter any difficulty, please reply to this message.\n\n"
        f"{helpline_res}"
        f"Thank you for choosing {settings.get('isp_name', 'Sabro Networks')}!"
    )

    encoded_msg = urllib.parse.quote(msg)
    return redirect(f"https://wa.me/{phone_clean}?text={encoded_msg}")

@app.route("/tickets/delete/<int:id>", methods=["POST"])
@admin_only
def delete_ticket(id):
    conn = db.get_db()
    tck = conn.execute("SELECT id FROM tickets WHERE id = ?", (id,)).fetchone()
    if not tck:
        conn.close()
        flash("Ticket not found.", "danger")
        return redirect(url_for("tickets_page"))

    conn.execute("DELETE FROM tickets WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Ticket deleted.", "info")
    return redirect(url_for("tickets_page"))


# ================= PROFILE & AVATAR (PFP) MANAGEMENT =================
@app.route("/profile/update_pfp", methods=["POST"])
def update_profile_pfp():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))
    
    file = request.files.get("pfp_file")
    if not file or not file.filename:
        flash("Please select an image file to upload.", "danger")
        return redirect(request.referrer or url_for("dashboard"))
    
    rel_path = save_pfp_upload(file, user_id)
    if not rel_path:
        flash("Invalid image format. Allowed formats: PNG, JPG, JPEG, WEBP, GIF.", "danger")
        return redirect(request.referrer or url_for("dashboard"))
    
    conn = db.get_db()
    conn.execute("UPDATE users SET pfp_image = ? WHERE id = ?", (rel_path, user_id))
    conn.commit()
    conn.close()
    flash("Profile picture updated successfully!", "success")
    return redirect(request.referrer or url_for("dashboard"))

# ================= STAFF & USER LOGINS (ADD, EDIT, DELETE) =================
@app.route("/staff")
@admin_only
def staff_list():
    conn = db.get_db()
    staff_rows = conn.execute("""
        SELECT u.*, 
               (SELECT COUNT(*) FROM tickets t WHERE t.assigned_user_id = u.id AND t.status != 'Resolved') as assigned_tickets,
               (SELECT COUNT(*) FROM tickets t WHERE t.assigned_user_id = u.id AND t.status = 'Resolved') as resolved_tickets,
               (SELECT COUNT(*) FROM invoices i WHERE i.collected_by_staff_id = u.id) as collected_invoices_count
        FROM users u
        ORDER BY u.id ASC
    """).fetchall()
    
    staff_members = []
    for s in staff_rows:
        s_dict = dict(s)
        s_dict["avatar_url"] = get_user_avatar(s_dict)
        if s_dict["role"] == "Complaint Boy":
            s_dict["level_info"] = calculate_technician_level(s_dict.get("resolved_tickets", 0), s_dict.get("technician_xp", 0))
        staff_members.append(s_dict)

    conn.close()
    return render_template("staff.html", staff_members=staff_members)

@app.route("/staff/add", methods=["POST"])
@admin_only
def add_staff():
    full_name = (request.form.get("full_name") or "").strip()
    username = (request.form.get("username") or "").strip().lower()
    password = (request.form.get("password") or "").strip()
    role = request.form.get("role", "Complaint Boy")
    phone = (request.form.get("phone") or "").strip()
    assigned_area = (request.form.get("assigned_area") or "").strip()
    status = request.form.get("status", "Active")
    created_at = datetime.now().strftime("%Y-%m-%d")

    if not full_name or not username or not password:
        flash("Staff full name, username, and password are required.", "danger")
        return redirect(url_for("staff_list"))

    conn = db.get_db()
    try:
        hashed_password = generate_password_hash(password)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?)
        """, (full_name, username, hashed_password, role, phone, assigned_area, status, created_at))
        new_id = cursor.lastrowid
        pfp_file = request.files.get("pfp_file")
        if pfp_file and pfp_file.filename:
            rel_pfp = save_pfp_upload(pfp_file, new_id)
            if rel_pfp:
                conn.execute("UPDATE users SET pfp_image = ? WHERE id = ?", (rel_pfp, new_id))
        conn.commit()
        flash(f"Staff member '{full_name}' (@{username}) registered with role {role}!", "success")
    except Exception as e:
        flash(f"Error adding staff member: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("staff_list"))

@app.route("/staff/edit/<int:id>", methods=["POST"])
@admin_only
def edit_staff(id):
    full_name = (request.form.get("full_name") or "").strip()
    username = (request.form.get("username") or "").strip().lower()
    password = (request.form.get("password") or "").strip()
    role = request.form.get("role", "Complaint Boy")
    phone = (request.form.get("phone") or "").strip()
    assigned_area = (request.form.get("assigned_area") or "").strip()
    status = request.form.get("status", "Active")

    conn = db.get_db()
    staff = conn.execute("SELECT id, password FROM users WHERE id = ?", (id,)).fetchone()
    if not staff:
        conn.close()
        flash("Staff member not found.", "danger")
        return redirect(url_for("staff_list"))

    if not full_name or not username:
        conn.close()
        flash("Staff full name and username are required.", "danger")
        return redirect(url_for("staff_list"))

    # Only re-hash if a new password is provided and it's not already a hash
    if password:
        if not (password.startswith("scrypt:") or password.startswith("pbkdf2:")):
            hashed_password = generate_password_hash(password)
        else:
            hashed_password = password
    else:
        hashed_password = staff["password"]

    try:
        conn.execute("""
            UPDATE users 
            SET full_name = ?, username = ?, password = ?, role = ?, phone = ?, assigned_area = ?, status = ?
            WHERE id = ?
        """, (full_name, username, hashed_password, role, phone, assigned_area, status, id))
        pfp_file = request.files.get("pfp_file")
        if pfp_file and pfp_file.filename:
            rel_pfp = save_pfp_upload(pfp_file, id)
            if rel_pfp:
                conn.execute("UPDATE users SET pfp_image = ? WHERE id = ?", (rel_pfp, id))
        conn.commit()
        flash(f"Staff profile for '{full_name}' updated successfully!", "success")
    except Exception as e:
        flash(f"Error updating staff: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("staff_list"))

@app.route("/staff/delete/<int:id>", methods=["POST"])
@admin_only
def delete_staff(id):
    if id == session.get("user_id"):
        flash("You cannot delete your currently logged in account!", "danger")
        return redirect(url_for("staff_list"))

    conn = db.get_db()
    staff = conn.execute("SELECT id, full_name FROM users WHERE id = ?", (id,)).fetchone()
    if not staff:
        conn.close()
        flash("Staff member not found.", "danger")
        return redirect(url_for("staff_list"))

    # Check for foreign key references in tickets or collected invoices
    assigned_tickets = conn.execute("SELECT COUNT(*) FROM tickets WHERE assigned_user_id = ?", (id,)).fetchone()[0]
    collected_invoices = conn.execute("SELECT COUNT(*) FROM invoices WHERE collected_by_staff_id = ?", (id,)).fetchone()[0]

    if assigned_tickets > 0 or collected_invoices > 0:
        conn.execute("UPDATE users SET status = 'Inactive' WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        flash(f"Staff member '{staff['full_name']}' is linked to {collected_invoices} invoice(s) and {assigned_tickets} ticket(s). Deactivated account to preserve audit records.", "warning")
        return redirect(url_for("staff_list"))

    try:
        conn.execute("DELETE FROM users WHERE id = ?", (id,))
        conn.commit()
        flash("Staff member deleted.", "info")
    except Exception as e:
        flash(f"Could not delete staff member: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("staff_list"))

@app.route("/recovery")
@admin_only
def recovery_page():
    return redirect(url_for("staff_list"))

# ================= CAPITAL INVESTMENTS (ADD & EDIT) =================
@app.route("/investments", methods=["GET", "POST"])
@admin_only
def investments_page():
    conn = db.get_db()
    if request.method == "POST":
        investor_name = request.form.get("investor_name", "").strip()
        title = request.form.get("title", "").strip()
        if not title or not investor_name:
            conn.close()
            flash("Investor name and title are required.", "danger")
            return redirect(url_for("investments_page"))
        try:
            amount = float(request.form.get("amount", 0) or 0)
        except (ValueError, TypeError):
            amount = 0.0
        amount = max(0.0, amount)
        category = request.form.get("category", "General")
        date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
        notes = request.form.get("notes", "")
        created_at = datetime.now().strftime("%Y-%m-%d")

        conn.execute("""
            INSERT INTO investments (investor_name, title, amount, category, date, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (investor_name, title, amount, category, date, notes, created_at))
        conn.commit()
        flash(f"Investment of {amount} by '{investor_name}' recorded!", "success")
        return redirect(url_for("investments_page"))

    investments = conn.execute("SELECT * FROM investments ORDER BY id DESC").fetchall()
    total_invested = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM investments").fetchone()[0]

    cat_summary = conn.execute("""
        SELECT category, SUM(amount) as total_cat 
        FROM investments 
        GROUP BY category
    """).fetchall()

    paid_sum = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE status = 'Paid'").fetchone()[0]
    total_expenses = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses").fetchone()[0]
    net_profit = paid_sum - total_expenses

    conn.close()

    return render_template("investments.html", investments=investments, total_invested=total_invested,
                           cat_summary=cat_summary, paid_sum=paid_sum, total_expenses=total_expenses, net_profit=net_profit)

@app.route("/investments/edit/<int:id>", methods=["POST"])
@admin_only
def edit_investment(id):
    investor_name = (request.form.get("investor_name") or "").strip()
    title = (request.form.get("title") or "").strip()
    if not title or not investor_name:
        flash("Investor name and title are required.", "danger")
        return redirect(url_for("investments_page"))
    try:
        amount = float(request.form.get("amount", 0) or 0)
    except (ValueError, TypeError):
        amount = 0.0
    amount = max(0.0, amount)
    amount = max(0.0, amount)
    category = request.form.get("category", "General")
    date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
    notes = request.form.get("notes", "")

    conn = db.get_db()
    item = conn.execute("SELECT id FROM investments WHERE id = ?", (id,)).fetchone()
    if not item:
        conn.close()
        flash("Investment record not found.", "danger")
        return redirect(url_for("investments_page"))

    conn.execute("""
        UPDATE investments 
        SET investor_name = ?, title = ?, amount = ?, category = ?, date = ?, notes = ?
        WHERE id = ?
    """, (investor_name, title, amount, category, date, notes, id))
    conn.commit()
    conn.close()
    flash(f"Investment '{title}' updated successfully!", "success")
    return redirect(url_for("investments_page"))

@app.route("/investments/delete/<int:id>", methods=["POST"])
@admin_only
def delete_investment(id):
    conn = db.get_db()
    item = conn.execute("SELECT id FROM investments WHERE id = ?", (id,)).fetchone()
    if not item:
        conn.close()
        flash("Investment record not found.", "danger")
        return redirect(url_for("investments_page"))

    conn.execute("DELETE FROM investments WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Investment entry removed.", "info")
    return redirect(url_for("investments_page"))

# ================= EXPENSES (ADD & EDIT) =================
@app.route("/expenses", methods=["GET", "POST"])
@admin_only
def expenses_page():
    conn = db.get_db()
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            conn.close()
            flash("Expense title is required.", "danger")
            return redirect(url_for("expenses_page"))
        category = request.form.get("category", "Office")
        try:
            amount = float(request.form.get("amount", 0) or 0)
        except (ValueError, TypeError):
            amount = 0.0
        amount = max(0.0, amount)
        date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
        paid_by = request.form.get("paid_by", "Admin")
        notes = request.form.get("notes", "")
        created_at = datetime.now().strftime("%Y-%m-%d")

        conn.execute("""
            INSERT INTO expenses (title, category, amount, date, paid_by, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, category, amount, date, paid_by, notes, created_at))
        conn.commit()
        flash(f"Expense '{title}' of {amount} added!", "success")
        return redirect(url_for("expenses_page"))

    category_filter = request.args.get("category", "")
    query = "SELECT * FROM expenses WHERE 1=1"
    params = []
    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)
    query += " ORDER BY id DESC"
    expenses = conn.execute(query, params).fetchall()

    cat_summary = conn.execute("""
        SELECT category, SUM(amount) as total_cat 
        FROM expenses 
        GROUP BY category
    """).fetchall()

    total_expense = sum(c['total_cat'] for c in cat_summary)
    conn.close()

    return render_template("expenses.html", expenses=expenses, cat_summary=cat_summary, 
                           total_expense=total_expense, category_filter=category_filter)

@app.route("/expenses/edit/<int:id>", methods=["POST"])
@admin_only
def edit_expense(id):
    title = (request.form.get("title") or "").strip()
    category = request.form.get("category", "Office")
    try:
        amount = float(request.form.get("amount", 0) or 0)
    except (ValueError, TypeError):
        amount = 0.0
    amount = max(0.0, amount)
    amount = max(0.0, amount)
    date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
    paid_by = request.form.get("paid_by", "Admin")
    notes = request.form.get("notes", "")

    conn = db.get_db()
    if not title:
        conn.close()
        flash("Expense title is required.", "danger")
        return redirect(url_for("expenses_page"))
    item = conn.execute("SELECT id FROM expenses WHERE id = ?", (id,)).fetchone()
    if not item:
        conn.close()
        flash("Expense record not found.", "danger")
        return redirect(url_for("expenses_page"))

    conn.execute("""
        UPDATE expenses 
        SET title = ?, category = ?, amount = ?, date = ?, paid_by = ?, notes = ?
        WHERE id = ?
    """, (title, category, amount, date, paid_by, notes, id))
    conn.commit()
    conn.close()
    flash(f"Expense '{title}' updated successfully!", "success")
    return redirect(url_for("expenses_page"))

@app.route("/expenses/delete/<int:id>", methods=["POST"])
@admin_only
def delete_expense(id):
    conn = db.get_db()
    item = conn.execute("SELECT id FROM expenses WHERE id = ?", (id,)).fetchone()
    if not item:
        conn.close()
        flash("Expense record not found.", "danger")
        return redirect(url_for("expenses_page"))

    conn.execute("DELETE FROM expenses WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Expense entry removed.", "info")
    return redirect(url_for("expenses_page"))

# ================= DEPOSITS & ADVANCES (ADD & EDIT) =================
@app.route("/deposits", methods=["GET", "POST"])
@admin_only
def deposits_page():
    conn = db.get_db()
    if request.method == "POST":
        try:
            customer_id = int(request.form.get("customer_id", 0) or 0)
        except (ValueError, TypeError):
            customer_id = 0
        if customer_id <= 0:
            conn.close()
            flash("Please select a valid customer.", "danger")
            return redirect(url_for("deposits_page"))
        deposit_type = request.form.get("deposit_type", "Security Deposit")
        try:
            amount = float(request.form.get("amount", 0) or 0)
        except (ValueError, TypeError):
            amount = 0.0
        amount = max(0.0, amount)
        date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
        notes = request.form.get("notes", "")
        created_at = datetime.now().strftime("%Y-%m-%d")

        conn.execute("""
            INSERT INTO deposits (customer_id, deposit_type, amount, status, date, notes, created_at)
            VALUES (?, ?, ?, 'Held', ?, ?, ?)
        """, (customer_id, deposit_type, amount, date, notes, created_at))
        conn.commit()
        flash(f"Deposit of {amount} recorded successfully!", "success")
        return redirect(url_for("deposits_page"))

    deposits = conn.execute("""
        SELECT d.*, c.full_name, c.pppoe_username, c.phone, c.area
        FROM deposits d
        JOIN customers c ON d.customer_id = c.id
        ORDER BY d.id DESC
    """).fetchall()

    customers = conn.execute("SELECT id, full_name, pppoe_username FROM customers ORDER BY full_name ASC").fetchall()
    total_held = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE status = 'Held'").fetchone()[0]
    total_refunded = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE status = 'Refunded'").fetchone()[0]
    conn.close()

    return render_template("deposits.html", deposits=deposits, customers=customers, 
                           total_held=total_held, total_refunded=total_refunded)

@app.route("/deposits/edit/<int:id>", methods=["POST"])
@admin_only
def edit_deposit(id):
    deposit_type = request.form.get("deposit_type", "Security Deposit")
    try:
        amount = float(request.form.get("amount", 0) or 0)
    except (ValueError, TypeError):
        amount = 0.0
    amount = max(0.0, amount)
    status = request.form.get("status", "Held")
    date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
    notes = request.form.get("notes", "")

    conn = db.get_db()
    item = conn.execute("SELECT id FROM deposits WHERE id = ?", (id,)).fetchone()
    if not item:
        conn.close()
        flash("Deposit record not found.", "danger")
        return redirect(url_for("deposits_page"))

    conn.execute("""
        UPDATE deposits 
        SET deposit_type = ?, amount = ?, status = ?, date = ?, notes = ?
        WHERE id = ?
    """, (deposit_type, amount, status, date, notes, id))
    conn.commit()
    conn.close()
    flash("Deposit record updated successfully!", "success")
    return redirect(url_for("deposits_page"))

@app.route("/deposits/update_status/<int:id>", methods=["POST"])
@admin_only
def update_deposit_status(id):
    new_status = request.form.get("status", "Held")
    conn = db.get_db()
    item = conn.execute("SELECT id FROM deposits WHERE id = ?", (id,)).fetchone()
    if not item:
        conn.close()
        flash("Deposit record not found.", "danger")
        return redirect(url_for("deposits_page"))

    conn.execute("UPDATE deposits SET status = ? WHERE id = ?", (new_status, id))
    conn.commit()
    conn.close()
    flash(f"Deposit status updated to {new_status}.", "info")
    return redirect(url_for("deposits_page"))

# ================= PACKAGES / TARIFFS (ADD & EDIT) =================
@app.route("/tariffs")
@admin_only
def tariffs_list():
    conn = db.get_db()
    tariffs = conn.execute("""
        SELECT t.*, COUNT(c.id) as subscriber_count 
        FROM tariffs t
        LEFT JOIN customers c ON c.tariff_id = t.id
        GROUP BY t.id
        ORDER BY t.price ASC
    """).fetchall()
    conn.close()
    return render_template("tariffs.html", tariffs=tariffs)

@app.route("/tariffs/add", methods=["POST"])
@admin_only
def add_tariff():
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Package name is required.", "danger")
        return redirect(url_for("tariffs_list"))
    try:
        speed_mb = int(request.form.get("speed_mb", 10) or 10)
    except (ValueError, TypeError):
        speed_mb = 10
    try:
        price = float(request.form.get("price", 1000) or 1000)
    except (ValueError, TypeError):
        price = 1000.0
    speed_mb = max(1, speed_mb)
    price = max(0.0, price)
    description = (request.form.get("description") or "").strip()

    conn = db.get_db()
    conn.execute("""
        INSERT INTO tariffs (name, speed_mb, price, description)
        VALUES (?, ?, ?, ?)
    """, (name, speed_mb, price, description))
    conn.commit()
    conn.close()
    flash(f"New package '{name}' added successfully!", "success")
    return redirect(url_for("tariffs_list"))

@app.route("/tariffs/edit/<int:id>", methods=["POST"])
@admin_only
def edit_tariff(id):
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Package name is required.", "danger")
        return redirect(url_for("tariffs_list"))
    try:
        speed_mb = int(request.form.get("speed_mb", 10) or 10)
    except (ValueError, TypeError):
        speed_mb = 10
    try:
        price = float(request.form.get("price", 1000) or 1000)
    except (ValueError, TypeError):
        price = 1000.0
    speed_mb = max(1, speed_mb)
    price = max(0.0, price)
    description = (request.form.get("description") or "").strip()

    conn = db.get_db()
    item = conn.execute("SELECT id FROM tariffs WHERE id = ?", (id,)).fetchone()
    if not item:
        conn.close()
        flash("Package not found.", "danger")
        return redirect(url_for("tariffs_list"))

    conn.execute("""
        UPDATE tariffs 
        SET name = ?, speed_mb = ?, price = ?, description = ?
        WHERE id = ?
    """, (name, speed_mb, price, description, id))
    conn.commit()
    conn.close()
    flash(f"Package '{name}' updated successfully!", "success")
    return redirect(url_for("tariffs_list"))

@app.route("/tariffs/delete/<int:id>", methods=["POST"])
@admin_only
def delete_tariff(id):
    conn = db.get_db()
    item = conn.execute("SELECT id FROM tariffs WHERE id = ?", (id,)).fetchone()
    if not item:
        conn.close()
        flash("Package not found.", "danger")
        return redirect(url_for("tariffs_list"))

    in_use = conn.execute("SELECT COUNT(*) FROM customers WHERE tariff_id = ?", (id,)).fetchone()[0]
    if in_use > 0:
        flash(f"Cannot delete package: {in_use} customers are currently subscribed to it!", "danger")
    else:
        conn.execute("DELETE FROM tariffs WHERE id = ?", (id,))
        conn.commit()
        flash("Package removed successfully.", "info")
    conn.close()
    return redirect(url_for("tariffs_list"))

# ================= SETTINGS =================
@app.route("/settings", methods=["GET", "POST"])
@admin_only
def settings_page():
    conn = db.get_db()
    if request.method == "POST":
        setting_keys = [
            "isp_name", "tagline", "phone", "business_whatsapp", "email", "address", "currency",
            "jazzcash_no", "easypaisa_no", "bank_info",
            "agency_name", "agency_tagline", "agency_url"
        ]
        for key in setting_keys:
            val = request.form.get(key)
            if val is not None:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val.strip()))
        conn.commit()
        flash("System, Payment Accounts & Business WhatsApp settings updated successfully!", "success")
        return redirect(url_for("settings_page"))

    conn.close()
    storage_engine = db.get_storage_engine_name()
    is_turso = db.is_turso()
    return render_template("settings.html", storage_engine=storage_engine, is_turso=is_turso)

# ================= DATABASE BACKUP DOWNLOAD =================
@app.route("/backup/db")
@admin_only
def backup_db():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sabro_networks_backup_{timestamp}.db"
    
    # Create an atomic point-in-time snapshot using SQLite's native backup API
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, filename)
    try:
        db.safe_backup_to_file(temp_path)
        with open(temp_path, "rb") as f:
            backup_bytes = f.read()
        try:
            os.remove(temp_path)
        except OSError:
            pass
        return send_file(
            io.BytesIO(backup_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype="application/octet-stream"
        )
    except Exception:
        # Fallback to direct path if temp creation encounters OS restriction
        return send_file(db.DB_PATH, as_attachment=True, download_name=filename, mimetype="application/octet-stream")

# ================= EXPORT =================
@app.route("/export/customers")
@admin_only
def export_customers():
    conn = db.get_db()
    customers = conn.execute("""
        SELECT c.id, c.full_name, c.pppoe_username, c.phone, c.address, c.area, 
               t.name as plan, t.price as price, c.status, c.expiry_date
        FROM customers c
        LEFT JOIN tariffs t ON c.tariff_id = t.id
        ORDER BY c.id ASC
    """).fetchall()
    conn.close()

    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens Urdu/special chars without corruption
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(["ID", "Customer Name", "PPPoE Username", "Phone", "Address", "Area", "Plan", "Price (PKR)", "Status", "Expiry Date"])
    for r in customers:
        writer.writerow(list(r))
    
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment;filename=sabro_ftth_customers.csv"}
    )

# ================= BULK CSV IMPORT / UPLOAD =================
@app.route("/import/customers", methods=["POST"])
@admin_only
def import_customers():
    file = request.files.get("csv_file")
    if not file or file.filename == '':
        flash("No CSV file selected for upload.", "danger")
        return redirect(url_for("customers_list"))
    
    if not file.filename.lower().endswith('.csv'):
        flash("Invalid file format. Please upload a standard .csv file.", "danger")
        return redirect(url_for("customers_list"))
    
    try:
        stream = io.StringIO(file.stream.read().decode("utf-8-sig", errors="ignore"))
        reader = csv.reader(stream)
        raw_headers = next(reader, [])
        headers = [h.strip().lower() for h in raw_headers]
        
        def find_col(possible_names):
            for name in possible_names:
                for idx, h in enumerate(headers):
                    if name in h:
                        return idx
            return -1

        name_idx = find_col(["customer name", "full_name", "name", "subscriber"])
        user_idx = find_col(["pppoe_username", "pppoe username", "username", "pppoe", "user"])
        phone_idx = find_col(["phone", "mobile", "contact", "cell"])
        addr_idx = find_col(["address", "addr", "location"])
        area_idx = find_col(["area", "sector", "zone", "mohalla"])
        plan_idx = find_col(["plan", "package", "tariff", "speed"])
        pole_idx = find_col(["db_box", "pole", "fdb", "box"])
        core_idx = find_col(["fiber_core", "core", "color", "colour"])

        if name_idx == -1 and user_idx == -1:
            flash("CSV file must contain a 'Customer Name' or 'PPPoE Username' column header.", "danger")
            return redirect(url_for("customers_list"))

        conn = db.get_db()
        tariffs = conn.execute("SELECT id, name, speed_mb FROM tariffs").fetchall()
        tariff_map = {t["name"].lower(): t["id"] for t in tariffs}
        for t in tariffs:
            tariff_map[f"{t['speed_mb']}mb"] = t["id"]
            tariff_map[f"{t['speed_mb']} mb"] = t["id"]
            tariff_map[f"{t['speed_mb']}"] = t["id"]
        default_tariff_id = tariffs[0]["id"] if tariffs else None

        imported_count = 0
        skipped_count = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        expiry_str = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        for row in reader:
            if not row or all(c.strip() == '' for c in row):
                continue
            name = row[name_idx].strip() if name_idx != -1 and name_idx < len(row) else ""
            username = row[user_idx].strip() if user_idx != -1 and user_idx < len(row) else ""
            phone = row[phone_idx].strip() if phone_idx != -1 and phone_idx < len(row) else ""
            addr = row[addr_idx].strip() if addr_idx != -1 and addr_idx < len(row) else ""
            area = row[area_idx].strip() if area_idx != -1 and area_idx < len(row) else "Sector A"
            plan_str = row[plan_idx].strip().lower() if plan_idx != -1 and plan_idx < len(row) else ""
            pole = row[pole_idx].strip() if pole_idx != -1 and pole_idx < len(row) else "Pole #01"
            core = row[core_idx].strip() if core_idx != -1 and core_idx < len(row) else "Core 1 (Blue)"

            if not name and not username:
                continue

            if not name:
                name = username.capitalize()
            if not username:
                clean_name = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
                username = f"{clean_name}.ftth"

            # Check if username already exists
            existing = conn.execute("SELECT id FROM customers WHERE pppoe_username = ?", (username,)).fetchone()
            if existing:
                skipped_count += 1
                continue

            # Tariff matching
            tariff_id = tariff_map.get(plan_str, default_tariff_id)

            conn.execute("""
                INSERT INTO customers (
                    full_name, pppoe_username, password, phone, address, area,
                    tariff_id, status, expiry_date, onu_serial, db_box, fiber_core, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Active', ?, '', ?, ?, ?)
            """, (name, username, "sabro1234", phone, addr, area, tariff_id, expiry_str, pole, core, now_str))
            imported_count += 1

        conn.commit()
        conn.close()

        if imported_count > 0:
            flash(f"Successfully uploaded and imported {imported_count} subscriber(s)! ({skipped_count} skipped)", "success")
        else:
            flash(f"No new subscribers were imported. ({skipped_count} duplicate or invalid entries skipped)", "warning")
            
    except Exception as e:
        flash(f"Error reading CSV file: {str(e)}", "danger")

    return redirect(url_for("customers_list"))


# ================= DATABASE BACKUP RESTORE / UPLOAD =================
@app.route("/restore/db", methods=["POST"])
@admin_only
def restore_db():
    file = request.files.get("backup_file")
    if not file or file.filename == '':
        flash("No backup file selected.", "danger")
        return redirect(url_for("settings_page"))
    
    header = file.stream.read(16)
    if header != b"SQLite format 3\x00":
        flash("Invalid backup file. The uploaded file is not a valid SQLite database.", "danger")
        return redirect(url_for("settings_page"))
    
    file.stream.seek(0)
    uploaded_bytes = file.stream.read()

    # Create safety backup of current database first
    safety_name = f"sabro_pre_restore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    safety_path = os.path.join(tempfile.gettempdir(), safety_name)
    try:
        db.safe_backup_to_file(safety_path)
    except Exception:
        pass

    temp_restored = os.path.join(tempfile.gettempdir(), f"uploaded_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    try:
        with open(temp_restored, "wb") as f:
            f.write(uploaded_bytes)
        
        # Test connecting and running integrity check on uploaded db
        test_conn = sqlite3.connect(temp_restored)
        res = test_conn.execute("PRAGMA integrity_check;").fetchone()
        test_conn.close()
        if not res or res[0] != "ok":
            flash("Database integrity check failed on the uploaded file.", "danger")
            return redirect(url_for("settings_page"))
        
        # Safely restore into active database
        if db.is_turso():
            src_conn = sqlite3.connect(temp_restored)
            turso_conn = db.get_db()
            tables = [r[0] for r in src_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
            for table in tables:
                turso_conn.execute(f"DELETE FROM {table};")
                rows = src_conn.execute(f"SELECT * FROM {table};").fetchall()
                if rows:
                    cols = [col[1] for col in src_conn.execute(f"PRAGMA table_info({table})").fetchall()]
                    placeholders = ", ".join(["?"] * len(cols))
                    for r in rows:
                        turso_conn.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})", list(r))
            turso_conn.close()
            src_conn.close()
        else:
            dest_conn = sqlite3.connect(db.DB_PATH, timeout=15.0)
            src_conn = sqlite3.connect(temp_restored)
            src_conn.backup(dest_conn)
            src_conn.close()
            dest_conn.close()
        
        try:
            os.remove(temp_restored)
        except OSError:
            pass

        flash("Database backup successfully uploaded and restored! All data has been synchronized.", "success")
    except Exception as e:
        flash(f"Error restoring database: {str(e)}", "danger")

    return redirect(url_for("settings_page"))



# ================= CONNECT DEALER PANEL SYNC =================
@app.route("/dealer/sync", methods=["GET"])
@admin_only
def dealer_sync_page():
    conn = db.get_db()
    config = conn.execute("SELECT * FROM dealer_sync_config WHERE id = 1").fetchone()
    if not config:
        conn.execute("INSERT OR IGNORE INTO dealer_sync_config (id, portal_url, dealer_username) VALUES (1, 'https://dealer.connect.net.pk', 'sabro.dealer')")
        conn.commit()
        config = conn.execute("SELECT * FROM dealer_sync_config WHERE id = 1").fetchone()
        
    logs = conn.execute("SELECT * FROM dealer_sync_logs ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return render_template("dealer_sync.html", config=config, logs=logs)

@app.route("/dealer/sync/save_config", methods=["POST"])
@admin_only
def dealer_sync_save_config():
    portal_url = request.form.get("portal_url", "https://dealer.connect.net.pk").strip()
    dealer_username = request.form.get("dealer_username", "").strip()
    dealer_password = request.form.get("dealer_password", "").strip()
    auto_sync_interval = request.form.get("auto_sync_interval", "Manual").strip()
    
    conn = db.get_db()
    existing = conn.execute("SELECT dealer_password FROM dealer_sync_config WHERE id = 1").fetchone()
    if not dealer_password and existing and existing["dealer_password"]:
        dealer_password = existing["dealer_password"]
        
    conn.execute("""
        UPDATE dealer_sync_config 
        SET portal_url = ?, dealer_username = ?, dealer_password = ?, auto_sync_interval = ?
        WHERE id = 1
    """, (portal_url, dealer_username, dealer_password, auto_sync_interval))
    conn.commit()
    conn.close()
    flash("Connect Dealer panel configuration updated successfully!", "success")
    return redirect(url_for("dealer_sync_page"))

@app.route("/dealer/sync/run", methods=["POST"])
@admin_only
def dealer_sync_run():
    conn = db.get_db()
    config = conn.execute("SELECT * FROM dealer_sync_config WHERE id = 1").fetchone()
    conn.close()
    
    portal_url = config["portal_url"] if config else "https://dealer.connect.net.pk"
    username = config["dealer_username"] if config else ""
    password = config["dealer_password"] if config else ""
    
    client = dealer_client.ConnectDealerClient(portal_url=portal_url, username=username, password=password)
    subscribers = client.pull_subscribers()
    res = dealer_client.reconcile_dealer_data(subscribers, source_label="Live Connect Portal Pull")
    
    if res["success"]:
        flash(f"Sync Successful! Scanned {res['total_scanned']} accounts: {res['updated_count']} renewed/updated, {res['created_count']} newly provisioned.", "success")
    else:
        flash(f"Sync notice: {res.get('message', 'No changes recorded.')}", "warning")
        
    return redirect(url_for("dealer_sync_page"))

@app.route("/dealer/sync/upload", methods=["POST"])
@admin_only
def dealer_sync_upload():
    if "dealer_file" not in request.files:
        flash("No file was uploaded. Please select a CSV or Excel export sheet.", "danger")
        return redirect(url_for("dealer_sync_page"))
        
    file = request.files["dealer_file"]
    if not file or file.filename == "":
        flash("Please select a valid Connect Communications export file.", "danger")
        return redirect(url_for("dealer_sync_page"))
        
    try:
        subscribers = dealer_client.ConnectDealerClient.parse_uploaded_sheet(file.stream, filename=file.filename)
        if not subscribers:
            flash("Could not detect subscriber records or username column in uploaded file. Please check file format.", "danger")
            return redirect(url_for("dealer_sync_page"))
            
        res = dealer_client.reconcile_dealer_data(subscribers, source_label=f"Sheet Import ({file.filename})")
        if res["success"]:
            flash(f"Sheet Ingestion Successful! {res['total_scanned']} records processed: {res['updated_count']} updated, {res['created_count']} newly added.", "success")
        else:
            flash(f"Sheet reconciliation notice: {res.get('message', 'No records changed.')}", "warning")
    except Exception as e:
        flash(f"Error reading dealer export sheet: {str(e)}", "danger")
        
    return redirect(url_for("dealer_sync_page"))

@app.route("/dealer/sync/test_connection", methods=["POST"])
@admin_only
def dealer_sync_test_connection():
    conn = db.get_db()
    config = conn.execute("SELECT * FROM dealer_sync_config WHERE id = 1").fetchone()
    conn.close()
    
    portal_url = config["portal_url"] if config else "https://dealer.connect.net.pk"
    username = config["dealer_username"] if config else ""
    password = config["dealer_password"] if config else ""
    
    client = dealer_client.ConnectDealerClient(portal_url=portal_url, username=username, password=password)
    res = client.test_connection()
    if res["success"]:
        flash(f"Portal Diagnostic: {res['status']} - {res['message']}", "info")
    else:
        flash(f"Portal Diagnostic Failed: {res['message']}", "danger")
        
    return redirect(url_for("dealer_sync_page"))


# ================= ERROR HANDLERS =================
@app.errorhandler(404)
def page_not_found(e):
    try:
        return render_template("404.html"), 404
    except Exception:
        return """<!DOCTYPE html><html><head><meta charset="utf-8"><title>404 Not Found | Sabro Networks</title><style>body{background:#0b0f19;color:#f3f4f6;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}div{background:#111827;border:1px solid #1f2937;padding:40px;border-radius:12px;text-align:center;max-width:480px;}h1{color:#60a5fa;margin:0 0 10px;}p{color:#9ca3af;margin-bottom:20px;}a{background:#2563eb;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;}</style></head><body><div><h1>404</h1><h3>Page Not Found</h3><p>The requested endpoint does not exist.</p><a href="/dashboard">Back to Dashboard</a></div></body></html>""", 404

@app.errorhandler(500)
def internal_server_error(e):
    try:
        return render_template("500.html"), 500
    except Exception:
        return """<!DOCTYPE html><html><head><meta charset="utf-8"><title>500 Server Notice | Sabro Networks</title><style>body{background:#0b0f19;color:#f3f4f6;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}div{background:#111827;border:1px solid #1f2937;padding:40px;border-radius:12px;text-align:center;max-width:480px;}h1{color:#ef4444;margin:0 0 10px;}p{color:#9ca3af;margin-bottom:20px;}a{background:#2563eb;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;}</style></head><body><div><h1>500</h1><h3>Temporary System Notice</h3><p>The server encountered a temporary condition. Data remains protected.</p><a href="/dashboard">Back to Dashboard</a></div></body></html>""", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1", "t")
    print("=" * 65)
    print("  Sabro Networks (FTTH)")
    print("  Enterprise ISP Billing, Recovery, Ticketing & Staff Logins")
    print(f"  Local / Server URL: http://0.0.0.0:{port}")
    print("=" * 65)
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
