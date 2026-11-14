-- Sabro Networks — Production PostgreSQL Migration 001
-- Target: Neon PostgreSQL / Cloudflare Hyperdrive / Pure Python pg8000
-- Preserves all relational structures, constraints, foreign keys, and indexes.

-- 1. System Settings
CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT
);

-- 2. Users & Staff Logins
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL, -- Admin, Recovery Boy, Complaint Boy, Staff
    phone VARCHAR(50) NOT NULL DEFAULT '',
    assigned_area VARCHAR(100) DEFAULT '',
    status VARCHAR(20) DEFAULT 'Active', -- Active, Inactive
    total_collected DOUBLE PRECISION DEFAULT 0.0,
    pfp_image TEXT DEFAULT '',
    technician_xp INTEGER DEFAULT 0,
    created_at VARCHAR(50)
);

-- 3. Tariffs / Packages
CREATE TABLE IF NOT EXISTS tariffs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    speed_mb INTEGER NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    description TEXT
);

-- 4. FTTH Subscribers / Customers
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    pppoe_username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL,
    phone VARCHAR(50),
    address TEXT,
    area VARCHAR(100),
    tariff_id INTEGER REFERENCES tariffs (id) ON DELETE SET NULL,
    status VARCHAR(20) DEFAULT 'Active', -- Active, Expired, Suspended
    expiry_date VARCHAR(50),
    onu_serial VARCHAR(100) DEFAULT '',
    db_box VARCHAR(100) DEFAULT '',
    fiber_core VARCHAR(50) DEFAULT '',
    cnic VARCHAR(50) DEFAULT '',
    installation_date VARCHAR(50),
    lat DOUBLE PRECISION DEFAULT 0.0,
    lng DOUBLE PRECISION DEFAULT 0.0,
    street VARCHAR(150) DEFAULT '',
    house_no VARCHAR(100) DEFAULT '',
    whatsapp VARCHAR(50) DEFAULT '',
    monthly_fee DOUBLE PRECISION DEFAULT 0.0,
    activation_date VARCHAR(50) DEFAULT '',
    onu_mac VARCHAR(100) DEFAULT '',
    router_model VARCHAR(100) DEFAULT '',
    olt_id INTEGER,
    splitter_id INTEGER,
    notes TEXT DEFAULT '',
    created_at VARCHAR(50)
);

-- 5. Invoices & Billing
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(100) UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    amount DOUBLE PRECISION NOT NULL,
    month_period VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'Unpaid', -- Paid, Unpaid, Overdue
    due_date VARCHAR(50),
    paid_date VARCHAR(50),
    payment_method VARCHAR(50), -- Cash, JazzCash, EasyPaisa, Bank Transfer
    collected_by_staff_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    paid_amount DOUBLE PRECISION DEFAULT 0.0,
    balance_due DOUBLE PRECISION DEFAULT 0.0,
    discount DOUBLE PRECISION DEFAULT 0.0,
    additional_charges DOUBLE PRECISION DEFAULT 0.0,
    notes TEXT DEFAULT '',
    created_at VARCHAR(50)
);

-- 6. Expenses Tracker
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    date VARCHAR(50) NOT NULL,
    paid_by VARCHAR(100),
    notes TEXT,
    created_at VARCHAR(50)
);

-- 7. Customer Deposits & Advances
CREATE TABLE IF NOT EXISTS deposits (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    deposit_type VARCHAR(100) NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    status VARCHAR(50) DEFAULT 'Held', -- Held, Refunded, Adjusted
    date VARCHAR(50) NOT NULL,
    notes TEXT,
    created_at VARCHAR(50)
);

-- 8. Capital Investments
CREATE TABLE IF NOT EXISTS investments (
    id SERIAL PRIMARY KEY,
    investor_name VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    category VARCHAR(100) NOT NULL,
    date VARCHAR(50) NOT NULL,
    notes TEXT,
    created_at VARCHAR(50)
);

-- 9. Upstream Dealer Sync Configuration & Logs
CREATE TABLE IF NOT EXISTS dealer_sync_config (
    id INTEGER PRIMARY KEY,
    portal_name VARCHAR(255) DEFAULT 'Connect Communications Dealer Portal',
    portal_url TEXT DEFAULT '',
    dealer_username VARCHAR(100) DEFAULT '',
    dealer_password VARCHAR(255) DEFAULT '',
    auto_sync_interval VARCHAR(50) DEFAULT 'Manual',
    last_sync_time VARCHAR(50),
    last_sync_status VARCHAR(100) DEFAULT 'Not Configured'
);

INSERT INTO dealer_sync_config (id, portal_url, dealer_username, last_sync_status)
VALUES (1, '', '', 'Not Configured')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS dealer_sync_logs (
    id SERIAL PRIMARY KEY,
    sync_time VARCHAR(50) NOT NULL,
    source VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    total_scanned INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    created_count INTEGER DEFAULT 0,
    details TEXT
);

-- 10. Complaint & Support Tickets
CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    ticket_number VARCHAR(100) UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    subject VARCHAR(255) NOT NULL,
    details TEXT,
    priority VARCHAR(50) DEFAULT 'Medium', -- Low, Medium, High, Critical
    status VARCHAR(50) DEFAULT 'Open', -- Open, In Progress, Resolved
    assigned_user_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    resolution_notes TEXT,
    category VARCHAR(100) DEFAULT 'Internet',
    contact_phone VARCHAR(50) DEFAULT '',
    created_at VARCHAR(50),
    resolved_at VARCHAR(50)
);

-- 11. MikroTik RouterOS Gateways
CREATE TABLE IF NOT EXISTS routers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    ip_address VARCHAR(100) NOT NULL,
    api_port INTEGER DEFAULT 8728,
    username VARCHAR(100) NOT NULL,
    password VARCHAR(255) NOT NULL,
    location VARCHAR(150) DEFAULT '',
    status VARCHAR(50) DEFAULT 'Online', -- Online, Offline, Unreachable
    last_seen VARCHAR(50),
    created_at VARCHAR(50)
);

-- 12. FTTH Optical Network Core: OLTs, PON Ports, Splitters, Fiber Cables & Cores
CREATE TABLE IF NOT EXISTS olts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    model VARCHAR(100) DEFAULT 'EPON/GPON OLT',
    ip_address VARCHAR(100) DEFAULT '',
    pon_ports_count INTEGER DEFAULT 8,
    location VARCHAR(150) DEFAULT '',
    status VARCHAR(50) DEFAULT 'Active', -- Active, Maintenance, Offline
    notes TEXT,
    created_at VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS pon_ports (
    id SERIAL PRIMARY KEY,
    olt_id INTEGER NOT NULL REFERENCES olts (id) ON DELETE CASCADE,
    port_number INTEGER NOT NULL,
    max_capacity INTEGER DEFAULT 64,
    optical_power_dbm DOUBLE PRECISION DEFAULT 3.5,
    status VARCHAR(50) DEFAULT 'Active'
);

CREATE TABLE IF NOT EXISTS splitters (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    olt_id INTEGER REFERENCES olts (id) ON DELETE SET NULL,
    pon_port_id INTEGER REFERENCES pon_ports (id) ON DELETE SET NULL,
    parent_splitter_id INTEGER,
    location VARCHAR(150) DEFAULT '',
    lat DOUBLE PRECISION DEFAULT 0.0,
    lng DOUBLE PRECISION DEFAULT 0.0,
    ratio VARCHAR(20) DEFAULT '1:8',
    max_ports INTEGER DEFAULT 8,
    used_ports INTEGER DEFAULT 0,
    loss_db DOUBLE PRECISION DEFAULT 10.5,
    notes TEXT,
    created_at VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS fiber_cables (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    capacity_cores INTEGER DEFAULT 12,
    start_point VARCHAR(150) DEFAULT '',
    end_point VARCHAR(150) DEFAULT '',
    length_meters DOUBLE PRECISION DEFAULT 0.0,
    status VARCHAR(50) DEFAULT 'Active',
    created_at VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS fiber_cores (
    id SERIAL PRIMARY KEY,
    cable_id INTEGER NOT NULL REFERENCES fiber_cables (id) ON DELETE CASCADE,
    core_number INTEGER NOT NULL,
    color_name VARCHAR(50) DEFAULT 'Blue',
    status VARCHAR(50) DEFAULT 'Free', -- Free, Spliced, Damaged, In Use
    customer_id INTEGER REFERENCES customers (id) ON DELETE SET NULL,
    notes TEXT
);

-- 13. Optical Inventory & Assets Ledger
CREATE TABLE IF NOT EXISTS inventory_items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL, -- ONU/ONT, Router, Drop Wire, Patch Cord, Joint Box, Connector, Tool
    unit VARCHAR(50) DEFAULT 'pcs',
    quantity INTEGER DEFAULT 0,
    unit_cost DOUBLE PRECISION DEFAULT 0.0,
    retail_price DOUBLE PRECISION DEFAULT 0.0,
    supplier VARCHAR(150) DEFAULT '',
    min_alert_threshold INTEGER DEFAULT 5,
    created_at VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS inventory_transactions (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES inventory_items (id) ON DELETE CASCADE,
    transaction_type VARCHAR(50) NOT NULL, -- Inbound, Outbound, Assigned, Damaged, Returned
    quantity INTEGER NOT NULL,
    recipient_type VARCHAR(50) DEFAULT '', -- Technician, Customer, Maintenance
    recipient_id INTEGER,
    notes TEXT,
    created_at VARCHAR(50)
);

-- 14. Field Installation Workflows
CREATE TABLE IF NOT EXISTS installations (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    technician_id INTEGER REFERENCES users (id) ON DELETE SET NULL,
    status VARCHAR(50) DEFAULT 'Scheduled', -- Scheduled, In Progress, Completed, Cancelled
    scheduled_date VARCHAR(50),
    drop_cable_length DOUBLE PRECISION DEFAULT 0.0,
    optical_power_dbm DOUBLE PRECISION DEFAULT -19.0,
    onu_mac VARCHAR(100) DEFAULT '',
    router_model VARCHAR(100) DEFAULT '',
    notes TEXT,
    completed_at VARCHAR(50),
    created_at VARCHAR(50)
);

-- 15. Production Performance Indexes
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_staff ON invoices(collected_by_staff_id);
CREATE INDEX IF NOT EXISTS idx_tickets_customer ON tickets(customer_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets(assigned_user_id, status);
CREATE INDEX IF NOT EXISTS idx_deposits_customer ON deposits(customer_id);
CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);
CREATE INDEX IF NOT EXISTS idx_customers_area ON customers(area);
CREATE INDEX IF NOT EXISTS idx_splitters_olt ON splitters(olt_id);
CREATE INDEX IF NOT EXISTS idx_installations_status ON installations(status);
CREATE INDEX IF NOT EXISTS idx_inventory_category ON inventory_items(category);
