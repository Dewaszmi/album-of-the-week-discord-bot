import os

from aiohttp import web

from album_service import album_data_to_entry

STATIC = os.path.join(os.path.dirname(__file__), "web", "static")


def create_web_app(bot, token: str) -> web.Application:
    app = web.Application()
    store = bot.store

    def authorized(request):
        return request.headers.get("Authorization") == f"Bearer {token}"

    async def index(_):
        return web.FileResponse(os.path.join(STATIC, "index.html"))

    async def get_queues(request):
        if not authorized(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        return web.json_response({"main": store.main, "bonus": store.bonus})

    async def search(request):
        if not authorized(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        q = request.query.get("q", "").strip()
        if not q:
            return web.json_response({"error": "q is required"}, status=400)
        return web.json_response({"results": await bot.search_albums(q)})

    async def add_album(request):
        if not authorized(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        try:
            queue = store.get(request.match_info["queue"])
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        body = await request.json()
        artist, title = body.get("artist", "").strip(), body.get("title", "").strip()
        if not artist or not title:
            return web.json_response({"error": "artist and title are required"}, status=400)
        album = await bot.fetch_album_info(artist, title)
        if not album:
            return web.json_response({"error": "Album not found"}, status=404)
        entry = album_data_to_entry(album, user_name=body.get("user_name", ""))
        queue.append(entry)
        store.save()
        return web.json_response({"ok": True, "entry": entry})

    async def move_album(request):
        if not authorized(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        try:
            queue = store.get(request.match_info["queue"])
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        body = await request.json()
        i, dest = int(body["index"]), int(body["index"]) + int(body["dir"])
        if not (0 <= i < len(queue) and 0 <= dest < len(queue)):
            return web.json_response({"error": "bad index"}, status=400)
        queue[i], queue[dest] = queue[dest], queue[i]
        store.save()
        return web.json_response({"ok": True})

    async def remove_album(request):
        if not authorized(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        try:
            queue = store.get(request.match_info["queue"])
            queue.pop(int(request.match_info["index"]))
        except (ValueError, IndexError) as e:
            return web.json_response({"error": str(e)}, status=400)
        store.save()
        return web.json_response({"ok": True})

    app.router.add_get("/", index)
    app.router.add_get("/api/queues", get_queues)
    app.router.add_get("/api/search", search)
    app.router.add_post("/api/queues/{queue}/add", add_album)
    app.router.add_post("/api/queues/{queue}/move", move_album)
    app.router.add_delete("/api/queues/{queue}/{index}", remove_album)
    app.router.add_static("/static/", STATIC)
    return app


async def start_web_server(bot, host: str, port: int, token: str):
    if not token:
        print("ADMIN_TOKEN not set — web UI disabled.")
        return
    runner = web.AppRunner(create_web_app(bot, token))
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    print(f"Web UI at http://{host}:{port}")
