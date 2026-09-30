# file: src/server/file_server.py
# NOTE: disabled (.py.off). A pod now has a single `port` and that port belongs
# to the http server, so this raw-TCP front desk has nowhere to bind -- two
# listeners on one port would collide. Re-enable only if it gets a port of its
# own again, or fold lookup/fetch into the http server instead.
# description: per-drive network responder (the "front desk"). Answers hash-based
# lookup and byte-range fetch requests against the CAS tree that service/dedupe.py
# maintains at <drive>:\o\<byte1>\<byte2>\<hash>\content.<ext>. Does no scanning
# or writing of its own -- purely reads what dedupe.py has already built.
#
# Protocol: newline-delimited JSON requests over TCP, one per connection.
#   {"cmd": "status"}
#   {"cmd": "lookup", "hash": "<sha256 hex>"}
#       -> {"found": true, "size": <bytes>} | {"found": false}
#   {"cmd": "fetch", "hash": "<sha256 hex>", "start": <int>, "end": <int>}
#       -> a JSON header line {"found": true, "size": <n>} followed immediately
#          by exactly <n> raw bytes on the same connection (the [start, end)
#          slice of the blob), or {"error": "..."} with no bytes following.
#
# Auto-discovered and launched once per drive by cli/start.py (any .py file
# directly under server/ is spawned per drive found by
# lib/drives.find_bitu_drives(), with the drive letter as its sole argument),
# only for drives with a valid <drive>:\I\-\bitu\config.json (see lib/drives.py).
# Lives under server/ rather than service/ specifically because it opens a
# socket -- process/socket isolation per drive is what makes the mesh-network
# simulation and sensitive-data isolation goals work; dedupe.py has no such
# need and runs as one process for every drive instead (see service/dedupe.py).
# Not meant to be run directly without a pod argument (a drive like D:, or a
# nested pod like D:\pod_1).

from __future__ import annotations

import json
import socketserver
from pathlib import Path

from lib.cas import cas_root, find_existing_blob
from pod.bootstrap import load_pod_or_exit

FETCH_CHUNK_SIZE = 1024 * 1024


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        drive_root: Path = self.server.drive_root  # type: ignore[attr-defined]

        raw = self.rfile.readline()
        if not raw:
            return

        try:
            request = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send_json({"error": f"bad request: {e}"})
            return

        cmd = request.get("cmd")
        if cmd == "status":
            self._send_json({"status": "ok", "drive": str(drive_root)})
        elif cmd == "lookup":
            self._handle_lookup(drive_root, request)
        elif cmd == "fetch":
            self._handle_fetch(drive_root, request)
        else:
            self._send_json({"error": f"unknown cmd: {cmd!r}"})

    def _send_json(self, obj: dict) -> None:
        self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))

    def _handle_lookup(self, drive_root: Path, request: dict) -> None:
        digest = request.get("hash")
        if not digest:
            self._send_json({"error": "missing 'hash'"})
            return
        blob = find_existing_blob(drive_root, digest)
        if blob is None:
            self._send_json({"found": False})
            return
        try:
            size = blob.stat().st_size
        except OSError as e:
            self._send_json({"error": str(e)})
            return
        self._send_json({"found": True, "size": size})

    def _handle_fetch(self, drive_root: Path, request: dict) -> None:
        digest = request.get("hash")
        if not digest:
            self._send_json({"error": "missing 'hash'"})
            return

        blob = find_existing_blob(drive_root, digest)
        if blob is None:
            self._send_json({"error": "not found"})
            return

        try:
            blob_size = blob.stat().st_size
        except OSError as e:
            self._send_json({"error": str(e)})
            return

        start = max(0, int(request.get("start", 0)))
        end = request.get("end")
        end = blob_size if end is None else min(int(end), blob_size)
        length = max(0, end - start)

        self._send_json({"found": True, "size": length})

        try:
            with open(blob, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(FETCH_CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except OSError:
            # Connection or blob became unavailable mid-stream; nothing more we
            # can send at this point since the header already committed to a size.
            pass


class FileServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, handler, drive_root: Path):
        super().__init__(addr, handler)
        self.drive_root = drive_root


def main():
    drive_root, _config, port = load_pod_or_exit("file_server")
    server = FileServer(("127.0.0.1", port), RequestHandler, drive_root)
    print(f"[file_server] {drive_root} -> 127.0.0.1:{port} serving CAS at {cas_root(drive_root)}",
          flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
