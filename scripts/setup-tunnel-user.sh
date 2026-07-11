#!/usr/bin/env bash
# Create a restricted SSH user that can only forward the AOTW web UI port.
# Run on the server (e.g. Raspberry Pi) with: sudo ./scripts/setup-tunnel-user.sh
#
# This does NOT modify sshd_config automatically — you add the Match block yourself
# and reload sshd, so a mistake won't lock you out of your main account.

set -euo pipefail

TUNNEL_USER="${TUNNEL_USER:-aotw-tunnel}"
WEB_PORT="${WEB_PORT:-8080}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0"
  exit 1
fi

if id "${TUNNEL_USER}" &>/dev/null; then
  echo "User ${TUNNEL_USER} already exists — skipping useradd."
else
  useradd -m -s /usr/sbin/nologin "${TUNNEL_USER}"
  echo "Created user: ${TUNNEL_USER} (shell: /usr/sbin/nologin)"
fi

SSH_DIR="/home/${TUNNEL_USER}/.ssh"
mkdir -p "${SSH_DIR}"
touch "${SSH_DIR}/authorized_keys"
chown -R "${TUNNEL_USER}:${TUNNEL_USER}" "${SSH_DIR}"
chmod 700 "${SSH_DIR}"
chmod 600 "${SSH_DIR}/authorized_keys"

SSHD_SNIPPET="/etc/ssh/sshd_config.d/aotw-tunnel.conf"
cat > "${SSHD_SNIPPET}" <<EOF
# AOTW web UI — tunnel-only SSH access (no shell)
Match User ${TUNNEL_USER}
    ForceCommand /usr/sbin/nologin
    AllowTcpForwarding local
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
EOF
chmod 644 "${SSHD_SNIPPET}"

if sshd -t 2>/dev/null; then
  systemctl reload sshd 2>/dev/null || systemctl reload ssh 2>/dev/null || true
  echo "Reloaded sshd (${SSHD_SNIPPET} installed)."
else
  echo "WARNING: sshd -t failed. Check ${SSHD_SNIPPET} before reloading sshd."
fi

echo ""
echo "=== Next steps ==="
echo ""
echo "1. Add your colleague's SSH public key to:"
echo "   ${SSH_DIR}/authorized_keys"
echo ""
echo "   Prefix each key line with (single line, no line breaks):"
echo "   command=\"/usr/sbin/nologin\",no-agent-forwarding,no-X11-forwarding,no-pty,permitopen=\"localhost:${WEB_PORT}\""
echo ""
echo "   Example:"
echo "   command=\"/usr/sbin/nologin\",no-agent-forwarding,no-X11-forwarding,no-pty,permitopen=\"localhost:${WEB_PORT}\" ssh-ed25519 AAAA... colleague@laptop"
echo ""
echo "2. Ensure the bot .env has:"
echo "   ADMIN_TOKEN=<long random secret>"
echo "   WEB_UI_HOST=127.0.0.1"
echo "   WEB_UI_PORT=${WEB_PORT}"
echo ""
echo "3. Share separately with your colleague:"
echo "   - SSH command (they run this, keep the window open):"
echo "     ssh -N -L 8080:localhost:${WEB_PORT} ${TUNNEL_USER}@<your-server-hostname>"
echo "   - URL after tunnel: http://localhost:8080"
echo "   - ADMIN_TOKEN from .env"
echo ""
echo "4. Test from another machine before sharing access."
echo ""
