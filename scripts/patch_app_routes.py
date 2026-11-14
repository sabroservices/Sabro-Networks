with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add /profile/update_pfp route
pfp_route = '''
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

'''

if '/profile/update_pfp' not in text:
    staff_marker = '# ================= STAFF & USER LOGINS (ADD, EDIT, DELETE) ================='
    text = text.replace(staff_marker, pfp_route + staff_marker)
    print("Added /profile/update_pfp route")

# 2. Update staff_list in app.py
old_staff_list = '''@app.route("/staff")
@admin_only
def staff_list():
    conn = db.get_db()
    staff_members = conn.execute("""
        SELECT u.*, 
               (SELECT COUNT(*) FROM tickets t WHERE t.assigned_user_id = u.id AND t.status != 'Resolved') as assigned_tickets,
               (SELECT COUNT(*) FROM invoices i WHERE i.collected_by_staff_id = u.id) as collected_invoices_count
        FROM users u
        ORDER BY u.id ASC
    """).fetchall()
    conn.close()
    return render_template("staff.html", staff_members=staff_members)'''

new_staff_list = '''@app.route("/staff")
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
    return render_template("staff.html", staff_members=staff_members)'''

if old_staff_list in text:
    text = text.replace(old_staff_list, new_staff_list)
    print("Updated staff_list with PFP and Level info")

# 3. Update add_staff in app.py to handle pfp_file
old_add_staff_insert = '''        conn.execute("""
            INSERT INTO users (full_name, username, password, role, phone, assigned_area, status, total_collected, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?)
        """, (full_name, username, hashed_password, role, phone, assigned_area, status, created_at))
        conn.commit()'''

new_add_staff_insert = '''        cursor = conn.cursor()
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
        conn.commit()'''

if old_add_staff_insert in text:
    text = text.replace(old_add_staff_insert, new_add_staff_insert)
    print("Updated add_staff with PFP upload support")

# 4. Update edit_staff in app.py to handle pfp_file
old_edit_staff_update = '''        conn.execute("""
            UPDATE users 
            SET full_name = ?, username = ?, password = ?, role = ?, phone = ?, assigned_area = ?, status = ?
            WHERE id = ?
        """, (full_name, username, hashed_password, role, phone, assigned_area, status, id))
        conn.commit()'''

new_edit_staff_update = '''        conn.execute("""
            UPDATE users 
            SET full_name = ?, username = ?, password = ?, role = ?, phone = ?, assigned_area = ?, status = ?
            WHERE id = ?
        """, (full_name, username, hashed_password, role, phone, assigned_area, status, id))
        pfp_file = request.files.get("pfp_file")
        if pfp_file and pfp_file.filename:
            rel_pfp = save_pfp_upload(pfp_file, id)
            if rel_pfp:
                conn.execute("UPDATE users SET pfp_image = ? WHERE id = ?", (rel_pfp, id))
        conn.commit()'''

if old_edit_staff_update in text:
    text = text.replace(old_edit_staff_update, new_edit_staff_update)
    print("Updated edit_staff with PFP upload support")

# 5. Award XP in edit_ticket when marked Resolved
old_edit_ticket_award = '''    conn.execute("""
        UPDATE tickets 
        SET subject = ?, details = ?, priority = ?, status = ?, assigned_user_id = ?, resolution_notes = ?, resolved_at = ?
        WHERE id = ?
    """, (subject, details, priority, status, assigned_user_id, resolution_notes, resolved_at, id))
    conn.commit()'''

new_edit_ticket_award = '''    conn.execute("""
        UPDATE tickets 
        SET subject = ?, details = ?, priority = ?, status = ?, assigned_user_id = ?, resolution_notes = ?, resolved_at = ?
        WHERE id = ?
    """, (subject, details, priority, status, assigned_user_id, resolution_notes, resolved_at, id))
    if status == "Resolved" and assigned_user_id:
        xp_gain = 180 if priority == "Critical" else 120
        conn.execute("UPDATE users SET technician_xp = technician_xp + ? WHERE id = ?", (xp_gain, assigned_user_id))
    conn.commit()'''

if old_edit_ticket_award in text:
    text = text.replace(old_edit_ticket_award, new_edit_ticket_award)
    print("Updated edit_ticket with XP awarding")

# 6. Update dashboard for Complaint Boy
old_tech_dash = '''        conn.close()
        return render_template("dashboard.html",
                               my_assigned_tickets=my_assigned_tickets,
                               my_assigned_count=len(my_assigned_tickets),
                               my_resolved_count=my_resolved_count,
                               open_field_tickets=open_field_tickets,
                               recent_resolved_tickets=recent_resolved_tickets)'''

new_tech_dash = '''        u_row = conn.execute("SELECT technician_xp FROM users WHERE id = ?", (user_id,)).fetchone()
        tech_xp = u_row["technician_xp"] if u_row else 0
        tech_level_info = calculate_technician_level(my_resolved_count, tech_xp)
        conn.close()
        return render_template("dashboard.html",
                               my_assigned_tickets=my_assigned_tickets,
                               my_assigned_count=len(my_assigned_tickets),
                               my_resolved_count=my_resolved_count,
                               open_field_tickets=open_field_tickets,
                               recent_resolved_tickets=recent_resolved_tickets,
                               tech_level_info=tech_level_info)'''

if old_tech_dash in text:
    text = text.replace(old_tech_dash, new_tech_dash)
    print("Updated Complaint Boy dashboard with tech_level_info")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("patch_app_routes.py completed")
