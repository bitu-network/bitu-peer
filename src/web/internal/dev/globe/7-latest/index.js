// file: src/web/internal/dev/globe/7-latest/index.js



// @ts-check
import { createGlobe } from "../../../../assets/globe/globe-view.js";

const Cesium = /** @type {any} */ (window).Cesium;
const d3 = /** @type {any} */ (window).d3;



const globe = createGlobe("cesiumContainer");

const statusEl = document.getElementById('status');
const heightEl = document.getElementById('height-display');
const globeZoomEl = document.getElementById('globe-zoom-display');
const rHopEl = document.getElementById('r-hop-display');
const countEl = document.getElementById('point-count');

function getColorFromR_hop(r_hop, totalChunks = 10) {
    const ratio = Math.min(r_hop / Math.max(totalChunks - 1, 1), 1);
    // Map ratio: r_hop = 0 (Blue at 240°) down to highest r_hop (Red at 0°)
    const hue = (1 - ratio) * (240 / 360);
    return Cesium.Color.fromHsl(hue, 1.0, 0.5);
}

// Actual sphere / globe zoom level derived from camera altitude
function getGlobeZoom(height) {
    if (height <= 0) return 20;
    return Math.max(0, Math.min(25, Math.round(Math.log2(40000000 / height))));
}

// Custom calculated r_hop mapping from height
function getRHopFromHeight(height) {
    const thresholds = [
        { maxAltitude: 25000000, r_hop: 0 },
        { maxAltitude: 19500000, r_hop: 1 },
        { maxAltitude: 15200000, r_hop: 2 },
        { maxAltitude: 11800000, r_hop: 3 },
        { maxAltitude: 9200000, r_hop: 4 },
        { maxAltitude: 7180000, r_hop: 5 },
        { maxAltitude: 5590000, r_hop: 6 },
        { maxAltitude: 4360000, r_hop: 7 },
        { maxAltitude: 3400000, r_hop: 8 },
        { maxAltitude: 2650000, r_hop: 9 },
        { maxAltitude: 2060000, r_hop: 10 },
        { maxAltitude: 1610000, r_hop: 11 },
        { maxAltitude: 1250000, r_hop: 12 },
        { maxAltitude: 975000, r_hop: 13 },
        { maxAltitude: 760000, r_hop: 14 },
        { maxAltitude: 593000, r_hop: 15 },
        { maxAltitude: 462000, r_hop: 16 },
        { maxAltitude: 360000, r_hop: 17 },
        { maxAltitude: 281000, r_hop: 18 },
        { maxAltitude: 219000, r_hop: 19 },
        { maxAltitude: 170000, r_hop: 20 }
    ];

    for (const step of thresholds) {
        if (height >= step.maxAltitude) {
            return step.r_hop;
        }
    }

    return 20;
}

let pinCollection = null;
let rectPrimitive = null;

async function requestViewportUpdate() {
    const height = globe.camera.positionCartographic.height;
    const globeZoom = getGlobeZoom(height);
    const r_hop = getRHopFromHeight(height);
    const rect = globe.camera.computeViewRectangle();

    heightEl.textContent = `Height: ${Math.round(height).toLocaleString()} m`;
    globeZoomEl.textContent = `Sphere Zoom: ${globeZoom}`;
    rHopEl.textContent = `r_hop: ${r_hop}`;

    let bounds = { west: -180, south: -90, east: 180, north: 90 };
    if (rect) {
        bounds = {
            west: Cesium.Math.toDegrees(rect.west),
            south: Cesium.Math.toDegrees(rect.south),
            east: Cesium.Math.toDegrees(rect.east),
            north: Cesium.Math.toDegrees(rect.north)
        };

        const boundsEl = document.getElementById('bounds-display');
        boundsEl.textContent = `N:${bounds.north.toFixed(2)}°, S:${bounds.south.toFixed(2)}° , W:${bounds.west.toFixed(2)}°, E:${bounds.east.toFixed(2)}°`;

        if (rectPrimitive) globe.scene.primitives.remove(rectPrimitive);
        // Skip drawing if the viewport covers the entire globe to avoid the 180° seam artifact
        if (!(bounds.west <= -179 && bounds.east >= 179)) {
            rectPrimitive = globe.scene.primitives.add(new Cesium.Primitive({
                geometryInstances: new Cesium.GeometryInstance({
                    geometry: new Cesium.RectangleOutlineGeometry({
                        rectangle: Cesium.Rectangle.fromDegrees(bounds.west, bounds.south, bounds.east, bounds.north),
                        vertexFormat: Cesium.PolylineColorAppearance.VERTEX_FORMAT
                    }),
                    attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.BLACK) }
                }),
                appearance: new Cesium.PolylineColorAppearance()
            }));
        }

    }

    try {
        const response = await fetch(`api.py?height=${height}&zoom=${globeZoom}&r_hop=${r_hop}&west=${bounds.west}&south=${bounds.south}&east=${bounds.east}&north=${bounds.north}`);
        if (!response.ok) throw new Error("Network response was not ok");
        const message = await response.json();

        if (message.type === 'points') {
            const points = message.data;
            statusEl.textContent = 'Active (HTTP Spatial Query)';
            statusEl.style.color = '#00ff00';
            countEl.textContent = `Points Rendered: ${points.length}`;

            if (pinCollection) {
                globe.scene.primitives.remove(pinCollection);
            }

            pinCollection = globe.scene.primitives.add(new Cesium.PointPrimitiveCollection());

            points.forEach(p => {
                pinCollection.add({
                    position: Cesium.Cartesian3.fromDegrees(p.longitude, p.latitude),
                    pixelSize: 16,
                    color: getColorFromR_hop(p.r_hop),
                    // outlineColor: Cesium.Color.WHITE,
                    outlineWidth: 0
                });
            });
        }
    } catch (err) {
        console.error("Fetch error:", err);
        statusEl.textContent = 'Disconnected / Error';
        statusEl.style.color = '#ff4444';
    }


}

let debounceTimer = null;
globe.camera.changed.addEventListener(() => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(requestViewportUpdate, 200);
});

globe.camera.moveEnd.addEventListener(requestViewportUpdate);

globe.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(0, 20, 22000000),
    duration: 2.5,
    complete: requestViewportUpdate
});