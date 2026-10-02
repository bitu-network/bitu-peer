# file: src/web/internal/dev/ws-test.ws.py

async def on_connect(ws):
    print("ws-test client connected")


async def on_message(ws, msg):

    print(
        "User answered:",
        msg
    )


async def on_disconnect():
    print("ws-test client disconnected")