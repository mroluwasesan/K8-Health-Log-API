#!/bin/bash

# Update package lists
echo "Updating system..."
sudo apt update && sudo apt upgrade -y

# Install Vim
echo "Installing Vim..."
sudo apt install vim -y

# Install Nginx
echo "Installing Nginx..."
sudo apt install nginx -y

# Remove default Nginx configuration
echo "Removing default Nginx configuration..."
sudo rm -f /etc/nginx/sites-available/default
sudo rm -f /etc/nginx/sites-enabled/default

# Create a new Nginx reverse proxy configuration
NGINX_CONFIG="/etc/nginx/sites-available/fastapi"

echo "Creating Nginx reverse proxy configuration..."

sudo bash -c "cat > $NGINX_CONFIG" <<EOL
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOL

# Enable the new configuration
echo "Enabling Nginx configuration..."
sudo ln -s $NGINX_CONFIG /etc/nginx/sites-enabled/

# Test and restart Nginx
echo "Restarting Nginx..."
sudo nginx -t && sudo systemctl restart nginx

# Install Python 3.9
echo "Installing Python 3.9..."
sudo apt install python3.9 python3.9-venv python3.9-dev -y

# Verify installation
echo "Checking installed versions..."
nginx -v
python3.9 --version

echo "Setup complete!"
