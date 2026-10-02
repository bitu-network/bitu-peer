// file: src/web/internal/dev/globe/2-click/index.js


const globeView = /** @type {any} */ (document.querySelector("globe-view"));

globeView.addEventListener("globe-ready", /** @type {EventListener} */ ((e) => {
    const viewer = /** @type {any} */ (e).detail;
    const Cesium = /** @type {any} */ (window).Cesium;

    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

    handler.setInputAction((click) => {
        const ray = viewer.camera.getPickRay(click.position);
        const cartesian = viewer.scene.globe.pick(ray, viewer.scene);
        if (!cartesian) return;

        const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
        const lat = Cesium.Math.toDegrees(cartographic.latitude);
        const lng = Cesium.Math.toDegrees(cartographic.longitude);

        console.log("clicked:", lat, lng);
        globeView.addPoint(lng, lat);
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
}));