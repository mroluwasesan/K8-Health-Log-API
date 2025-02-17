#!/bin/bash

set -e  # Exit on error

APP_DIR="/home/rotimi/K8-Health-Log-API"
SERVICE_NAME="fastapi.service"

echo "Pulling latest changes..."
cd "$APP_DIR"
git pull origin main

echo "Activating virtual environment..."
source "$APP_DIR/venv/bin/activate"

echo "Installing dependencies..."
pip install --no-cache-dir -r requirements.txt

echo "Restarting service..."
sudo systemctl daemon-reload
sudo systemctl restart $SERVICE_NAME
sudo systemctl status $SERVICE_NAME --no-pager

echo "Deployment completed successfully!"
