# 🌐 Sabro Networks &bull; FTTH Telecom & Operations Management System

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-black.svg?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Database](https://img.shields.io/badge/SQLite-WAL%20High--Concurrency-003B57.svg?logo=sqlite&logoColor=white)](https://sqlite.org/)
[![Tests](https://img.shields.io/badge/Tests-24%2F24%20Passing%20(100%25)-success.svg)](#-test-suite)
[![License](https://img.shields.io/badge/License-Proprietary-orange.svg)](#)

An enterprise-grade, sober, and elegant operations platform designed specifically for FTTH (Fiber-To-The-Home) Internet Service Providers. Built to replace cluttered legacy panels with high-efficiency, role-segregated operational desks for NOC Admins, Field Technicians, and Bill Recovery Agents.

---

## 🚀 Key Architectural Highlights

* **🎯 100% Role-Isolated Desks**:
  * **Admin / NOC Supervisor**: Dedicated Complaints Queue, Optical telemetry indicators, technician dispatch, capacity duty roster, capital investments, and full system management. Zero irrelevant billing or dealer clutter on the primary dashboard.
  * **Complaint Boy (Field Fiber Technician)**: Isolated work orders desk showing only assigned fiber faults, drop line lookups, optical core colors, and an integrated gamified XP leveling system (Tiers 1–5).
  * **Recovery Boy (Field Collector)**: Dedicated dues recovery desk, pending amounts, 1-click cash collection with instant subscriber validity extension, and friendly Roman Urdu WhatsApp reminders.
* **⚡ 1-Click Telecom WhatsApp Automations**:
  * **Customer Bill Reminders**: Short, polite, and friendly Roman Urdu notifications with zero tech/hardware dumps.
  * **Field Tech Dispatch**: Pre-formatted ticket details (FDB box, drop fiber core color, subscriber address) delivered directly to technician WhatsApp.
  * **Restoration Notice**: Automated ticket resolved messages sent directly to subscribers upon fiber splice completion.
  * **Bulk Defaulters Summary**: Generates a consolidated recovery list with single-tap messaging.
* **🌐 FTTH Physical Plant Tracking**:
  * Tracks ONU Serials, Fiber Distribution Boxes (FDB), Pole numbers, CNIC records, and Drop Fiber Cores (Blue, Orange, Green, Brown) with visual color badges.
* **🛡️ Security & Enterprise Concurrency**:
  * SQLite configured with **Write-Ahead Logging (WAL)** and 25s busy timeout for high-concurrency environments.
  * PBKDF2/scrypt cryptographic password hashing with automatic legacy upgrade.
  * `HttpOnly` and `SameSite=Lax` session cookie protection.
  * Safe live binary database backups via SQLite Backup API.

---

## 👥 Default Demo Credentials

| Role | Username | Password | Dedicated Focus & Desk |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin` | `admin123` | Full NOC & complaints desk, staff roster, packages, backups |
| **Complaint Boy** | `rashid.tech` | `tech123` | Field technician work orders, fiber lookup, resolve tickets |
| **Recovery Boy** | `tariq.rec` | `rec123` | Unpaid dues recovery desk, cash collections, Roman Urdu reminders |

---

## 💻 Tech Stack

* **Backend**: Python 3.10+, Flask 3.x
* **Database**: SQLite 3 with WAL Journaling (`PRAGMA journal_mode=WAL;`)
* **Frontend**: Bootstrap 5.3, Bootstrap Icons, Plus Jakarta Sans & JetBrains Mono typography, Chart.js
* **Server Engines**: Gunicorn (Linux/Cloud), Waitress (Windows/Production), Flask WSGI (Development)

---

## ⚡ Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/sabro-networks-portal.git
cd sabro-networks-portal
```

### 2. Set Up Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Initialize Database
```bash
# Initializes tables, performance indexes, and default seed staff
python init_db.py
```

### 5. Launch the Application
```bash
# Development Server
python app.py

# Production Server (Windows)
waitress-serve --listen=0.0.0.0:5000 app:app

# Production Server (Linux)
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

Open your browser at **`http://127.0.0.1:5000`** and log in with any of the accounts listed above.

---

## 🧪 Test Suite

The system includes 24 regression, security, role-boundary, and lifecycle unit tests:

```bash
python -m unittest test_security_suite.py test_enterprise_suite.py test_company_system.py
```

### Test Coverage Highlights
* `[PASS]` Clean digital bill slip verification (zero PPPoE/hardware clutter).
* `[PASS]` Role isolation barriers (Recovery Boy and Complaint Boy boundaries).
* `[PASS]` FTTH subscriber lifecycle (Creation, FTTH specs, Deposit, Edit).
* `[PASS]` 6 Telecom WhatsApp automations (Welcome, Reminder, Invoice, Dispatch, Resolution, Defaulters).
* `[PASS]` Gamified technician leveling system (Tiers 1–5, +XP on resolve).
* `[PASS]` Automated database backup integrity.

---

## 📁 Project Structure

```text
├── app.py                     # Main Flask application & route controllers
├── db.py                      # Database schema, migrations, connection pool & seeds
├── init_db.py                 # CLI database initializer & seeder
├── dealer_client.py           # Upstream Connect Communications integration
├── templates/                 # Jinja2 template views
│   ├── base.html              # Sober corporate layout with role-specific navigation
│   ├── dashboard.html         # Multi-role dashboard (NOC, Tech Desk, Recovery Desk)
│   ├── login.html             # High-contrast corporate login screen
│   ├── customers.html         # FTTH subscriber management & optical parameters
│   ├── invoices.html          # Invoices & billing recovery desk
│   ├── tickets.html           # Complaint tickets management & technician assignment
│   ├── staff.html             # Staff accounts & PFP management
│   ├── expenses.html          # Daily expense tracker (Kharcha)
│   ├── investments.html       # Capital investment tracker
│   ├── tariffs.html           # FTTH speed packages & tariffs
│   └── settings.html          # ISP branding & WhatsApp configuration
├── static/                    # Static assets
│   ├── img/                   # Logos, default SVG avatars, favicon
│   └── uploads/pfp/           # User profile picture upload destination
├── requirements.txt           # Python package dependencies
├── .env.example               # Environment variables template
├── .gitignore                 # Production Git ignore rules
└── test_*.py                  # Automated test suites
```

---

## 📜 License & Ownership

Developed for **Sabro Networks (FTTH)** in partnership with **Vshatkay Solutions Agency**.
All rights reserved.
