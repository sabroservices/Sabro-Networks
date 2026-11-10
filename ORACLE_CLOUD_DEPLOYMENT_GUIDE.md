# Sabro Networks • Oracle Cloud Free Tier & Free Domain Deployment Guide

This guide provides step-by-step instructions to deploy **Sabro Networks Powered By Connect (FTTH)** on **Oracle Cloud Always Free Tier** with a free domain and automated Let's Encrypt SSL certificate.

---

## Architecture Overview

```
[ Internet / WhatsApp Users ]
             │
             ▼
   [ Cloudflare / DuckDNS ] (Free Domain: your-isp.duckdns.org)
             │  Port 80/443 (SSL/HTTPS)
             ▼
  [ Nginx Reverse Proxy ]
             │  Unix Socket / localhost:5000
             ▼
   [ Gunicorn WSGI Server ]
             │
   [ Sabro Networks (Flask) ]
             │
    [ SQLite3 Database ] (With Nightly Automated Backup Cron)
```

---

## Step 1: Create Your Always Free Oracle Cloud VM

1. Register or log into [Oracle Cloud Infrastructure (OCI)](https://cloud.oracle.com/).
2. Navigate to **Compute** > **Instances** > **Create Instance**.
3. Choose:
   - **Image**: Ubuntu 22.04 LTS or 24.04 LTS (Minimal or Standard).
   - **Shape**:
     - *Option A (AMD)*: `VM.Standard.E2.1.Micro` (1 OCPU, 1 GB RAM) - Always Free.
     - *Option B (Ampere ARM)*: `VM.Standard.A1.Flex` (Up to 4 OCPUs, 24 GB RAM) - Always Free.
   - **Networking**: Assign a public IPv4 address.
   - **SSH Keys**: Download your private key (`ssh-key.key`).
4. Click **Create** and copy your **Public IP Address** (e.g. `129.151.xx.xx`).

---

## Step 2: Open Ports 80 & 443 in Oracle Cloud Security Lists

1. On the instance details page, click on your **Subnet** > **Default Security List**.
2. Click **Add Ingress Rules**:
   - **Source CIDR**: `0.0.0.0/0`
   - **IP Protocol**: `TCP`
   - **Destination Port Range**: `80, 443`
   - **Description**: `Allow HTTP and HTTPS traffic`
3. Click **Add Ingress Rules**.

---

## Step 3: Connect via SSH and Open Linux Firewall

From your computer terminal or PowerShell:
```bash
ssh -i /path/to/ssh-key.key ubuntu@YOUR_ORACLE_PUBLIC_IP
```

Open OS-level firewall ports:
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

---

## Step 4: Install Dependencies & Clone Project

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install Python, Nginx, Git, Certbot
sudo apt install -y python3-pip python3-venv nginx git certbot python3-certbot-nginx

# Create directory and clone/upload your app
sudo mkdir -p /var/www/sabro-networks
sudo chown -R ubuntu:ubuntu /var/www/sabro-networks
cd /var/www/sabro-networks

# If using Git: git clone <your-repo-url> .
# Or upload using SCP: scp -r -i key.key ./* ubuntu@IP:/var/www/sabro-networks/
```

Set up virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

Generate production `.env`:
```bash
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env
```

---

## Step 5: Configure Systemd Background Service

Create `/etc/systemd/system/sabro-networks.service`:
```ini
[Unit]
Description=Sabro Networks FTTH Billing Application
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/var/www/sabro-networks
Environment="PATH=/var/www/sabro-networks/venv/bin"
EnvironmentFile=/var/www/sabro-networks/.env
ExecStart=/var/www/sabro-networks/venv/bin/gunicorn --workers 3 --bind unix:sabro_networks.sock wsgi:app

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl start sabro-networks
sudo systemctl enable sabro-networks
sudo systemctl status sabro-networks
```

---

## Step 6: Connect a 100% Free Domain (DuckDNS)

1. Go to [DuckDNS.org](https://www.duckdns.org/) and log in with Google / GitHub.
2. Under **Domains**, create a free subdomain, e.g. `sabronetworks.duckdns.org`.
3. Set the target IP address to your **Oracle Cloud Public IP** and click **Update IP**.

*(Alternative: You can use Cloudflare with any domain name you own for free DDoS protection and DNS management).*

---

## Step 7: Configure Nginx Reverse Proxy with SSL

Create `/etc/nginx/sites-available/sabro-networks`:
```nginx
server {
    listen 80;
    server_name sabronetworks.duckdns.org; # Replace with your domain

    client_max_body_size 50M;

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/sabro-networks/sabro_networks.sock;
    }

    location /static {
        alias /var/www/sabro-networks/static;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }
}
```

Enable the Nginx site:
```bash
sudo ln -s /etc/nginx/sites-available/sabro-networks /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

Obtain a free SSL certificate via Let's Encrypt:
```bash
sudo certbot --nginx -d sabronetworks.duckdns.org
```
Certbot will automatically install the SSL certificate and configure HTTPS redirection!

---

## Step 8: Automated Nightly Database Backup Cron Job

Create a backup script at `/var/www/sabro-networks/scripts/backup_db.sh`:
```bash
mkdir -p /var/www/sabro-networks/backups
cat << 'EOF' > /var/www/sabro-networks/backup_cron.sh
#!/bin/bash
BACKUP_DIR="/var/www/sabro-networks/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
sqlite3 /var/www/sabro-networks/sabro_networks.db ".backup '${BACKUP_DIR}/sabro_backup_${TIMESTAMP}.db'"
gzip "${BACKUP_DIR}/sabro_backup_${TIMESTAMP}.db"
# Keep only last 14 days of backups
find "${BACKUP_DIR}" -name "sabro_backup_*.db.gz" -mtime +14 -delete
EOF

chmod +x /var/www/sabro-networks/backup_cron.sh
```

Add to cron (`crontab -e`):
```cron
# Run daily at 3:00 AM
0 3 * * * /var/www/sabro-networks/backup_cron.sh > /dev/null 2>&1
```

---

## Step 9: Verification Checklist

- [x] Portal accessible securely over `https://sabronetworks.duckdns.org`.
- [x] WhatsApp digital bill slips accessible on mobile phones.
- [x] Admin dashboard displays active optical complaints queue front-and-center.
- [x] Staff passwords masked as `••••••••` in staff directory.
- [x] Recovery Boys restricted strictly to their assigned sector area.
- [x] Daily automated backup running at 3:00 AM.
