# file: src/web/internal/dev/globe/7-latest/api.py

import os
import sqlite3
from flask import request, jsonify

DB_PATH = os.path.join(os.path.dirname(__file__), "../dummy_points.sqlite")

def handle():
    if not os.path.exists(DB_PATH):
        return jsonify({"type": "error", "message": "Database not found."}), 404

    try:
        # Use r_hop directly for depth control
        r_hop_val = int(request.args.get("r_hop", 2))
        max_hop = min(r_hop_val, 20)

        min_lat = request.args.get("south", type=float) or request.args.get("min_lat", type=float)
        max_lat = request.args.get("north", type=float) or request.args.get("max_lat", type=float)
        min_lng = request.args.get("west", type=float) or request.args.get("min_lng", type=float)
        max_lng = request.args.get("east", type=float) or request.args.get("max_lng", type=float)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        if None not in (min_lat, max_lat, min_lng, max_lng):
            query = """
                SELECT id, latitude, longitude, r_hop 
                FROM points 
                WHERE r_hop <= ? 
                  AND latitude BETWEEN ? AND ? 
                  AND longitude BETWEEN ? AND ?
                ORDER BY r_hop DESC
            """
            cursor.execute(query, (max_hop, min_lat, max_lat, min_lng, max_lng))
        else:
            query = """
                SELECT id, latitude, longitude, r_hop 
                FROM points 
                WHERE r_hop <= ?
                ORDER BY r_hop DESC
            """
            cursor.execute(query, (max_hop,))

        rows = cursor.fetchall()
        conn.close()

        points_data = []
        for row in rows:
            point_id, latitude, longitude, r_hop = row
            points_data.append({
                "id": point_id,
                "r_hop": r_hop,
                "latitude": latitude,
                "longitude": longitude
            })

        return jsonify({
            "type": "points",
            "zoom": max_hop,
            "data": points_data
        })

    except Exception as e:
        return jsonify({"type": "error", "message": str(e)}), 400
