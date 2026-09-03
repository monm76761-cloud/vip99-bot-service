import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from aiohttp import web

BASE_DIR = Path(__file__).resolve().parent
BOT_SCRIPT = Path(os.environ.get("BOT_SCRIPT", BASE_DIR / "bot.py"))
LOG_PATH = Path(os.environ.get("BOT_LOG_PATH", BASE_DIR / "bot.log"))
CONTROL_API_TOKEN = os.environ.get("CONTROL_API_TOKEN", "").strip()
BOT_PROCESS = None
PROCESS_LOCK = asyncio.Lock()
STARTED_AT = None


def authorized(request):
    if not CONTROL_API_TOKEN:
        return False
    token = request.headers.get("Authorization", "")
    return token == f"Bearer {CONTROL_API_TOKEN}"


def json_response(payload, status=200):
    return web.json_response(payload, status=status)


def process_status():
    running = BOT_PROCESS is not None and BOT_PROCESS.returncode is None
    return {
        "service": "vip99-control-api",
        "bot": "running" if running else "stopped",
        "pid": BOT_PROCESS.pid if running else None,
        "log_path": str(LOG_PATH),
    }


async def require_auth(request):
    if not authorized(request):
        return json_response({"error": "unauthorized"}, status=401)
    return None


async def health(request):
    return json_response({"ok": True, **process_status()})


async def status(request):
    denied = await require_auth(request)
    return denied or json_response({"ok": True, **process_status()})


async def start_bot():
    global BOT_PROCESS, STARTED_AT
    async with PROCESS_LOCK:
        if BOT_PROCESS is not None and BOT_PROCESS.returncode is None:
            return False
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_handle = LOG_PATH.open("a", encoding="utf-8")
        child_env = os.environ.copy()
        child_env["DISABLE_BOT_WEB_SERVER"] = "1"
        BOT_PROCESS = await asyncio.create_subprocess_exec(
            sys.executable,
            str(BOT_SCRIPT),
            cwd=str(BASE_DIR),
            env=child_env,
            stdout=log_handle,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        STARTED_AT = asyncio.get_running_loop().time()
        asyncio.create_task(_close_log_when_done(BOT_PROCESS, log_handle))
        return True


async def _close_log_when_done(process, log_handle):
    try:
        await process.wait()
    finally:
        log_handle.close()


async def stop_bot():
    global BOT_PROCESS
    async with PROCESS_LOCK:
        if BOT_PROCESS is None or BOT_PROCESS.returncode is not None:
            return False
        try:
            os.killpg(BOT_PROCESS.pid, signal.SIGTERM)
            await asyncio.wait_for(BOT_PROCESS.wait(), timeout=10)
        except asyncio.TimeoutError:
            os.killpg(BOT_PROCESS.pid, signal.SIGKILL)
            await BOT_PROCESS.wait()
        return True


async def restart_bot():
    await stop_bot()
    return await start_bot()


async def action(request):
    denied = await require_auth(request)
    if denied:
        return denied
    name = request.match_info["name"]
    if name == "start":
        changed = await start_bot()
    elif name == "stop":
        changed = await stop_bot()
    elif name == "restart":
        changed = await restart_bot()
    else:
        return json_response({"error": "unknown action"}, status=404)
    return json_response({"ok": True, "changed": changed, **process_status()})


async def on_startup(app):
    await start_bot()


async def on_cleanup(app):
    await stop_bot()


app = web.Application()
app.router.add_get("/healthz", health)
app.router.add_get("/api/status", status)
app.router.add_post("/api/{name:start|stop|restart}", action)
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)
