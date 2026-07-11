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

The UI binds to `127.0.0.1` by default and is **not** exposed to the internet. Access it remotely via SSH tunnel.

### Remote access via SSH

On the machine where the bot runs, ensure `WEB_UI_PORT` (default `8080`) is set in `.env`.

From a remote machine with SSH access to the server:

```bash
ssh -L 8080:localhost:8080 user@your-server
```

Keep that SSH session open, then open `http://localhost:8080` in a browser and enter the `ADMIN_TOKEN` from `.env`.

To use a different local port (e.g. if 8080 is taken):

```bash
ssh -L 9090:localhost:8080 user@your-server
```

Then open `http://localhost:9090`.