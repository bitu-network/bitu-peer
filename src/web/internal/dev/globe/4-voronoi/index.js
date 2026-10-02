// file: src/web/internal/dev/globe/4-voronoi/index.js

export {};

const Cesium = /** @type {any} */ (window).Cesium;
const d3 = /** @type {any} */ (window).d3;
const globeView = /** @type {any} */ (document.querySelector("globe-view"));

const points = [
    [-74.006, 40.7128],
    [-0.1276, 51.5074],
    [139.6917, 35.6895],
];

const voronoiEntities = [];

globeView.addEventListener("globe-ready", (e) => {
    const viewer = e.detail;

    function clearVoronoi() {
        for (const entity of voronoiEntities) viewer.entities.remove(entity);
        voronoiEntities.length = 0;
    }

    function renderVoronoi() {
        clearVoronoi();
        if (points.length < 2) return;

        const voronoi = d3.geoVoronoi(points);
        for (const feature of voronoi.polygons().features) {
            const outerRing = feature.geometry.coordinates?.[0];
            if (!outerRing) continue;
            voronoiEntities.push(globeView.addPolyline(outerRing.flat()));
        }
    }

    for (const [lng, lat] of points) globeView.addPoint(lng, lat);
    renderVoronoi();

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((click) => {
        const ray = viewer.camera.getPickRay(click.position);
        const cartesian = viewer.scene.globe.pick(ray, viewer.scene);
        if (!cartesian) return;

        const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
        const lat = Cesium.Math.toDegrees(cartographic.latitude);
        const lng = Cesium.Math.toDegrees(cartographic.longitude);

        points.push([lng, lat]);
        globeView.addPoint(lng, lat);
        renderVoronoi();
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
});