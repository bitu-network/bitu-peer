# file: src/web/internal/dev/wip/cwd-watch/ws-integration-test.py
import asyncio
import json
import websockets

async def server_ticker(websocket):
    """Pushes a message to the client every 3 seconds independently."""
    try:
        count = 0
        while True:
            await asyncio.sleep(3)
            count += 1
            await websocket.send(json.dumps({"server_push": f"Background tick #{count}"}))
            print(f"[WS] Server pushed tick #{count}")
    except websockets.exceptions.ConnectionClosed:
        pass

async def handle(websocket):
    print("[WS] Client connected to dynamic handler.")
    
    # Start the background ticker task for this specific connection
    ticker_task = asyncio.create_task(server_ticker(websocket))
    
    try:
        async for message in websocket:
            data = json.loads(message)
            num = int(data.get("number", 0))
            incremented = num + 1
            print(f"[WS] Received: {num} | Sending back: {incremented}")
            await websocket.send(json.dumps({"result": incremented}))
    except websockets.exceptions.ConnectionClosed:
        print("[WS] Client disconnected.")
    finally:
        # Clean up the background task when the client leaves
        ticker_task.cancel()