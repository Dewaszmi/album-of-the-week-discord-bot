# Discord bot to implement Album of the Week events into a server

This is a small side project to create a Discord bot for automatic Album of the Week events in a Discord server I'm a member of. It's designed for local hosting on a minimal home server.

## DISCLAIMER
THIS IS NOT A PUBLICLY AVAILABLE DISCORD BOT APPLICATION. It's designed to be hosted locally, and currently supports managing only one server at a time. If you want to use it at your own server, you should have a machine able to host the bot

## Installation
- Copy the repo on your device and insert the appropriate values into the .env file (see .env.example for reference)
- Then, run the code by run_bot.py (when running on a 24/7 server, it's recommended to setup a daemon to autorun / restart the app)

## Web UI (queue management)

The bot includes a local web UI for managing album queues and a backlog of future ideas. It starts automatically when `ADMIN_TOKEN` is set in `.env`.

Features:
- Search Last.fm and add albums to the normal or bonus queue
- View, reorder (drag-and-drop), and remove albums from the normal and bonus queues
- Add, edit, and delete backlog notes for future album ideas

The UI binds to `127.0.0.1` by default and is **not** exposed to the internet. The `ADMIN_TOKEN` protects the UI itself — anyone who reaches it still needs that secret.

### Giving a colleague access (without full server access)

Use a **tunnel-only SSH account** — your colleague can forward the web UI port but cannot open a shell or access files on your Pi.

Quick setup on the Pi:

```bash
cd /path/to/discord-album-of-the-week-bot
chmod +x scripts/setup-tunnel-user.sh
sudo WEB_PORT=8080 ./scripts/setup-tunnel-user.sh
```

Then add your colleague's public key to `/home/aotw-tunnel/.ssh/authorized_keys` with the `permitopen` prefix (the script prints the exact format).

Your colleague runs:

```bash
ssh -N -L 8080:localhost:8080 aotw-tunnel@your-pi-hostname
```

They open `http://localhost:8080` and enter the `ADMIN_TOKEN`. Share the token separately (not in the same message as the SSH hostname).

#### Manual setup (same result as the script)

Create a dedicated Linux user that can **only** forward the web UI port — no shell, no file access, no other commands.

On your server (as root or with sudo):

```bash
# 1. Create a user with no login shell
sudo useradd -m -s /usr/sbin/nologin aotw-tunnel

# 2. (Recommended) Use an SSH key — no password login
sudo mkdir -p /home/aotw-tunnel/.ssh
sudo nano /home/aotw-tunnel/.ssh/authorized_keys
# Paste your colleague's public key, prefixed with:
# command="/usr/sbin/nologin",no-agent-forwarding,no-X11-forwarding,no-pty,permitopen="localhost:8080"
# Example:
# command="/usr/sbin/nologin",no-agent-forwarding,no-X11-forwarding,no-pty,permitopen="localhost:8080" ssh-ed25519 AAAA... colleague@laptop

sudo chown -R aotw-tunnel:aotw-tunnel /home/aotw-tunnel/.ssh
sudo chmod 700 /home/aotw-tunnel/.ssh
sudo chmod 600 /home/aotw-tunnel/.ssh/authorized_keys

# 3. Restrict the user in sshd (e.g. /etc/ssh/sshd_config.d/aotw-tunnel.conf)
```

```
Match User aotw-tunnel
    ForceCommand /usr/sbin/nologin
    AllowTcpForwarding local
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
```

```bash
# 4. Validate and reload
sudo sshd -t && sudo systemctl reload sshd
```

What they **cannot** do: open a shell, read files, run commands, or forward other ports (with `permitopen` set).

What you should still do:
- Use a strong, unique `ADMIN_TOKEN` (share it separately from the SSH key)
- Rotate the token if they no longer need access
- Remove their key from `authorized_keys` when access should end

#### Option B: Cloudflare Tunnel (browser only, no SSH)

Expose **only** the web UI over HTTPS via your existing Cloudflare setup. Your colleague opens a URL in a browser — no SSH, no server access.

**Prerequisites on the Pi**

1. Bot running with these in `.env`:
   ```env
   ADMIN_TOKEN=<long random secret>
   WEB_UI_HOST=127.0.0.1
   WEB_UI_PORT=8080
   ```
2. Verify the UI works locally: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/` should return `200`.
3. `cloudflared` already running (you likely have this for your website).

**Step 1 — Add a hostname to your existing tunnel**

Pick a subdomain, e.g. `aotw.yourdomain.com` (must be a domain already on Cloudflare).

**If you manage the tunnel in the Cloudflare dashboard** (Zero Trust → Networks → Tunnels):

1. Open your existing tunnel → **Public Hostname** → **Add a public hostname**
2. Subdomain: `aotw` (or whatever you prefer)
3. Domain: your domain
4. Service type: **HTTP**
5. URL: `127.0.0.1:8080` (or `localhost:8080`)
6. Save

Cloudflare creates the DNS record automatically.

**If you use a local `config.yml`** (common on Raspberry Pi):

Find your config (often `/etc/cloudflared/config.yml` or `~/.cloudflared/config.yml`) and add a new ingress rule **above** the catch-all `http_status:404` line:

```yaml
ingress:
  - hostname: yourdomain.com          # your existing website
    service: http://localhost:80      # whatever you already have
  - hostname: aotw.yourdomain.com     # new — AOTW web UI
    service: http://127.0.0.1:8080
  - service: http_status:404           # must stay last
```

Then restart cloudflared:

```bash
sudo systemctl restart cloudflared
```

If the DNS record is not auto-created, add a CNAME in the Cloudflare DNS dashboard:

| Type | Name | Target |
|---|---|---|
| CNAME | `aotw` | `<your-tunnel-id>.cfargotunnel.com` |

(The exact target is shown on the tunnel page in Zero Trust.)

**Step 2 — Add Cloudflare Access (who can open the URL)**

This is the gate that keeps random internet users out — separate from `ADMIN_TOKEN`.

1. [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com/) → **Access** → **Applications**
2. **Add an application** → **Self-hosted**
3. Application name: `AOTW Queue Manager`
4. Session duration: e.g. 24 hours
5. **Add public hostname**: `aotw.yourdomain.com`
6. **Add a policy** — e.g.:
   - Policy name: `AOTW editors`
   - Action: **Allow**
   - Include: **Emails** → your email + your colleague's email  
     (or **One-time PIN** if you don't want to pre-list emails)
7. Save

**Step 3 — Share access with your colleague**

Send them:

1. The URL: `https://aotw.yourdomain.com`
2. The `ADMIN_TOKEN` from your `.env` (via a separate channel — Signal, in person, etc.)

When they visit the URL:

1. Cloudflare Access asks them to verify (email PIN or login, depending on your policy)
2. The AOTW login screen asks for the `ADMIN_TOKEN`

**Step 4 — Quick test**

```bash
# On the Pi — bot UI reachable locally
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/

# From any browser (or your phone off Wi-Fi)
# Open https://aotw.yourdomain.com → Access login → ADMIN_TOKEN login
```

**Security notes**

- Keep `WEB_UI_HOST=127.0.0.1` — only `cloudflared` talks to the UI locally; no router port forwarding needed.
- Do **not** skip Cloudflare Access — `ADMIN_TOKEN` alone on a public URL is weaker (it's a single shared secret in the browser).
- If your colleague leaves, remove their email from the Access policy and rotate `ADMIN_TOKEN`.
- This tunnel route exposes **only** the queue UI, not your other website or shell.

**Troubleshooting**

| Problem | Check |
|---|---|
| 502 / error from Cloudflare | Bot running? `WEB_UI_PORT` matches tunnel URL? |
| Access loop / blocked | Policy includes colleague's email? Correct hostname on the Access app? |
| Tunnel not updating | `sudo systemctl status cloudflared` — config syntax? ingress order? |
| Port clash on Pi | Change `WEB_UI_PORT` in `.env` and update the tunnel URL to match |



### Local access (you, on the server)

If you are already on the machine, open `http://127.0.0.1:8080` directly.

### SSH tunnel (your own admin account)

If you use your own SSH account (with shell access), you can tunnel the same way:

```bash
ssh -N -L 8080:localhost:8080 you@your-server
```

Then open `http://localhost:8080` and enter the `ADMIN_TOKEN`.

To use a different local port (e.g. if 8080 is taken):

```bash
ssh -N -L 9090:localhost:8080 you@your-server
```

Then open `http://localhost:9090`.