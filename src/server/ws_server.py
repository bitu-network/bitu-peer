# file: src/server/ws_server.py

import asyncio
import importlib.util
import argparse
from pathlib import Path
import websockets

from config import BIND_HOST
from project import get_src_root

WEB_ROOT = get_src_root() / "web"


async def handler(websocket, target_root):
    path = websocket.request.path.strip("/")
    if not path:
        path = "index"

    # Map directly to target file structure based on mode
    target_path = target_root / path
    
    if target_path.is_dir():
        target_file = target_path / "index.html.ws.py"
    else:
        target_file = target_root / f"{path}.html.ws.py"
        if not target_file.is_file():
            target_file = target_root / path / "index.html.ws.py"

    if not target_file.is_file():
        await websocket.close(code=4004, reason=f"WebSocket handler not found at {target_file}")
        return

    spec = importlib.util.spec_from_file_location("ws_handler", target_file)
    if spec is None or spec.loader is None:
        await websocket.close(code=4050, reason="Failed to load handler spec")
        return

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        if hasattr(module, "handle"):
            await module.handle(websocket)
        else:
            await websocket.close(code=4005, reason="Handler missing 'handle' entrypoint")
    except Exception as e:
        await websocket.close(code=4050, reason=f"Handler error: {str(e)}")


async def main(host: str, port: int, mode: str):
    target_root = WEB_ROOT / mode
    print(f"[WS] Serving handlers from root: {target_root}")
    
    async with websockets.serve(lambda ws: handler(ws, target_root), host, port):
        print(f"WebSocket Server running on ws://{host}:{port}")
        await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run WebSocket Server")
    parser.add_argument("--host", default=BIND_HOST, help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    parser.add_argument("--mode", default="public", choices=["public", "local"], help="Environment mode")
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port, args.mode))