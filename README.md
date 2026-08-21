# Discord bot to implement Album of the Week events into a server

This is a small side project to create a Discord bot for automatic Album of the Week events in a Discord server I'm a member of. It's designed for local hosting on a minimal home server.

## DISCLAIMER
THIS IS NOT A PUBLICLY AVAILABLE DISCORD BOT APPLICATION. It's designed to be hosted locally, and currently supports managing only one server at a time. If you want to use it at your own server, you should have a machine able to host the bot

## Installation
- Copy the repo on your device and insert the appropriate values into the .env file (see .env.example for reference)
- Then, run the code with `python run_bot.py` (when running on a 24/7 server, it's recommended to setup a daemon to autorun / restart the app)

## Web UI
Start the bot with `python run_bot.py --web`. Set `ADMIN_TOKEN` in `.env`. The bot serves a queue manager at `http://127.0.0.1:8080` (override with `WEB_UI_HOST` / `WEB_UI_PORT`). Log in with that token to add, reorder, and remove albums.
