with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add PFP and Leveling functions before inject_globals
pfp_level_functions = '''ALLOWED_PFP_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

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

    return {
        "level": lvl,
        "title": title,
        "badge_color": badge_color,
        "icon": icon,
        "resolved_count": resolved_count,
        "progress_pct": min(100, max(0, progress_pct)),
        "tickets_to_next": tickets_to_next,
        "next_level_req": next_req,
        "xp": calculated_xp
    }

def get_user_avatar(user_dict_or_row):
    """Returns avatar URL (uploaded custom PFP or role-based high-tech SVG)."""
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
        full_path = os.path.join(app.root_path, "static", pfp.replace("/", os.sep))
        if os.path.exists(full_path):
            return url_for('static', filename=pfp)

    if role == "Complaint Boy":
        return url_for('static', filename='img/avatar_complaint.svg')
    elif role == "Recovery Boy":
        return url_for('static', filename='img/avatar_recovery.svg')
    return url_for('static', filename='img/avatar_admin.svg')

def save_pfp_upload(file_storage, user_id):
    """Saves uploaded PFP image to static/uploads/pfp/ and returns relative path."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext not in ALLOWED_PFP_EXTENSIONS:
        return None
    
    upload_dir = os.path.join(app.root_path, "static", "uploads", "pfp")
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"pfp_{user_id}_{int(datetime.now().timestamp())}.{ext}"
    dest_path = os.path.join(upload_dir, filename)
    file_storage.save(dest_path)
    return f"uploads/pfp/{filename}"

'''

old_inject = '''@app.context_processor
def inject_globals():
    settings = get_settings()
    current_user = None
    if "user_id" in session:
        current_user = {
            "id": session.get("user_id"),
            "name": session.get("user_name"),
            "username": session.get("username"),
            "role": session.get("user_role"),
            "area": session.get("user_area")
        }
    return dict(
        settings=settings, 
        current_user=current_user,
        now_year=datetime.now().year,
        now_month=datetime.now().strftime("%B %Y")
    )'''

new_inject = '''@app.context_processor
def inject_globals():
    settings = get_settings()
    current_user = None
    if "user_id" in session:
        conn = db.get_db()
        u_row = conn.execute("SELECT * FROM users WHERE id = ?", (session.get("user_id"),)).fetchone()
        if u_row:
            avatar = get_user_avatar(u_row)
            level_info = None
            if u_row["role"] == "Complaint Boy":
                resolved_c = conn.execute("SELECT COUNT(*) FROM tickets WHERE assigned_user_id = ? AND status = 'Resolved'", (u_row["id"],)).fetchone()[0]
                level_info = calculate_technician_level(resolved_c, u_row["technician_xp"])
            
            current_user = {
                "id": u_row["id"],
                "name": u_row["full_name"],
                "username": u_row["username"],
                "role": u_row["role"],
                "area": u_row["assigned_area"],
                "phone": u_row["phone"],
                "pfp_image": u_row["pfp_image"],
                "avatar_url": avatar,
                "level_info": level_info
            }
        conn.close()
    return dict(
        settings=settings, 
        current_user=current_user,
        now_year=datetime.now().year,
        now_month=datetime.now().strftime("%B %Y"),
        clean_whatsapp_phone=clean_whatsapp_phone,
        get_user_avatar=get_user_avatar,
        calculate_technician_level=calculate_technician_level
    )'''

target_marker = '@app.context_processor\ndef inject_globals():'
if target_marker in text and 'calculate_technician_level' not in text:
    text = text.replace(target_marker, pfp_level_functions + target_marker)
    text = text.replace(old_inject, new_inject)
    print("Added PFP and leveling functions and updated inject_globals")
else:
    print("PFP functions already in text or marker not found")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)
