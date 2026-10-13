import { $, esc, toast, openSheet, store, persist } from './util.js';
import { LEC_NAMES, lecCss } from './lec.js';
import * as EP from './endpoints.js';

const template = (url, maximumLevel, credit) => () =>
  new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider({ url, maximumLevel, credit }));

const arcgis = (url, opts = {}) => () =>
  Cesium.ImageryLayer.fromProviderAsync(Cesium.ArcGisMapServerImageryProvider.fromUrl(url, opts));

function dep3(rasterFunction) {
  const rr = encodeURIComponent(JSON.stringify({ rasterFunction }));
  return () => new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider({
    url: `${EP.USGS_3DEP}/exportImage?bbox={westProjected},{southProjected},{eastProjected},{northProjected}` +
      `&bboxSR=102100&imageSR=102100&size={width},{height}&format=png&renderingRule=${rr}&f=image`,
    tilingScheme: new Cesium.WebMercatorTilingScheme(),
    maximumLevel: 16,
    credit: 'USGS 3DEP',
  }));
}

const BASEMAPS = [
  { id: 'sat', name: 'Satellite', make: () => Cesium.ImageryLayer.fromWorldImagery({ style: Cesium.IonWorldImageryStyle.AERIAL }) },
  { id: 'hybrid', name: 'Hybrid', make: () => Cesium.ImageryLayer.fromWorldImagery({ style: Cesium.IonWorldImageryStyle.AERIAL_WITH_LABELS }) },
  { id: 'topo', name: 'USGS Topo', make: template(`${EP.USGS_BASEMAP}/USGSTopo/MapServer/tile/{z}/{y}/{x}`, 16, 'USGS The National Map') },
  { id: 'imgtopo', name: 'Imagery + Topo', make: template(`${EP.USGS_BASEMAP}/USGSImageryTopo/MapServer/tile/{z}/{y}/{x}`, 16, 'USGS The National Map') },
  { id: 'esri', name: 'Esri Imagery', make: template(EP.ESRI_IMAGERY, 19, 'Esri, Maxar, Earthstar Geographics') },
];

const OVERLAYS = [
  { id: 'lec', group: 'Ecology', name: 'LEC landscape classes', alpha: 0.72, on: true },
  { id: 'hillshade', group: 'Terrain', name: 'Hillshade (3DEP)', alpha: 0.45, make: dep3('Hillshade Gray') },
  { id: 'slope', group: 'Terrain', name: 'Slope (3DEP)', alpha: 0.55, make: dep3('Slope Map') },
  { id: 'contours', group: 'Terrain', name: 'Contours (USGS)', alpha: 1, make: arcgis(EP.USGS_CONTOURS), note: 'zoom in' },
  { id: 'hydro', group: 'Water', name: 'Streams & lakes (NHD)', alpha: 1, make: template(`${EP.USGS_BASEMAP}/USGSHydroCached/MapServer/tile/{z}/{y}/{x}`, 16, 'USGS NHD') },
  { id: 'flood', group: 'Water', name: 'FEMA flood zones', alpha: 0.6, make: arcgis(EP.FEMA_NFHL, { layers: '28' }) },
  { id: 'wetlands', group: 'Water', name: 'Wetlands (NWI)', alpha: 0.65, make: arcgis(EP.NWI), note: 'zoom in' },
  {
    id: 'soils', group: 'Land', name: 'Soils (SSURGO)', alpha: 0.85, note: 'zoom in',
    make: () => new Cesium.ImageryLayer(new Cesium.WebMapServiceImageryProvider({
      url: EP.SDA_WMS, layers: 'mapunitpoly',
      parameters: { transparent: true, format: 'image/png' }, credit: 'USDA NRCS SSURGO',
    })),
  },
  { id: 'padus', group: 'Land', name: 'Public land (PAD-US)', alpha: 0.5, make: arcgis(EP.PADUS) },
];

const PLACES = [
  { name: 'Pickens County', lon: -82.68, lat: 34.80, h: 48000, pitch: -50, heading: 0 },
  { name: 'Table Rock', lon: -82.70, lat: 34.99, h: 4500, pitch: -25, heading: 0 },
  { name: 'Clemson Forest', lon: -82.83, lat: 34.70, h: 6000, pitch: -40, heading: 20 },
  { name: 'Lake Keowee', lon: -82.90, lat: 34.80, h: 9000, pitch: -40, heading: 330 },
];

export function initLayers(app) {
  const v = app.viewer;
  const saved = store('sfs.layers', {});
  const state = {
    base: saved.base || 'sat',
    on: new Set(saved.on || OVERLAYS.filter(o => o.on).map(o => o.id)),
    alpha: saved.alpha || {},
    exag: saved.exag || 1,
    terrain3d: true,
    status: {},
    layers: {},
  };
  const save = () => persist('sfs.layers', { base: state.base, on: [...state.on], alpha: state.alpha, exag: state.exag });

  function setBase(id) {
    const def = BASEMAPS.find(b => b.id === id) || BASEMAPS[0];
    const old = v.imageryLayers.get(0);
    if (old) v.imageryLayers.remove(old, true);
    v.imageryLayers.add(def.make(), 0);
    state.base = def.id;
    save();
  }

  function watch(layer, def) {
    const onProvider = p => {
      let errs = 0;
      p.errorEvent.addEventListener(() => {
        if (++errs === 8) { state.status[def.id] = 'tiles failing — service may block browser access'; toast(`${def.name}: tiles failing`); }
      });
    };
    if (layer.ready) onProvider(layer.imageryProvider);
    else {
      layer.readyEvent.addEventListener(onProvider);
      layer.errorEvent.addEventListener(e => {
        state.status[def.id] = `unavailable (${(e && e.message) || 'service error'})`;
        toast(`${def.name} unavailable`);
      });
    }
  }

  function apply(def) {
    const want = state.on.has(def.id);
    let layer = state.layers[def.id];
    if (want && !layer && def.make) {
      layer = state.layers[def.id] = def.make();
      v.imageryLayers.add(layer);
      watch(layer, def);
    }
    if (layer) {
      layer.show = want;
      layer.alpha = state.alpha[def.id] ?? def.alpha;
    }
  }

  function setLecLayer(layer) {
    state.layers.lec = layer;
    v.imageryLayers.add(layer);
    apply(OVERLAYS[0]);
  }

  function setExaggeration(x) {
    state.exag = x;
    if ('verticalExaggeration' in v.scene) v.scene.verticalExaggeration = x;
    save();
  }

  function flyTo(p, duration = 2) {
    v.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, p.h),
      orientation: { heading: Cesium.Math.toRadians(p.heading), pitch: Cesium.Math.toRadians(p.pitch), roll: 0 },
      duration,
    });
  }

  function lecLegend() {
    return `<div class="legend">${Object.entries(LEC_NAMES).map(([k, n]) => `<span><i class="sw" style="background:${lecCss(k)}"></i>${n}</span>`).join('')}</div>`;
  }

  function open() {
    const groups = [...new Set(OVERLAYS.map(o => o.group))];
    const html = `
      <h3>Basemap</h3>
      <div class="chips">${BASEMAPS.map(b => `<button class="chip ${b.id === state.base ? 'on' : ''}" data-base="${b.id}">${esc(b.name)}</button>`).join('')}</div>
      <h3>Parcels</h3>
      <label class="row"><input type="checkbox" id="ly-parcels" ${app.parcels?.visible ? 'checked' : ''}> Property lines &amp; owners
        <small>${esc(app.parcels?.status || '')}</small></label>
      ${groups.map(g => `<h3>${g}</h3>` + OVERLAYS.filter(o => o.group === g).map(o => `
        <div class="row">
          <label><input type="checkbox" data-ov="${o.id}" ${state.on.has(o.id) ? 'checked' : ''}> ${esc(o.name)}
            ${o.note ? `<small>${esc(o.note)}</small>` : ''}
            ${state.status[o.id] ? `<small class="err">${esc(state.status[o.id])}</small>` : ''}
            ${o.id === 'lec' && !state.layers.lec ? '<small>computing…</small>' : ''}</label>
          <input type="range" min="0" max="100" value="${Math.round((state.alpha[o.id] ?? o.alpha) * 100)}" data-alpha="${o.id}">
        </div>${o.id === 'lec' ? lecLegend() : ''}`).join('')).join('')}
      <h3>3D</h3>
      <label class="row"><input type="checkbox" id="ly-terrain" ${state.terrain3d ? 'checked' : ''}> 3D terrain</label>
      <label class="row">Exaggeration <input type="range" id="ly-exag" min="1" max="3" step="0.25" value="${state.exag}"> <span id="ly-exag-v">${state.exag}×</span></label>
      <h3>Jump to</h3>
      <div class="chips">${PLACES.map((p, i) => `<button class="chip" data-place="${i}">${esc(p.name)}</button>`).join('')}</div>
      <p class="fine">Data: Cesium World Terrain, USGS The National Map &amp; 3DEP, FEMA NFHL, USFWS NWI, USDA NRCS SSURGO, USGS PAD-US, Pickens County GIS. Screening use only — not a survey.</p>`;
    const body = openSheet('Layers', html);

    body.querySelectorAll('[data-base]').forEach(b => b.onclick = () => {
      setBase(b.dataset.base);
      body.querySelectorAll('[data-base]').forEach(x => x.classList.toggle('on', x === b));
    });
    body.querySelectorAll('[data-ov]').forEach(cb => cb.onchange = () => {
      const def = OVERLAYS.find(o => o.id === cb.dataset.ov);
      cb.checked ? state.on.add(def.id) : state.on.delete(def.id);
      apply(def); save();
    });
    body.querySelectorAll('[data-alpha]').forEach(r => r.oninput = () => {
      const def = OVERLAYS.find(o => o.id === r.dataset.alpha);
      state.alpha[def.id] = r.value / 100;
      apply(def); save();
    });
    body.querySelectorAll('[data-place]').forEach(b => b.onclick = () => flyTo(PLACES[+b.dataset.place]));
    $('ly-parcels').onchange = e => app.parcels?.setVisible(e.target.checked);
    $('ly-terrain').onchange = e => {
      state.terrain3d = e.target.checked;
      v.terrainProvider = state.terrain3d && app.terrain ? app.terrain : new Cesium.EllipsoidTerrainProvider();
    };
    $('ly-exag').oninput = e => { setExaggeration(+e.target.value); $('ly-exag-v').textContent = `${e.target.value}×`; };
  }

  setBase(state.base);
  OVERLAYS.filter(o => o.make).forEach(apply);
  setExaggeration(state.exag);
  $('btn-layers').onclick = open;

  return { setLecLayer, flyTo, PLACES };
}
