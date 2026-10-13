import { $, deg, esc, getJSON, toast, openSheet, fmt, queryLayer, polygonRings } from './util.js';
import { lecAt, LEC_NAMES, lecCss } from './lec.js';
import { PICKENS_MAP_DATA } from './endpoints.js';
import { runSiteReport } from './report.js';

const MAX_VIEW_HEIGHT = 7000; // m — parcel lines only draw when zoomed in
const LABEL_HEIGHT = 2500;

// Approximate outline, used only if the county boundary layer can't be fetched.
export const PICKENS_FALLBACK = [[
  [-82.98, 34.88], [-82.97, 35.10], [-82.87, 35.20], [-82.67, 35.22], [-82.54, 35.13],
  [-82.35, 35.06], [-82.38, 34.84], [-82.50, 34.70], [-82.75, 34.69], [-82.90, 34.75], [-82.98, 34.88],
]];

const FIELD_PATTERNS = {
  owner: [/^own(er)?_?(name)?_?1?$/i, /^ownam/i, /owner/i, /^name_?1?$/i],
  tms: [/^tms/i, /^pin$/i, /parcel_?(id|no|num)|parcelid|map_?(num|no)|tax_?map/i, /tms|pin/i],
  acres: [/^(calc_?|gis_?|deed_?)?acre(s|age)?$/i, /acre/i],
  address: [/situs|site_?addr|prop.*addr|phys.*addr|location/i, /^(full_?)?addr(ess)?$/i],
  value: [/tot.*(val|appr)|market|fmv|apprais/i, /val/i],
  mail: [/mail.*(addr|1)|own.*addr/i],
};

function mapFields(fields) {
  const usable = fields.filter(f => !/^(objectid|fid|shape|globalid|st_area|st_length)/i.test(f.name));
  const taken = new Set();
  const m = {};
  for (const [key, patterns] of Object.entries(FIELD_PATTERNS)) {
    for (const re of patterns) {
      const hit = usable.find(f => !taken.has(f.name) && (re.test(f.name) || re.test(f.alias || '')) &&
        !(key === 'address' && /mail|own/i.test(f.name)));
      if (hit) { m[key] = hit.name; taken.add(hit.name); break; }
    }
  }
  return m;
}

let mapLayersP = null;
function countyMapLayers() {
  mapLayersP ??= getJSON(PICKENS_MAP_DATA).then(item => {
    const flat = [];
    (function walk(ls) { for (const l of ls || []) { flat.push(l); walk(l.layers); } })(item.operationalLayers);
    return flat;
  });
  return mapLayersP;
}

async function findCountyLayer(re) {
  const layers = await countyMapLayers();
  const cands = layers.filter(l => l.url && re.test(l.title || ''));
  const pick = cands.find(l => !/label|annot|dimension|text|lot line/i.test(l.title)) || cands[0];
  if (!pick) return null;
  const url = pick.url.replace(/\/+$/, '');
  if (/\/\d+$/.test(url)) return url;
  const svc = await getJSON(`${url}?f=json`);
  const l = (svc.layers || []).find(x => re.test(x.name)) || (svc.layers || [])[0];
  return l ? `${url}/${l.id}` : null;
}

export async function fetchCountyBoundary() {
  try {
    const url = await findCountyLayer(/county.*(bound|line|limit)|boundary/i);
    if (!url) return null;
    const feats = await queryLayer(url, { where: '1=1', outFields: '', returnGeometry: true, geometryPrecision: 5 });
    return feats.find(f => f.geometry && /Polygon/.test(f.geometry.type)) || null;
  } catch {
    return null;
  }
}

export function initParcels(app) {
  const v = app.viewer;
  const labels = new Cesium.CustomDataSource('parcel-labels');
  v.dataSources.add(labels);
  const st = { url: null, meta: null, F: {}, visible: true, prim: null, sel: [], req: 0, tap: 0, status: 'loading…' };

  const api = app.parcels = {
    get visible() { return st.visible; },
    get status() { return st.status; },
    get fields() { return st.F; },
    setVisible(on) { st.visible = on; refresh(); },
    search,
    select,
  };

  function clearLines() {
    if (st.prim) { v.scene.groundPrimitives.remove(st.prim); st.prim = null; }
    labels.entities.removeAll();
  }

  function viewEnvelope() {
    const c = v.camera.positionCartographic;
    const lon = deg(c.longitude), lat = deg(c.latitude);
    const rect = v.camera.computeViewRectangle();
    let [w, s, e, n] = rect ? [rect.west, rect.south, rect.east, rect.north].map(deg) : [lon - 0.03, lat - 0.02, lon + 0.03, lat + 0.02];
    // Tilted views can see the horizon; keep requests local.
    w = Math.max(w, lon - 0.05); e = Math.min(e, lon + 0.05);
    s = Math.max(s, lat - 0.04); n = Math.min(n, lat + 0.04);
    return `${w},${s},${e},${n}`;
  }

  async function refresh() {
    const h = v.camera.positionCartographic.height;
    if (!st.url || !st.visible || h > MAX_VIEW_HEIGHT) { clearLines(); return; }
    const id = ++st.req;
    const outFields = [...new Set(Object.values(st.F))].join(',') || '*';
    try {
      const feats = await queryLayer(st.url, {
        where: '1=1', geometry: viewEnvelope(), geometryType: 'esriGeometryEnvelope', inSR: 4326,
        spatialRel: 'esriSpatialRelIntersects', outFields, returnGeometry: true, geometryPrecision: 6,
      });
      if (id !== st.req) return;
      draw(feats, h);
    } catch (e) {
      if (id === st.req) toast(`Parcels: ${e.message}`);
    }
  }

  function draw(feats, h) {
    clearLines();
    const instances = [];
    for (const f of feats) {
      for (const ring of polygonRings(f.geometry)) {
        if (ring.length < 2) continue;
        instances.push(new Cesium.GeometryInstance({
          geometry: new Cesium.GroundPolylineGeometry({ positions: Cesium.Cartesian3.fromDegreesArray(ring.flat()), width: 2 }),
        }));
      }
    }
    if (instances.length) {
      st.prim = v.scene.groundPrimitives.add(new Cesium.GroundPolylinePrimitive({
        geometryInstances: instances,
        appearance: new Cesium.PolylineMaterialAppearance({
          material: Cesium.Material.fromType('Color', { color: Cesium.Color.fromCssColorString('#ffd54f').withAlpha(0.9) }),
        }),
      }));
    }
    if (h < LABEL_HEIGHT && st.F.owner) {
      for (const f of feats.slice(0, 300)) {
        const name = f.properties[st.F.owner];
        if (!name) continue;
        let pt;
        try { pt = turf.pointOnFeature(f).geometry.coordinates; } catch { continue; }
        labels.entities.add({
          position: Cesium.Cartesian3.fromDegrees(pt[0], pt[1]),
          label: {
            text: String(name).slice(0, 30), font: '600 12px sans-serif',
            fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK, outlineWidth: 3,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            scaleByDistance: new Cesium.NearFarScalar(300, 1.1, LABEL_HEIGHT, 0.65),
          },
        });
      }
    }
  }

  function highlight(f) {
    st.sel.forEach(e => v.entities.remove(e));
    st.sel = [];
    if (!f || !f.geometry) return;
    const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
    const P = ring => Cesium.Cartesian3.fromDegreesArray(ring.flat());
    for (const [outer, ...holes] of polys) {
      st.sel.push(v.entities.add({
        polygon: {
          hierarchy: new Cesium.PolygonHierarchy(P(outer), holes.map(hh => new Cesium.PolygonHierarchy(P(hh)))),
          material: Cesium.Color.YELLOW.withAlpha(0.18),
          classificationType: Cesium.ClassificationType.TERRAIN,
        },
      }));
      st.sel.push(v.entities.add({ polyline: { positions: P(outer), width: 4, clampToGround: true, material: Cesium.Color.YELLOW } }));
    }
  }

  function val(f, key) {
    const k = st.F[key];
    return k ? f.properties[k] : undefined;
  }

  function parcelSection(f) {
    const gisAcres = turf.area(f) / 4046.856;
    const rawAcres = Number(val(f, 'acres'));
    const money = x => (Number.isFinite(Number(x)) && x !== '' && x != null ? `$${Number(x).toLocaleString()}` : esc(x));
    const rows = [
      ['Owner', esc(val(f, 'owner') ?? '—')],
      ['TMS #', esc(val(f, 'tms') ?? '—')],
      ['Address', esc(val(f, 'address') ?? '—')],
      ['Acres', Number.isFinite(rawAcres) && rawAcres > 0 ? `${rawAcres.toFixed(2)} (GIS ${gisAcres.toFixed(2)})` : `${gisAcres.toFixed(2)} (GIS)`],
      ...(val(f, 'value') != null ? [['Value', money(val(f, 'value'))]] : []),
      ...(val(f, 'mail') ? [['Mailing', esc(val(f, 'mail'))]] : []),
    ];
    const all = Object.entries(f.properties)
      .filter(([, x]) => x !== null && x !== '' && x !== ' ')
      .map(([k, x]) => `<tr><td>${esc(k)}</td><td>${esc(x)}</td></tr>`).join('');
    return `
      <table class="kv big">${rows.map(([k, x]) => `<tr><td>${k}</td><td>${x}</td></tr>`).join('')}</table>
      <div class="actions">
        <button class="primary" id="pc-report">Site report</button>
        <button id="pc-zoom">Zoom to parcel</button>
      </div>
      <details><summary>All attributes</summary><table class="kv">${all}</table></details>`;
  }

  function wireParcelButtons(f) {
    $('pc-report').onclick = () => runSiteReport(app, f, { title: val(f, 'owner') || val(f, 'tms') || 'Parcel' });
    $('pc-zoom').onclick = () => zoomTo(f);
  }

  function zoomTo(f) {
    const [w, s, e, n] = turf.bbox(f);
    const pad = Math.max(e - w, n - s) * 0.35 + 0.0008;
    v.camera.flyTo({ destination: Cesium.Rectangle.fromDegrees(w - pad, s - pad, e + pad, n + pad), duration: 1.5 });
  }

  function select(f, { zoom = true } = {}) {
    highlight(f);
    if (zoom) zoomTo(f);
    openSheet(val(f, 'owner') || 'Parcel', parcelSection(f));
    wireParcelButtons(f);
  }

  async function identify(carto) {
    const lon = deg(carto.longitude), lat = deg(carto.latitude);
    const lec = lecAt(lon, lat);
    const pointHtml = elev => `
      <table class="kv">
        <tr><td>Location</td><td>${fmt.ll(lon, lat)}</td></tr>
        <tr><td>Elevation</td><td id="pt-elev">${elev}</td></tr>
        <tr><td>LEC class</td><td>${lec ? `<i class="sw" style="background:${lecCss(lec)}"></i>${LEC_NAMES[lec]}` : '—'}</td></tr>
      </table>
      <div id="pc-parcel">${st.url ? '<p class="muted">Looking up parcel…</p>' : `<p class="muted">Parcels ${esc(st.status)}</p>`}</div>`;
    openSheet('Point', pointHtml('…'));

    const c = Cesium.Cartographic.fromDegrees(lon, lat);
    Cesium.sampleTerrainMostDetailed(app.terrain, [c]).then(([r]) => {
      if ($('pt-elev')) $('pt-elev').textContent = fmt.ft(r.height);
    }).catch(() => {});

    if (!st.url) return;
    const tap = ++st.tap;
    try {
      const [f] = await queryLayer(st.url, {
        geometry: `${lon},${lat}`, geometryType: 'esriGeometryPoint', inSR: 4326,
        spatialRel: 'esriSpatialRelIntersects', outFields: '*', returnGeometry: true, geometryPrecision: 6,
      });
      const slot = $('pc-parcel');
      if (!slot || tap !== st.tap) return;
      if (!f) { slot.innerHTML = '<p class="muted">No parcel here.</p>'; highlight(null); return; }
      highlight(f);
      $('sheet-title').textContent = val(f, 'owner') || 'Parcel';
      slot.innerHTML = parcelSection(f);
      wireParcelButtons(f);
    } catch (e) {
      const slot = $('pc-parcel');
      if (slot) slot.innerHTML = `<p class="err">Parcel lookup failed: ${esc(e.message)}</p>`;
    }
  }

  async function search(q) {
    if (!st.url) { toast(`Parcels ${st.status}`); return; }
    const term = q.trim().toUpperCase().replace(/'/g, "''");
    if (term.length < 3) { toast('Type at least 3 characters'); return; }
    const strFields = ['owner', 'tms', 'address'].map(k => st.F[k]).filter(n => n &&
      (st.meta.fields.find(f => f.name === n) || {}).type === 'esriFieldTypeString');
    if (!strFields.length) { toast('No searchable parcel fields'); return; }
    openSheet('Search', '<p class="muted">Searching…</p>');
    try {
      const feats = (await queryLayer(st.url, {
        where: strFields.map(n => `UPPER(${n}) LIKE '%${term}%'`).join(' OR '),
        outFields: '*', returnGeometry: true, geometryPrecision: 6,
      })).slice(0, 40);
      if (!feats.length) { openSheet('Search', `<p class="muted">No parcels match “${esc(q)}”.</p>`); return; }
      const body = openSheet(`Search · ${feats.length}${feats.length === 40 ? '+' : ''}`, `<ul class="results">${feats.map((f, i) => `
        <li><button data-i="${i}"><b>${esc(val(f, 'owner') ?? '—')}</b>
          <span>${esc(val(f, 'address') ?? '')} · TMS ${esc(val(f, 'tms') ?? '—')} · ${(turf.area(f) / 4046.856).toFixed(1)} ac</span></button></li>`).join('')}</ul>`);
      body.querySelectorAll('[data-i]').forEach(b => b.onclick = () => select(feats[+b.dataset.i]));
    } catch (e) {
      openSheet('Search', `<p class="err">Search failed: ${esc(e.message)}</p>`);
    }
  }

  app.handlers.identify = identify;

  (async () => {
    try {
      st.url = new URLSearchParams(location.search).get('parcels') || await findCountyLayer(/parcel/i);
      if (!st.url) throw new Error('no parcel layer found in county map');
      st.meta = await getJSON(`${st.url}?f=json`);
      st.F = mapFields(st.meta.fields || []);
      st.status = 'loaded';
      v.camera.moveEnd.addEventListener(refresh);
      refresh();
    } catch (e) {
      st.url = null;
      st.status = `unavailable (${e.message})`;
      toast(`Parcel layer unavailable: ${e.message}`, 6000);
    }
  })();

  return api;
}
