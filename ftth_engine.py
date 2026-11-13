"""
FTTH / GPON Network Engineering Engine for Sabro Networks
Provides optical link budget calculations, TIA-598 fiber color coding,
and topology aggregation for OLTs, PON ports, and Splitters (FDBs).
"""

# Standard TIA-598 Optical Fiber Color Codes
TIA_598_COLORS = [
    {"num": 1, "name": "Blue", "hex": "#2563eb", "text": "text-white"},
    {"num": 2, "name": "Orange", "hex": "#ea580c", "text": "text-white"},
    {"num": 3, "name": "Green", "hex": "#16a34a", "text": "text-white"},
    {"num": 4, "name": "Brown", "hex": "#854d0e", "text": "text-white"},
    {"num": 5, "name": "Slate / Grey", "hex": "#64748b", "text": "text-white"},
    {"num": 6, "name": "White", "hex": "#f8fafc", "text": "text-dark"},
    {"num": 7, "name": "Red", "hex": "#dc2626", "text": "text-white"},
    {"num": 8, "name": "Black", "hex": "#0f172a", "text": "text-white"},
    {"num": 9, "name": "Yellow", "hex": "#eab308", "text": "text-dark"},
    {"num": 10, "name": "Violet / Purple", "hex": "#9333ea", "text": "text-white"},
    {"num": 11, "name": "Rose / Pink", "hex": "#ec4899", "text": "text-white"},
    {"num": 12, "name": "Aqua / Cyan", "hex": "#06b6d4", "text": "text-dark"},
]

SPLITTER_LOSS_RATIOS = {
    "1:2": 3.7,
    "1:4": 7.3,
    "1:8": 10.5,
    "1:16": 13.8,
    "1:32": 17.2,
    "1:64": 20.8
}

def calculate_optical_budget(olt_tx_power_dbm=3.5, distance_meters=800, splitter_ratios=None):
    """
    Calculates optical link budget for GPON Class B+/C+ link.
    Fiber attenuation: ~0.35 dB/km @ 1310nm
    Splice & connector losses: ~0.5 dB
    """
    if splitter_ratios is None:
        splitter_ratios = ["1:8"]
    
    fiber_loss = (distance_meters / 1000.0) * 0.35
    connector_loss = 0.5 * (len(splitter_ratios) + 1)
    
    splitter_loss = sum(SPLITTER_LOSS_RATIOS.get(r, 10.5) for r in splitter_ratios)
    total_loss = fiber_loss + connector_loss + splitter_loss
    rx_power = round(olt_tx_power_dbm - total_loss, 2)
    
    if rx_power >= -21.0:
        quality = "Optimal"
        badge_class = "success"
    elif rx_power >= -24.0:
        quality = "Good"
        badge_class = "primary"
    elif rx_power >= -27.0:
        quality = "Acceptable"
        badge_class = "warning"
    else:
        quality = "Critical Weak Signal"
        badge_class = "danger"
        
    return {
        "tx_power_dbm": olt_tx_power_dbm,
        "fiber_distance_meters": distance_meters,
        "fiber_loss_db": round(fiber_loss, 2),
        "splitter_loss_db": round(splitter_loss, 2),
        "total_loss_db": round(total_loss, 2),
        "estimated_rx_power_dbm": rx_power,
        "quality": quality,
        "badge_class": badge_class
    }


def get_optical_color_info(core_number):
    """Returns color name and hex for a 1-12 fiber core index."""
    idx = (int(core_number) - 1) % 12
    return TIA_598_COLORS[idx]


def recalculate_splitter_ports(conn, splitter_id):
    """Updates used_ports count for a splitter based on customer assignments."""
    if not splitter_id:
        return
    count = conn.execute(
        "SELECT COUNT(*) FROM customers WHERE splitter_id = ?", (splitter_id,)
    ).fetchone()[0]
    conn.execute(
        "UPDATE splitters SET used_ports = ? WHERE id = ?", (count, splitter_id)
    )
    conn.commit()
