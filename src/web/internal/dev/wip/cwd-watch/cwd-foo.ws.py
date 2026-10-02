# file: src/web/internal/dev/wip/cwd-watch/cwd-foo.ws.py
import asyncio

async def on_connect(ws):
    print("cwd_foo branch connected")

async def on_message(ws, msg):
    print(f"cwd_foo received message: {msg}")

async def on_disconnect():
    print("cwd_foo branch disconnected")
