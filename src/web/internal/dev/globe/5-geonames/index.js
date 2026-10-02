// file: src/web/internal/dev/globe/5-geonames/index.js
export {};

const Cesium = /** @type {any} */ (window).Cesium;
const globeView = /** @type {any} */ (document.querySelector("globe-view"));

const statusEl = document.getElementById('status');
const countEl = document.getElementById('point-count');
const tooltipEl = document.getElementById('tooltip');

function getColorForPopulation(pop) {
    if (pop > 5000000) return Cesium.Color.RED;
    if (pop > 1000000) return Cesium.Color.ORANGE;
    if (pop > 250000) return Cesium.Color.YELLOW;
    return Cesium.Color.CYAN;
}

globeView.addEventListener("globe-ready", async (e) => {
    const viewer = e.detail;

    try {
        const response = await fetch('/assets/cities15000.json');
        if (!response.ok) throw new Error("Failed to load geonames data");
        const data = await response.json();

        statusEl.textContent = 'Active (GeoNames Loaded)';
        statusEl.style.color = '#00ff00';
        countEl.textContent = `Points Rendered: ${data.length}`;

        const pinCollection = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());

        data.forEach(item => {
            const lat = item.lat || item.latitude || item.fields?.latitude;
            const lng = item.lng || item.longitude || item.fields?.longitude;
            const pop = item.population || item.fields?.population || 0;
            const name = item.name || item.ascii_name || item.fields?.name || "Unknown";

            if (lat != null && lng != null) {
                pinCollection.add({
                    position: Cesium.Cartesian3.fromDegrees(Number(lng), Number(lat)),
                    pixelSize: Math.max(4, Math.min(12, Math.log10(Number(pop) + 1) * 2)),
                    color: getColorForPopulation(Number(pop)),
                    outlineColor: Cesium.Color.WHITE,
                    outlineWidth: 0.5,
                    id: {
                        name: String(name),
                        population: Number(pop).toLocaleString()
                    }
                });
            }
        });
    } catch (err) {
        console.error("Fetch error:", err);
        statusEl.textContent = 'Error loading dataset';
        statusEl.style.color = '#ff4444';
    }

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((movement) => {
        const pickedObject = viewer.scene.pick(movement.endPosition);
        if (Cesium.defined(pickedObject) && pickedObject.primitive && pickedObject.id) {
            const d = pickedObject.id;
            if (d && typeof d === 'object' && d.name) {
                tooltipEl.style.display = 'block';
                tooltipEl.style.left = `${movement.endPosition.x + 15}px`;
                tooltipEl.style.top = `${movement.endPosition.y + 15}px`;
                tooltipEl.innerHTML = `<strong>${d.name}</strong><br>Population: ${d.population}`;
                return;
            }
        }
        tooltipEl.style.display = 'none';
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(0, 20, 22000000),
        duration: 2.5
    });
});