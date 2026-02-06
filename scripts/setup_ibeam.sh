#!/bin/bash
#
# IBeAM Setup Script for STOXX50 Trade Filter
# Sets up IB Gateway in Docker for headless IBKR API access
#
# Usage: ./scripts/setup_ibeam.sh [paper|live]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IBEAM_DIR="$HOME/ibeam"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "=============================================="
echo "  IBeAM Setup for STOXX50 Trade Filter"
echo "=============================================="
echo -e "${NC}"

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker not found!${NC}"
    echo ""
    echo "Install Docker first:"
    echo "  curl -fsSL https://get.docker.com | sh"
    echo "  sudo usermod -aG docker \$USER"
    echo "  # Then log out and back in"
    exit 1
fi

# Check Docker is running
if ! docker info &> /dev/null; then
    echo -e "${RED}Docker is not running or you don't have permission.${NC}"
    echo ""
    echo "Try: sudo systemctl start docker"
    echo "Or:  sudo usermod -aG docker \$USER  (then log out/in)"
    exit 1
fi

echo -e "${GREEN}Docker found and running.${NC}"
echo ""

# Get trading mode
MODE="${1:-}"
if [ -z "$MODE" ]; then
    echo "Select trading mode:"
    echo "  1) Paper trading (recommended for testing)"
    echo "  2) Live trading"
    echo ""
    read -p "Enter choice [1/2]: " choice
    case $choice in
        1) MODE="paper" ;;
        2) MODE="live" ;;
        *) echo "Invalid choice"; exit 1 ;;
    esac
fi

if [ "$MODE" = "paper" ]; then
    PORT=4002
    GATEWAY_TYPE="paper"
    echo -e "${YELLOW}Setting up PAPER trading${NC}"
elif [ "$MODE" = "live" ]; then
    PORT=4001
    GATEWAY_TYPE="live"
    echo -e "${RED}Setting up LIVE trading - real money!${NC}"
else
    echo "Invalid mode. Use: paper or live"
    exit 1
fi

echo ""

# Create config directory
echo "Creating config directory: $IBEAM_DIR"
mkdir -p "$IBEAM_DIR"

# Get credentials
echo ""
echo -e "${CYAN}Enter your IBKR credentials:${NC}"
echo "(These are stored locally in $IBEAM_DIR/conf.yaml)"
echo ""

read -p "IBKR Username: " IBKR_USER
read -s -p "IBKR Password: " IBKR_PASS
echo ""

# Create conf.yaml
cat > "$IBEAM_DIR/conf.yaml" << EOF
ibeam:
  account: $IBKR_USER
  password: $IBKR_PASS
EOF
chmod 600 "$IBEAM_DIR/conf.yaml"

echo -e "${GREEN}Credentials saved.${NC}"
echo ""

# Stop existing container if running
if docker ps -a --format '{{.Names}}' | grep -q '^ibeam$'; then
    echo "Stopping existing ibeam container..."
    docker stop ibeam 2>/dev/null || true
    docker rm ibeam 2>/dev/null || true
fi

# Pull latest image
echo "Pulling IBeAM Docker image..."
docker pull voyz/ibeam

# Run container
echo ""
echo "Starting IBeAM container..."
docker run -d \
    --name ibeam \
    --restart unless-stopped \
    -p $PORT:$PORT \
    -v "$IBEAM_DIR:/srv/conf" \
    -e IBEAM_GATEWAY_TYPE=$GATEWAY_TYPE \
    voyz/ibeam

echo ""
echo -e "${GREEN}IBeAM container started!${NC}"
echo ""

# Wait for startup
echo "Waiting for IB Gateway to start (this takes ~30 seconds)..."
echo -e "${YELLOW}Check your phone for 2FA notification!${NC}"
echo ""

sleep 5
echo "Container logs:"
echo "----------------------------------------"
timeout 60 docker logs -f ibeam 2>&1 | while read line; do
    echo "$line"
    if echo "$line" | grep -q "Gateway running"; then
        echo "----------------------------------------"
        echo -e "${GREEN}IB Gateway is running!${NC}"
        break
    fi
    if echo "$line" | grep -q "error\|Error\|ERROR"; then
        echo "----------------------------------------"
        echo -e "${RED}Error detected - check credentials${NC}"
    fi
done &
LOGS_PID=$!

# Give user time to do 2FA
sleep 30
kill $LOGS_PID 2>/dev/null || true

echo ""
echo ""

# Update config.yaml
CONFIG_FILE="$PROJECT_DIR/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    echo "Updating config.yaml..."

    # Use Python to update YAML properly
    "$PROJECT_DIR/venv/bin/python" << EOF
import yaml

with open('$CONFIG_FILE', 'r') as f:
    config = yaml.safe_load(f)

if 'ibkr' not in config:
    config['ibkr'] = {}

config['ibkr']['enabled'] = True
config['ibkr']['host'] = '127.0.0.1'
config['ibkr']['port'] = $PORT
config['ibkr']['client_id'] = 1
config['ibkr']['timeout'] = 10

with open('$CONFIG_FILE', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print("Updated config.yaml with IBKR settings")
EOF
else
    echo -e "${YELLOW}config.yaml not found. Create it from config.yaml.example${NC}"
fi

# Install ib_insync
echo ""
echo "Installing ib_insync..."
"$PROJECT_DIR/venv/bin/pip" install -q ib_insync

# Test connection
echo ""
echo "Testing connection..."
"$PROJECT_DIR/venv/bin/python" << EOF
from ibkr_provider import IBKRProvider

p = IBKRProvider(port=$PORT, timeout=15)
if p.connect():
    price = p.get_index_price()
    if price:
        print(f"\033[92mSuccess! Euro Stoxx 50 price: {price:.2f}\033[0m")
    else:
        print("\033[93mConnected but no price data (market may be closed)\033[0m")
    p.disconnect()
else:
    print("\033[91mConnection failed - approve 2FA and try again\033[0m")
    print("Check logs: docker logs ibeam")
EOF

echo ""
echo "=============================================="
echo -e "${GREEN}Setup complete!${NC}"
echo "=============================================="
echo ""
echo "Useful commands:"
echo "  docker logs -f ibeam     # View logs"
echo "  docker restart ibeam     # Restart gateway"
echo "  docker stop ibeam        # Stop gateway"
echo ""
echo "Test with:"
echo "  ./venv/bin/python trade_filter.py -a -p"
echo ""
echo "IBeAM will auto-restart on reboot."
echo "You may need to approve 2FA again after restarts."
echo ""
