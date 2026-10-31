#!/usr/bin/env bash
# =========================================================================
# MALKIA CARGO WAVE LIMITED - aaPanel Automated Setup Script
# Port: 3444 (Gunicorn Daemon)
# =========================================================================

set -e

# Detect project directory automatically (e.g. /www/wwwroot/malkia)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "====================================================="
echo "   Setting up Malkia Unified System on aaPanel       "
echo "   Directory: $APP_DIR"
echo "   Internal Port: 3444"
echo "====================================================="

cd "$APP_DIR"

# 1. Prepare .env if not exists
if [ ! -f ".env" ]; then
    echo "[1/5] Creating .env from template (.env.example)..."
    cp .env.example .env
    echo "(!) Kumbuka kubadilisha taarifa zako ndani ya .env baadaye ukihitaji."
else
    echo "[1/5] .env file tayari ipo."
fi

# 2. Virtual Environment
echo "[2/5] Creating Python virtual environment (.venv)..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# 3. Pip Install
echo "[3/5] Installing Python dependencies & Gunicorn..."
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# 4. Database Migrations, Initial Seed & Static Files
echo "[4/5] Running migrations, seeding initial stages & collecting static files..."
python manage.py migrate
python seed_data.py || true
python manage.py collectstatic --noinput

# 5. Systemd Service (Port 3444)
echo "[5/5] Registering Systemd Service (Port 3444)..."
SERVICE_FILE="/etc/systemd/system/malkia_portal.service"

sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Malkia Cargo Wave Portal (Gunicorn Daemon on Port 3444)
After=network.target

[Service]
User=root
Group=www-data
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/.venv/bin"
Environment="DJANGO_SETTINGS_MODULE=malkia_project.settings"
ExecStart=$APP_DIR/.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:3444 --timeout 120 --access-logfile /var/log/malkia_access.log --error-logfile /var/log/malkia_error.log malkia_project.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable malkia_portal
sudo systemctl restart malkia_portal

echo "====================================================="
echo "[SUCCESS] Mfumo wa Malkia unakimbia kwenye Port 3444!"
echo "Unaweza kuangalia status kwa: sudo systemctl status malkia_portal"
echo "Akaunti ya kuingilia:"
echo "   Username: admin  |  Password: admin123"
echo "   Username: ceo    |  Password: ceo123"
echo "====================================================="
