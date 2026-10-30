#!/usr/bin/env bash
# ========================================================
# MALKIA CARGO WAVE — AUTOMATED VPS SETUP SCRIPT
# Configures Gunicorn on Port 3444 & Nginx for both domains
# ========================================================

set -e

echo "====================================================="
echo "   Setting up Malkia Cargo Wave Limited on VPS       "
echo "====================================================="

APP_DIR="/var/www/malkia"

# 1. Update & Install dependencies
echo "[1/6] Installing system packages..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# 2. Virtual Environment
echo "[2/6] Configuring Python virtualenv in $APP_DIR..."
cd "$APP_DIR"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# 3. Pip Install
echo "[3/6] Installing python packages & gunicorn..."
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# 4. Database Migrations & Static Files
echo "[4/6] Running database migrations & collecting static files..."
python manage.py migrate
python manage.py collectstatic --noinput

# 5. Setup Systemd Service on PORT 3444
echo "[5/6] Registering Systemd Service (Port 3444)..."
sudo cp "$APP_DIR/deploy/malkia_portal.service" /etc/systemd/system/malkia_portal.service
sudo systemctl daemon-reload
sudo systemctl enable malkia_portal
sudo systemctl restart malkia_portal

# 6. Setup Nginx Configuration
echo "[6/6] Configuring Nginx Virtual Hosts..."
sudo cp "$APP_DIR/deploy/nginx_malkia.conf" /etc/nginx/sites-available/malkia.conf
if [ ! -f /etc/nginx/sites-enabled/malkia.conf ]; then
    sudo ln -s /etc/nginx/sites-available/malkia.conf /etc/nginx/sites-enabled/
fi

sudo nginx -t
sudo systemctl restart nginx

echo "====================================================="
echo "✅ Malkia Portal successfully running on Port 3444!"
echo "   - Portal:  http://portal.malkiacargowave.com"
echo "   - Website: http://malkiacargowave.com"
echo ""
echo "👉 To activate FREE SSL (HTTPS), run:"
echo "   sudo certbot --nginx -d portal.malkiacargowave.com -d malkiacargowave.com -d www.malkiacargowave.com"
echo "====================================================="

