#!/usr/bin/env bash
# Starts the whole cluster and prints the address other devices should open.
# Usage: ./start.sh            (port 80)
#        HTTP_PORT=8080 ./start.sh
set -e
cd "$(dirname "$0")"

PORT="${HTTP_PORT:-80}"

detect_ip() {
  if command -v ipconfig >/dev/null 2>&1 && [ "$(uname)" = "Darwin" ]; then
    for ifc in en0 en1 en2 en3; do
      ip=$(ipconfig getifaddr "$ifc" 2>/dev/null || true)
      [ -n "$ip" ] && { echo "$ip"; return; }
    done
  fi
  if command -v hostname >/dev/null 2>&1; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -n "$ip" ] && { echo "$ip"; return; }
  fi
  if command -v ip >/dev/null 2>&1; then
    ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}'
  fi
}

IP="${PUBLIC_HOST:-$(detect_ip)}"
if [ -n "$IP" ] && [ "$PORT" != "80" ]; then IP="$IP:$PORT"; fi
export PUBLIC_HOST="$IP" HTTP_PORT="$PORT"

echo ""
if [ -n "$IP" ]; then
  echo "  On this computer:        http://localhost$( [ "$PORT" != "80" ] && echo ":$PORT")"
  echo "  On phones/laptops (same Wi-Fi): http://$IP"
  echo "  (the app's 'Add a device' button shows a QR code for this address)"
else
  echo "  Could not detect your Wi-Fi IP. Other devices can use http://<your-computer-ip>"
fi
echo ""

docker compose up --build "$@"
