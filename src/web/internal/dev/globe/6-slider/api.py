# file: src/web/internal/dev/globe/6-slider/api.py

import os
import sqlite3
from flask import request, jsonify

DB_PATH = os.path.join(os.path.dirname(__file__), "../dummy_points.sqlite")

def handle():
    if not os.path.exists(DB_PATH):
        return jsonify({"type": "error", "message": "Database not found."}), 404

    try:
        max_depth = int(request.args.get("depth", 2))
        safe_depth = min(max_depth, 15)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Enforce a strict safety ceiling to protect browser and server memory
        cursor.execute("""
            SELECT id, latitude, longitude, r_hop 
            FROM points 
            WHERE r_hop <= ? 
        """, (safe_depth,))
        
        rows = cursor.fetchall()
        conn.close()

        points_data = []
        for row in rows:
            point_id, latitude, longitude, r_hop = row
            points_data.append({
                "id": point_id,
                "depth": r_hop,
                "pos": [longitude, latitude]
            })

        return jsonify({
            "type": "tree_nodes",
            "depth": safe_depth,
            "data": points_data
        })

    except Exception as e:
        return jsonify({"type": "error", "message": str(e)}), 400