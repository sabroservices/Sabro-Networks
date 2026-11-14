#!/usr/bin/env bash
# ==============================================================================
# Sabro Networks Powered By Connect (FTTH)
# Oracle Cloud Free Tier (Ubuntu) Automated Deployment Script
# ==============================================================================

set -e

APP_DIR="/var/www/sabro_networks"
SERVICE_NAME="sabro-networks"
DOMAIN_OR_IP="${1:-sabronetworks.duckdns.org}"

echo "=================================================================="
echo "  Deploying Sabro Networks on Oracle Cloud Free Tier"
echo "  Target Domain / IP: ${DOMAIN_OR_IP}"
echo "=================================================================="

# 1. Update OS and install prerequisites
echo "[1/6] Updating system and installing dependencies..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git curl ufw

# 2. Setup Application Directory
echo "[2/6] Setting up application folder at ${APP_DIR}..."
sudo mkdir -p ${APP_DIR}
sudo chown -R $USER:$USER ${APP_DIR}

# Copy files if script is run inside the repo folder
if [ -f "app.py" ]; then
    cp -r * ${APP_DIR}/
fi

cd ${APP_DIR}

# 3. Create Python Virtual Environment
echo "[3/6] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create Systemd Service for 24/7 Uptime & Auto-Restart
echo "[4/6] Creating Systemd background service..."
sudo bash -c "cat > /etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Sabro Networks FTTH Billing Application (Gunicorn)
After=network.target

[Service]
User=$USER
Group=www-data
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin"
Environment="PORT=5000"
Environment="SECRET_KEY=$(openssl rand -hex 24)"
ExecStart=${APP_DIR}/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}

# 5. Configure Nginx Reverse Proxy
echo "[5/6] Setting up Nginx Reverse Proxy..."
sudo bash -c "cat > /etc/nginx/sites-available/${SERVICE_NAME}" <<EOF
server {
    listen 80;
    server_name ${DOMAIN_OR_IP};

    client_max_body_size 50M;

    location /static/ {
        alias ${APP_DIR}/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# 6. Configure Firewall
echo "[6/6] Configuring Ubuntu UFW firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "=================================================================="
echo "  SUCCESS! Sabro Networks is now running on Oracle Cloud!"
echo "  Access it at: http://${DOMAIN_OR_IP}"
echo ""
echo "  To enable free HTTPS SSL certificate with Let's Encrypt, run:"
echo "    sudo certbot --nginx -d ${DOMAIN_OR_IP}"
echo "=================================================================="
