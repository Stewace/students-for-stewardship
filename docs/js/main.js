import { $, toast, closeSheet } from './util.js';
import { CESIUM_ION_TOKEN } from './endpoints.js';
import { initLayers } from './layers.js';
import { initParcels, fetchCountyBoundary, PICKENS_FALLBACK } from './parcels.js';
import { initTools, readHashView } from './tools.js';
import { computeLEC } from './lec.js';

Cesium.Ion.defaultAccessToken = CESIUM_ION_TOKEN;

const viewer = new Cesium.Viewer('cesiumContainer', {
  baseLayerPicker: false, navigationHelpButton: false, homeButton: false, sceneModePicker: false,
  geocoder: false, animation: false, timeline: false, fullscreenButton: false,
  infoBox: false, selectionIndicator: false,
});
viewer.scene.globe.depthTestAgainstTerrain = true;
viewer.scene.globe.enableLighting = false;
viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

const app = { viewer, terrain: null, mode: 'identify', handlers: {} };
window.__app = app;

const layers = initLayers(app);
initTools(app);
initParcels(app);

const start = readHashView() || layers.PLACES[0];
layers.flyTo(start, 0);

const tap = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
tap.setInputAction(e => {
  if (!app.terrain) { toast('Terrain still loading…'); return; }
  const cart = viewer.scene.globe.pick(viewer.camera.getPickRay(e.position), viewer.scene);
  if (!cart) return;
  app.handlers[app.mode]?.(Cesium.Cartographic.fromCartesian(cart));
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

$('sheet-close').onclick = closeSheet;
$('search-form').onsubmit = e => {
  e.preventDefault();
  $('search-q').blur();
  app.parcels.search($('search-q').value);
};

function drawBoundary(rings) {
  for (const ring of rings) {
    viewer.entities.add({
      polyline: {
        positions: Cesium.Cartesian3.fromDegreesArray(ring.flat()), width: 2.5, clampToGround: true,
        material: new Cesium.PolylineDashMaterialProperty({ color: Cesium.Color.fromCssColorString('#8bc34a').withAlpha(0.9), dashLength: 18 }),
      },
    });
  }
}

(async () => {
  app.terrain = await Cesium.createWorldTerrainAsync({ requestVertexNormals: true });
  viewer.terrainProvider = app.terrain;

  const boundary = await Promise.race([fetchCountyBoundary(), new Promise(r => setTimeout(() => r(null), 12000))]);
  let county = boundary ? turf.simplify(boundary, { tolerance: 0.0005 }) : turf.polygon(PICKENS_FALLBACK);
  if (!boundary) toast('Using approximate county outline');
  const rings = county.geometry.type === 'Polygon' ? [county.geometry.coordinates[0]] : county.geometry.coordinates.map(p => p[0]);
  drawBoundary(rings);

  const lecLayer = await computeLEC(app, (lon, lat) => turf.booleanPointInPolygon([lon, lat], county));
  layers.setLecLayer(lecLayer);
})().catch(err => {
  console.error(err);
  $('lec-status').textContent = `Error: ${err?.message || err}`;
});
