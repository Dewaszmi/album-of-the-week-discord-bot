import os

from aiohttp import web

from album_service import album_data_to_entry

WEB_STATIC_DIR = os.path.join(os.path.dirname(__file__), "web", "static")
VALID_QUEUES = {"main", "bonus"}


def _check_auth(request: web.Request, admin_token: str) -> bool:
    if not admin_token:
        return False
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:] == admin_token
    return request.query.get("token") == admin_token


@web.middleware
async def auth_middleware(request, handler):
    admin_token = request.app["admin_token"]
    if request.path in ("/", "/index.html") or request.path.startswith("/static/"):
        return await handler(request)
    if not _check_auth(request, admin_token):
        return web.json_response({"error": "Unauthorized"}, status=401)
    return await handler(request)


def create_web_app(bot, admin_token: str) -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    app["admin_token"] = admin_token
    app["bot"] = bot
    store = bot.store

    async def index(request):
        return web.FileResponse(os.path.join(WEB_STATIC_DIR, "index.html"))

    async def get_queues(request):
        store.reload()
        return web.json_response(
            {"main": store.main, "bonus": store.bonus, "backlog": store.backlog}
        )

    async def reorder_queue(request):
        queue_name = request.match_info["queue"]
        if queue_name not in VALID_QUEUES:
            return web.json_response({"error": "Unknown queue"}, status=400)
        try:
            body = await request.json()
            order = body["order"]
            if not isinstance(order, list):
                raise ValueError("order must be a list")
            store.reload()
            store.reorder(queue_name, order)
        except (KeyError, ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        except IndexError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def remove_album(request):
        queue_name = request.match_info["queue"]
        if queue_name not in VALID_QUEUES:
            return web.json_response({"error": "Unknown queue"}, status=400)
        try:
            index = int(request.match_info["index"])
            store.reload()
            removed = store.remove_at(queue_name, index)
        except (ValueError, IndexError) as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True, "removed": removed})

    async def add_backlog(request):
        try:
            body = await request.json()
            text = body.get("text", "")
            added_by = body.get("added_by", "")
            if not text.strip():
                return web.json_response({"error": "text is required"}, status=400)
            store.reload()
            note = store.add_backlog_note(text, added_by)
        except (KeyError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True, "note": note})

    async def update_backlog(request):
        try:
            index = int(request.match_info["index"])
            body = await request.json()
            text = body.get("text", "")
            if not text.strip():
                return web.json_response({"error": "text is required"}, status=400)
            store.reload()
            note = store.update_backlog_note(index, text)
        except (ValueError, IndexError) as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True, "note": note})

    async def remove_backlog(request):
        try:
            index = int(request.match_info["index"])
            store.reload()
            removed = store.remove_backlog_note(index)
        except (ValueError, IndexError) as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True, "removed": removed})

    async def search_albums(request):
        query = request.query.get("q", "").strip()
        if not query:
            return web.json_response({"error": "q is required"}, status=400)
        try:
            limit = min(int(request.query.get("limit", "8")), 15)
        except ValueError:
            limit = 8
        results = await bot.search_albums(query, limit=limit)
        return web.json_response({"results": results})

    async def add_album(request):
        queue_name = request.match_info["queue"]
        if queue_name not in VALID_QUEUES:
            return web.json_response({"error": "Unknown queue"}, status=400)
        try:
            body = await request.json()
            artist = body.get("artist", "").strip()
            title = body.get("title", "").strip()
            user_name = body.get("user_name", "").strip()
            if not artist or not title:
                return web.json_response(
                    {"error": "artist and title are required"}, status=400
                )
            album_data = await bot.fetch_album_info(artist, title)
            if not album_data:
                return web.json_response({"error": "Album not found"}, status=404)
            entry = album_data_to_entry(album_data, user_name=user_name)
            store.reload()
            store.append_album(queue_name, entry)
        except (KeyError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True, "entry": entry})

    app.router.add_get("/", index)
    app.router.add_get("/api/queues", get_queues)
    app.router.add_get("/api/albums/search", search_albums)
    app.router.add_post("/api/queues/{queue}/add", add_album)
    app.router.add_put("/api/queues/{queue}/reorder", reorder_queue)
    app.router.add_delete("/api/queues/{queue}/{index}", remove_album)
    app.router.add_post("/api/backlog", add_backlog)
    app.router.add_put("/api/backlog/{index}", update_backlog)
    app.router.add_delete("/api/backlog/{index}", remove_backlog)
    app.router.add_static("/static/", WEB_STATIC_DIR, show_index=False)

    return app


async def start_web_server(bot, host: str, port: int, admin_token: str):
    if not admin_token:
        print("⚠️  ADMIN_TOKEN not set — web UI disabled.")
        return

    app = create_web_app(bot, admin_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"Web UI running at http://{host}:{port} (SSH tunnel to access remotely)")
