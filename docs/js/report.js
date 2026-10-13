import { $, esc, openSheet, fmt, queryLayer, findSublayer, breakdown, download } from './util.js';
import { lecAt, LEC_NAMES, lecCss } from './lec.js';
import { FEMA_NFHL, NWI, SDA_REST } from './endpoints.js';

const SAMPLE_TARGET = 400;
const STEP_M = 15; // offset for finite-difference slope

const SLOPE_CLASSES = [
  { max: 8, label: '0–8% gentle', color: '#7cb342' },
  { max: 15, label: '8–15% moderate', color: '#fdd835' },
  { max: 25, label: '15–25% steep', color: '#fb8c00' },
  { max: Infinity, label: '>25% very steep', color: '#c62828' },
];
const ASPECTS = [
  { label: 'North', color: '#1e88e5' }, { label: 'East', color: '#26a69a' },
  { label: 'South', color: '#ef6c00' }, { label: 'West', color: '#8e24aa' },
];
const PALETTE = ['#1565c0', '#00897b', '#7cb342', '#f9a825', '#ef6c00', '#8e24aa', '#6d4c41', '#546e7a'];

function gridSamples(feat) {
  const [w, s, e, n] = turf.bbox(feat);
  const cos = Math.cos(((s + n) / 2) * Math.PI / 180);
  const areaDeg = Math.max((e - w) * cos * (n - s), 1e-12);
  const stepLat = Math.sqrt(areaDeg / (SAMPLE_TARGET * 1.6));
  const stepLon = stepLat / cos;
  const pts = [];
  for (let lat = s + stepLat / 2; lat < n; lat += stepLat) {
    for (let lon = w + stepLon / 2; lon < e; lon += stepLon) {
      if (turf.booleanPointInPolygon([lon, lat], feat)) pts.push({ lon, lat });
    }
  }
  if (!pts.length) {
    const [lon, lat] = turf.pointOnFeature(feat).geometry.coordinates;
    pts.push({ lon, lat });
  }
  return pts;
}

async function terrainStats(app, pts) {
  const lat0 = pts[0].lat;
  const dLat = STEP_M / 110950, dLon = STEP_M / (111320 * Math.cos(lat0 * Math.PI / 180));
  const cartos = pts.flatMap(p => [
    Cesium.Cartographic.fromDegrees(p.lon, p.lat),
    Cesium.Cartographic.fromDegrees(p.lon + dLon, p.lat),
    Cesium.Cartographic.fromDegrees(p.lon, p.lat + dLat),
  ]);
  await Cesium.sampleTerrainMostDetailed(app.terrain, cartos);
  pts.forEach((p, i) => {
    const [z0, zx, zy] = [cartos[3 * i].height, cartos[3 * i + 1].height, cartos[3 * i + 2].height];
    const gx = (zx - z0) / STEP_M, gy = (zy - z0) / STEP_M;
    p.elev = z0;
    p.slope = Math.hypot(gx, gy) * 100;
    p.aspect = (Math.atan2(-gx, -gy) * 180 / Math.PI + 360) % 360;
  });
}

function zoneIn(pts, feats, labelFn) {
  for (const p of pts) {
    const f = feats.find(ff => turf.booleanPointInPolygon([p.lon, p.lat], ff));
    p[labelFn.key] = f ? labelFn(f.properties) : null;
  }
}

function tally(pts, keyFn, acresPer) {
  const m = new Map();
  for (const p of pts) { const k = keyFn(p); if (k != null) m.set(k, (m.get(k) || 0) + acresPer); }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

const acresFmt = a => `${a.toFixed(2)} ac`;

async function floodSection(feat, pts, acresPer) {
  const url = await findSublayer(FEMA_NFHL, /flood hazard zones/i, 28);
  const feats = await queryLayer(url, {
    geometry: turf.bbox(feat).join(','), geometryType: 'esriGeometryEnvelope', inSR: 4326,
    spatialRel: 'esriSpatialRelIntersects', outFields: 'FLD_ZONE,ZONE_SUBTY,SFHA_TF', returnGeometry: true, geometryPrecision: 6,
  });
  const label = Object.assign(pr => `${pr.FLD_ZONE || '?'}${pr.ZONE_SUBTY ? ` – ${pr.ZONE_SUBTY.toLowerCase()}` : ''}`, { key: 'flood' });
  zoneIn(pts, feats, label);
  for (const p of pts) p.sfha = !!p.flood && /^(A|V)/.test(p.flood) && !/0\.2/.test(p.flood);
  const rows = tally(pts, p => p.flood || 'Outside mapped hazard polygons', acresPer);
  const sfhaAc = pts.filter(p => p.sfha).length * acresPer;
  return `<p>${sfhaAc > 0 ? `<b class="warn">${acresFmt(sfhaAc)} in the 1% annual-chance floodplain (SFHA).</b>` : 'No Special Flood Hazard Area on this parcel.'}</p>` +
    breakdown(rows.map(([k, a], i) => ({ label: k, value: a, color: /^(A|V)/.test(k) ? '#1565c0' : PALETTE[(i + 3) % PALETTE.length] })), acresFmt);
}

async function wetlandSection(feat, pts, acresPer) {
  const url = await findSublayer(NWI, /wetland/i, 0);
  const feats = await queryLayer(url, {
    geometry: turf.bbox(feat).join(','), geometryType: 'esriGeometryEnvelope', inSR: 4326,
    spatialRel: 'esriSpatialRelIntersects', outFields: '*', returnGeometry: true, geometryPrecision: 6,
  });
  const label = Object.assign(pr => pr.WETLAND_TYPE || pr.Wetland_Type || pr.ATTRIBUTE || 'Wetland', { key: 'wetland' });
  zoneIn(pts, feats, label);
  const rows = tally(pts, p => p.wetland, acresPer);
  if (!rows.length) return '<p>No NWI wetlands mapped on this parcel.</p>';
  return breakdown(rows.map(([k, a], i) => ({ label: k, value: a, color: PALETTE[i % PALETTE.length] })), acresFmt) +
    '<p class="fine">NWI is a planning inventory, not a jurisdictional delineation.</p>';
}

function toWKT(feat) {
  let f = feat;
  for (let tol = 0.00002; turf.coordAll(f).length > 250 && tol < 0.01; tol *= 2) f = turf.simplify(feat, { tolerance: tol });
  const ring = r => `(${r.map(([x, y]) => `${x.toFixed(6)} ${y.toFixed(6)}`).join(', ')})`;
  const poly = rings => `(${rings.map(ring).join(', ')})`;
  return f.geometry.type === 'Polygon' ? `POLYGON ${poly(f.geometry.coordinates)}` : `MULTIPOLYGON (${f.geometry.coordinates.map(poly).join(', ')})`;
}

async function sda(query) {
  const r = await fetch(SDA_REST, { method: 'POST', body: JSON.stringify({ query, format: 'JSON+COLUMNNAME' }) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const j = await r.json();
  const [cols, ...rows] = j.Table || [];
  return rows.map(row => Object.fromEntries(cols.map((c, i) => [c, row[i]])));
}

// Even-odd test across every ring handles both holes and multipart polygons.
function parseWKTRings(wkt) {
  return [...wkt.matchAll(/\(([^()]+)\)/g)].map(m => m[1].split(',').map(pair => pair.trim().split(/\s+/).map(Number)));
}
function inRings(x, y, rings) {
  let inside = false;
  for (const r of rings) {
    for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
      if ((r[i][1] > y) !== (r[j][1] > y) && x < (r[j][0] - r[i][0]) * (y - r[i][1]) / (r[j][1] - r[i][1]) + r[i][0]) inside = !inside;
    }
  }
  return inside;
}

async function soilSection(feat, pts, acresPer) {
  const wkt = toWKT(feat);
  const units = await sda(`SELECT m.mukey, m.musym, m.muname, a.drclassdcd, a.hydgrpdcd, a.flodfreqdcd
    FROM mapunit m LEFT JOIN muaggatt a ON a.mukey = m.mukey
    WHERE m.mukey IN (SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('${wkt}'))`);
  if (!units.length) return '<p>No SSURGO map units returned.</p>';

  let acres = null;
  try {
    const polys = await sda(`SELECT P.mukey, P.mupolygongeo.STAsText() AS wkt FROM mupolygon P
      WHERE P.mupolygonkey IN (SELECT * FROM SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('${wkt}'))`);
    const parsed = polys.map(p => ({ mukey: String(p.mukey), rings: parseWKTRings(p.wkt) }));
    for (const p of pts) p.mukey = (parsed.find(pp => inRings(p.lon, p.lat, pp.rings)) || {}).mukey || null;
    acres = new Map(tally(pts, p => p.mukey, acresPer));
  } catch { /* per-unit acreage is optional */ }

  units.sort((a, b) => (acres?.get(String(b.mukey)) || 0) - (acres?.get(String(a.mukey)) || 0));
  return `<table class="kv soil"><tr><th>Map unit</th><th>Drainage</th><th>HSG</th>${acres ? '<th>Acres</th>' : ''}</tr>${units.map(u => `
    <tr><td><b>${esc(u.musym)}</b> ${esc(u.muname)}${u.flodfreqdcd && !/none/i.test(u.flodfreqdcd) ? ` <small class="warn">flooding: ${esc(u.flodfreqdcd)}</small>` : ''}</td>
    <td>${esc(u.drclassdcd || '—')}</td><td>${esc(u.hydgrpdcd || '—')}</td>
    ${acres ? `<td>${(acres.get(String(u.mukey)) || 0).toFixed(1)}</td>` : ''}</tr>`).join('')}</table>
    <p class="fine">HSG = hydrologic soil group (A drains fastest, D slowest). Source: USDA NRCS Soil Data Access.</p>`;
}

function section(id, title) {
  return `<section class="rp"><h3>${title}</h3><div id="${id}"><p class="muted">Loading…</p></div></section>`;
}

export async function runSiteReport(app, feat, { title = 'Parcel' } = {}) {
  const areaAc = turf.area(feat) / 4046.856;
  openSheet(`Site report · ${title}`, `
    <p><b>${areaAc.toFixed(2)} acres</b> (GIS) · <span id="rp-n"></span></p>
    ${section('rp-build', 'Buildable estimate')}
    ${section('rp-terrain', 'Terrain')}
    ${section('rp-lec', 'Landscape ecosystem classes')}
    ${section('rp-flood', 'FEMA flood zones')}
    ${section('rp-wet', 'Wetlands (NWI)')}
    ${section('rp-soil', 'Soils (SSURGO)')}
    <div class="actions"><button id="rp-export">Export GeoJSON</button></div>
    <p class="fine">Screening estimate from public data sampled on a grid — not a survey, delineation, or legal determination.</p>`);

  const pts = gridSamples(feat);
  const acresPer = areaAc / pts.length;
  $('rp-n').textContent = `${pts.length} sample points`;
  $('rp-export').onclick = () => download('parcel.geojson', JSON.stringify(feat), 'application/geo+json');
  const fill = (id, html) => { const el = $(id); if (el) el.innerHTML = html; };
  const fail = (id, e) => fill(id, `<p class="err">Unavailable: ${esc(e.message || e)}</p>`);

  const terrainP = terrainStats(app, pts).then(() => {
    const el = pts.map(p => p.elev);
    const [lo, hi] = [Math.min(...el), Math.max(...el)];
    const mean = el.reduce((a, b) => a + b, 0) / el.length;
    const avgSlope = pts.reduce((a, p) => a + p.slope, 0) / pts.length;
    fill('rp-terrain', `
      <table class="kv"><tr><td>Elevation</td><td>${fmt.ft(lo)} – ${fmt.ft(hi)} (mean ${fmt.ft(mean)})</td></tr>
      <tr><td>Relief</td><td>${fmt.ft(hi - lo)}</td></tr><tr><td>Mean slope</td><td>${avgSlope.toFixed(1)}%</td></tr></table>
      <h4>Slope</h4>${breakdown(SLOPE_CLASSES.map(c => ({ label: c.label, value: pts.filter(p => p.slope < c.max && p.slope >= (SLOPE_CLASSES[SLOPE_CLASSES.indexOf(c) - 1]?.max ?? 0)).length * acresPer, color: c.color })), acresFmt)}
      <h4>Aspect</h4>${breakdown(ASPECTS.map((a, i) => ({ label: a.label, value: pts.filter(p => p.slope >= 2 && Math.floor(((p.aspect + 45) % 360) / 90) === i).length * acresPer, color: a.color })), acresFmt)}`);
    const lecRows = tally(pts, p => lecAt(p.lon, p.lat), acresPer);
    fill('rp-lec', lecRows.length
      ? breakdown(lecRows.map(([k, a]) => ({ label: LEC_NAMES[k], value: a, color: lecCss(k) })), acresFmt)
      : '<p class="muted">LEC grid still computing — reopen the report when it finishes.</p>');
  }).catch(e => { fail('rp-terrain', e); fail('rp-lec', e); throw e; });

  const floodP = floodSection(feat, pts, acresPer).then(h => fill('rp-flood', h)).catch(e => { fail('rp-flood', e); throw e; });
  const wetP = wetlandSection(feat, pts, acresPer).then(h => fill('rp-wet', h)).catch(e => { fail('rp-wet', e); throw e; });
  soilSection(feat, pts, acresPer).then(h => fill('rp-soil', h)).catch(e => fail('rp-soil', e));

  const [t, fl, wt] = await Promise.allSettled([terrainP, floodP, wetP]);
  if (t.status === 'rejected') { fill('rp-build', '<p class="err">Needs terrain data.</p>'); return; }
  const ok = pts.filter(p => p.slope < 15 && !p.sfha && !p.wetland);
  const caveats = [fl.status === 'rejected' && 'flood', wt.status === 'rejected' && 'wetland'].filter(Boolean);
  fill('rp-build', `
    <p class="big"><b>${(ok.length * acresPer).toFixed(2)} ac</b> of ${areaAc.toFixed(2)} (${fmt.pct(ok.length / pts.length)})</p>
    <p class="fine">Land under 15% slope, outside the SFHA and NWI wetlands. Setbacks, easements and zoning are not applied.
    ${caveats.length ? `<span class="warn">Not checked: ${caveats.join(', ')} (service unavailable).</span>` : ''}</p>`);
}
