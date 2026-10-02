// file: src/web/internal/dev/foo/webglearth/webglearth.js
// file: /ui/simulator/simulator.js


(function () {
  const earth = new WE.map('earth_div');
  WE.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap'
  }).addTo(earth);

  const points = [];

  const POINT_QTY = 4;

  for(let i=0;i<POINT_QTY;i++){
    points.push(_randomLatLng())
  }

  points.forEach(([lat, lng]) => {
    WE.marker([lat, lng], { radius: 5, color: '#f00' }).addTo(earth);
  });

  // Connect points with great-circle lines
  for (let i = 0; i < points.length - 1; i++) {
    _drawGreatCircle(earth, points[i], points[i + 1]);
  }
})();








function _randomLatLng() {
  const lat = (Math.random() * 180) - 90;    // -90 to +90
  const lng = (Math.random() * 360) - 180;  // -180 to +180
  return [lat, lng];
}



function _drawGreatCircle(earth, pointA, pointB, options = {}) {
  // Convert lat/lng to 3D Cartesian
  function latLngToCartesian(lat, lng) {
    const radLat = lat * Math.PI / 180;
    const radLng = lng * Math.PI / 180;
    const x = Math.cos(radLat) * Math.cos(radLng);
    const y = Math.cos(radLat) * Math.sin(radLng);
    const z = Math.sin(radLat);
    return [x, y, z];
  }

  // Convert 3D Cartesian to lat/lng
  function cartesianToLatLng(x, y, z) {
    const lat = Math.asin(z) * 180 / Math.PI;
    const lng = Math.atan2(y, x) * 180 / Math.PI;
    return [lat, lng];
  }

  // Spherical linear interpolation (slerp)
  function slerp(a, b, t) {
    const dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const theta = Math.acos(Math.min(Math.max(dot, -1), 1));
    const sinTheta = Math.sin(theta);
    if (sinTheta < 1e-6) return a;
    const f1 = Math.sin((1 - t) * theta) / sinTheta;
    const f2 = Math.sin(t * theta) / sinTheta;
    return [
      f1 * a[0] + f2 * b[0],
      f1 * a[1] + f2 * b[1],
      f1 * a[2] + f2 * b[2]
    ];
  }

  const segments = options.segments || 100;
  const a = latLngToCartesian(pointA[0], pointA[1]);
  const b = latLngToCartesian(pointB[0], pointB[1]);

  const lineCoords = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    const p = slerp(a, b, t);
    lineCoords.push(cartesianToLatLng(p[0], p[1], p[2]));
  }

  WE.polygon(lineCoords, {
    color: options.color || '#00f',
    weight: options.weight || 2,
    geodesic: true
  }).addTo(earth);
}