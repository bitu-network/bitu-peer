// file: src/web/assets/globe/globe-view.js
const Cesium = /** @type {any} */ (window).Cesium;

export const GLOBE_STYLE = {
  viewer: {
    animation: false,
    timeline: false,
    baseLayerPicker: false,
    geocoder: false,
    infoBox: false,
    selectionIndicator: false,
    homeButton: false,
    fullscreenButton: false,
    navigationHelpButton: false,
    sceneModePicker: false,
    imageryProvider: false,
  },
  imagery: {
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
  },
  scene: {
    backgroundColor: Cesium.Color.BLACK,
    showSkyBox: false,
    showAtmosphere: false,
    lighting: false,
    showSun: false,
    showMoon: false
  },
  point: {
    pixelSize: 16,
    color: Cesium.Color.BLACK
  },
  voronoiLine: {
    width: 2,
    color: Cesium.Color.GREY.withAlpha(1.0)
  },
  polygon: {
    material: Cesium.Color.DODGERBLUE.withAlpha(0.35),
    outlineColor: Cesium.Color.WHITE.withAlpha(0.8)
  }
};

export function createGlobe(container) {
  Cesium.Ion.defaultAccessToken = undefined;
  const viewer = new Cesium.Viewer(container, GLOBE_STYLE.viewer);

  viewer.imageryLayers.addImageryProvider(
    new Cesium.UrlTemplateImageryProvider(GLOBE_STYLE.imagery)
  );

  viewer.cesiumWidget.creditContainer.style.display = "none";
  viewer.scene.skyBox.show = GLOBE_STYLE.scene.showSkyBox;
  viewer.scene.backgroundColor = GLOBE_STYLE.scene.backgroundColor;
  viewer.scene.skyAtmosphere.show = GLOBE_STYLE.scene.showAtmosphere;
  viewer.scene.sun.show = GLOBE_STYLE.scene.showSun;
  viewer.scene.moon.show = GLOBE_STYLE.scene.showMoon;
  viewer.scene.globe.showGroundAtmosphere = false;
  viewer.scene.globe.enableLighting = GLOBE_STYLE.scene.lighting;
  viewer.scene.globe.baseColor = Cesium.Color.BLACK;
  viewer.scene.globe.showSkirts = false;

  return viewer;
}

export function addPoint(viewer, lng, lat, style = GLOBE_STYLE.point) {
  return viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(lng, lat),
    point: { pixelSize: style.pixelSize, color: style.color }
  });
}

export function addPolygon(viewer, coordinates, style = GLOBE_STYLE.polygon) {
  const positions = coordinates.map(([lng, lat]) => Cesium.Cartesian3.fromDegrees(lng, lat));
  return viewer.entities.add({
    polygon: {
      hierarchy: positions,
      material: style.material,
      outline: true,
      outlineColor: style.outlineColor
    }
  });
}

export function addPolyline(viewer, degreesArray, style = GLOBE_STYLE.voronoiLine) {
  return viewer.entities.add({
    polyline: {
      positions: Cesium.Cartesian3.fromDegreesArray(degreesArray),
      width: style.width,
      material: style.color
    }
  });
}

class GlobeView extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    const container = document.createElement('div');
    container.id = 'cesiumContainer';
    Object.assign(container.style, { width: '100%', height: '100%' });
    this.shadowRoot.append(container);

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdn.jsdelivr.net/npm/cesium@1.136.0/Build/Cesium/Widgets/widgets.css';
    this.shadowRoot.append(link);

    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/cesium@1.136.0/Build/Cesium/Cesium.js';
    script.onload = () => this.initGlobe(container);
    this.shadowRoot.append(script);
  }

  initGlobe(container) {
    const viewer = createGlobe(container);
    viewer.scene.skyBox.show = false;
    viewer.scene.skyAtmosphere.show = false;
    viewer.scene.backgroundColor = Cesium.Color.BLACK;
    viewer.cesiumWidget.creditContainer.style.display = 'none';
    viewer.scene.sun.show = false;
    viewer.scene.moon.show = false;
    viewer.scene.globe.enableLighting = false;

    this.viewer = viewer;
    this.dispatchEvent(new CustomEvent("globe-ready", { detail: viewer, bubbles: true, composed: true }));
  }

  addPoint(lng, lat, style) {
    return addPoint(this.viewer, lng, lat, style);
  }

  addPolygon(coordinates, style) {
    return addPolygon(this.viewer, coordinates, style);
  }

  addPolyline(degreesArray, style) {
    return addPolyline(this.viewer, degreesArray, style);
  }
}

customElements.define('globe-view', GlobeView);