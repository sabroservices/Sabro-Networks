import os

img_dir = os.path.join('static', 'img')
os.makedirs(img_dir, exist_ok=True)

# 1. Admin Avatar (Dark Navy, Orange Core, Shield & Crown)
admin_svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <linearGradient id="adminGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a" />
      <stop offset="100%" stop-color="#1e293b" />
    </linearGradient>
    <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ea580c" />
      <stop offset="100%" stop-color="#f97316" />
    </linearGradient>
  </defs>
  <circle cx="50" cy="50" r="48" fill="url(#adminGrad)" stroke="url(#ringGrad)" stroke-width="4"/>
  <circle cx="50" cy="36" r="16" fill="#f8fafc" opacity="0.95"/>
  <path d="M22 80 C22 62, 34 56, 50 56 C66 56, 78 62, 78 80 Z" fill="#f8fafc" opacity="0.95"/>
  <path d="M42 20 L50 26 L58 20 L56 30 L44 30 Z" fill="#ea580c"/>
  <circle cx="80" cy="80" r="14" fill="#ea580c" stroke="#ffffff" stroke-width="2"/>
  <path d="M76 80 L79 83 L85 77" stroke="#ffffff" stroke-width="2" fill="none" stroke-linecap="round"/>
</svg>'''

# 2. Complaint Boy Avatar (Technician, Amber/Orange, Splicing Tool & Level Star)
complaint_svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <linearGradient id="compGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1c1917" />
      <stop offset="100%" stop-color="#292524" />
    </linearGradient>
    <linearGradient id="starGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b" />
      <stop offset="100%" stop-color="#d97706" />
    </linearGradient>
  </defs>
  <circle cx="50" cy="50" r="48" fill="url(#compGrad)" stroke="#f59e0b" stroke-width="4"/>
  <circle cx="50" cy="36" r="16" fill="#fef3c7" opacity="0.95"/>
  <path d="M22 80 C22 62, 34 56, 50 56 C66 56, 78 62, 78 80 Z" fill="#fef3c7" opacity="0.95"/>
  <!-- Safety Helmet / Cap -->
  <path d="M32 32 C32 20, 68 20, 68 32 Z" fill="#f59e0b"/>
  <!-- Level Badge Star on bottom right -->
  <circle cx="80" cy="80" r="15" fill="url(#starGrad)" stroke="#ffffff" stroke-width="2"/>
  <polygon points="80,70 83,76 89,77 85,82 86,88 80,85 74,88 75,82 71,77 77,76" fill="#ffffff"/>
</svg>'''

# 3. Recovery Boy Avatar (Emerald Green, Bike & Cash Bag)
recovery_svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <linearGradient id="recGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#064e3b" />
      <stop offset="100%" stop-color="#047857" />
    </linearGradient>
  </defs>
  <circle cx="50" cy="50" r="48" fill="url(#recGrad)" stroke="#10b981" stroke-width="4"/>
  <circle cx="50" cy="36" r="16" fill="#ecfdf5" opacity="0.95"/>
  <path d="M22 80 C22 62, 34 56, 50 56 C66 56, 78 62, 78 80 Z" fill="#ecfdf5" opacity="0.95"/>
  <!-- Cash Collection Coin on bottom right -->
  <circle cx="80" cy="80" r="14" fill="#10b981" stroke="#ffffff" stroke-width="2"/>
  <text x="80" y="85" font-size="14" font-weight="bold" fill="#ffffff" text-anchor="middle" font-family="sans-serif">Rs</text>
</svg>'''

with open(os.path.join(img_dir, 'avatar_admin.svg'), 'w', encoding='utf-8') as f:
    f.write(admin_svg)

with open(os.path.join(img_dir, 'avatar_complaint.svg'), 'w', encoding='utf-8') as f:
    f.write(complaint_svg)

with open(os.path.join(img_dir, 'avatar_recovery.svg'), 'w', encoding='utf-8') as f:
    f.write(recovery_svg)

print("Default role avatars created in static/img/")
