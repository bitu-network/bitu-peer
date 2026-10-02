// file: src/web/internal/dev/globe/6-slider/index.js



// @ts-check
import { createGlobe } from "../../../../assets/globe/globe-view.js";
import { getRankColor } from "../../../../assets/js/color.js";

const Cesium = /** @type {any} */ (window).Cesium;
const d3 = /** @type {any} */ (window).d3;

const globe = createGlobe("cesiumContainer");

const statusEl = document.getElementById('status');
const depthValEl = document.getElementById('depthVal');
const countEl = document.getElementById('count');
const slider = document.getElementById("depth");

const activeEntities = [];



async function requestDepth(depth) {
    statusEl.textContent = "Loading...";
    statusEl.style.color = "#ffaa00";
    try {
        // Explicitly fetch from adjacent api.py
        const response = await fetch(`api.py?depth=${depth}`);

        if (!response.ok) throw new Error("Network response was not ok");
        const message = await response.json();
        if (message.type === 'tree_nodes') {
            renderVoronoiTree(message.data, depth);
            statusEl.textContent = "Connected (HTTP)";
            statusEl.style.color = "#00ff00";
        }
    } catch (err) {
        console.error("Fetch error:", err);
        statusEl.textContent = "Disconnected / Error";
        statusEl.style.color = "#ff4444";
    }
}

function renderVoronoiTree(nodes, maxDepth) {
    for (const entity of activeEntities) {
        globe.entities.remove(entity);
    }
    activeEntities.length = 0;

    countEl.textContent = `Points: ${nodes.length}`;
    const visiblePoints = nodes.map(n => n.pos);

    for (const node of nodes) {
        const [longitude, latitude] = node.pos;
        console.log({ depth: node.depth, maxDepth });
        const entity = globe.entities.add({
            position: Cesium.Cartesian3.fromDegrees(longitude, latitude),
            point: {
                pixelSize: Math.max(6, 14 - (node.depth * 1.0)),

                color: Cesium.Color.fromCssColorString(getRankColor(node.depth + 1)),
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 0
            }
        });
        activeEntities.push(entity);
    }

    if (visiblePoints.length >= 2) {
        try {
            const voronoi = d3.geoVoronoi(visiblePoints);
            const features = voronoi.polygons().features;

            for (const feature of features) {
                const outerRing = feature.geometry.coordinates?.[0];
                if (!outerRing) continue;

                const degreesArray = outerRing.flat();
                const polyEntity = globe.entities.add({
                    polyline: {
                        positions: Cesium.Cartesian3.fromDegreesArray(degreesArray),
                        width: 4,
                        material: Cesium.Color.BLACK.withAlpha(0.1)
                    }
                });
                activeEntities.push(polyEntity);
            }
        } catch (err) {
            console.error("Voronoi computation error:", err);
        }
    }
}

if (slider) {
    slider.addEventListener("input", (e) => {
        const target = /** @type {HTMLInputElement} */ (e.target);
        const depth = parseInt(target.value, 10);
        if (depthValEl) depthValEl.textContent = String(depth);
        requestDepth(depth);
    });

    requestDepth(parseInt(/** @type {HTMLInputElement} */(slider).value, 10));
}

globe.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(0, 20, 25000000),
    duration: 1.5
});

