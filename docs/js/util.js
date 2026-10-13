export const $ = id => document.getElementById(id);
export const deg = r => Cesium.Math.toDegrees(r);

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function qs(params) {
  return Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(typeof v === 'object' ? JSON.stringify(v) : v)}`)
    .join('&');
}

export async function getJSON(url, opts = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), opts.timeout || 25000);
  try {
    const r = await fetch(url, { ...opts, signal: ctrl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    if (j && j.error) throw new Error(j.error.message || 'service error');
    return j;
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('timed out');
    throw e;
  } finally {
    clearTimeout(t);
  }
}

let toastTimer;
export function toast(msg, ms = 3200) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

export function openSheet(title, html) {
  $('sheet-title').textContent = title;
  $('sheet-body').innerHTML = html;
  $('sheet-body').scrollTop = 0;
  $('sheet').classList.add('open');
  return $('sheet-body');
}
export function closeSheet() { $('sheet').classList.remove('open'); }

export const fmt = {
  ft: m => `${Math.round(m * 3.28084).toLocaleString()} ft`,
  dist: m => (m < 1609.34 ? `${Math.round(m * 3.28084).toLocaleString()} ft` : `${(m / 1609.34).toFixed(2)} mi`),
  acres: m2 => `${(m2 / 4046.856).toFixed(2)} ac`,
  ll: (lon, lat) => `${lat.toFixed(5)}, ${lon.toFixed(5)}`,
  pct: x => `${Math.round(x * 100)}%`,
};

export function store(key, fallback) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
}
export function persist(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* storage unavailable */ }
}

export function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function pathDistance(cartos) {
  let d = 0;
  for (let i = 1; i < cartos.length; i++) {
    d += new Cesium.EllipsoidGeodesic(cartos[i - 1], cartos[i]).surfaceDistance;
  }
  return d;
}

// Horizontal stacked bar + legend rows from [{label, value, color}]
export function breakdown(rows, unitFn) {
  const total = rows.reduce((s, r) => s + r.value, 0) || 1;
  const bar = rows.map(r => `<span style="width:${(100 * r.value / total).toFixed(2)}%;background:${r.color}"></span>`).join('');
  const list = rows.map(r => `<tr><td><i class="sw" style="background:${r.color}"></i>${esc(r.label)}</td><td>${unitFn(r.value)}</td><td>${fmt.pct(r.value / total)}</td></tr>`).join('');
  return `<div class="stack">${bar}</div><table class="kv">${list}</table>`;
}

// ArcGIS JSON → GeoJSON. Esri outer rings are clockwise; holes attach to the preceding outer ring.
function ringSignedArea(r) {
  let a = 0;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) a += (r[i][0] - r[j][0]) * (r[i][1] + r[j][1]);
  return a / 2;
}
export function esriToGeoJSON(f) {
  const g = f.geometry;
  let geometry = null;
  if (g && g.rings) {
    const polys = [];
    for (const r of g.rings) {
      if (ringSignedArea(r) >= 0 || !polys.length) polys.push([r]);
      else polys[polys.length - 1].push(r);
    }
    geometry = polys.length === 1 ? { type: 'Polygon', coordinates: polys[0] } : { type: 'MultiPolygon', coordinates: polys };
  } else if (g && g.paths) {
    geometry = { type: 'MultiLineString', coordinates: g.paths };
  } else if (g && g.x != null) {
    geometry = { type: 'Point', coordinates: [g.x, g.y] };
  }
  return { type: 'Feature', properties: f.attributes || {}, geometry };
}

export async function queryLayer(layerUrl, params) {
  const j = await getJSON(`${layerUrl}/query?${qs({ f: 'json', outSR: 4326, ...params })}`);
  return (j.features || []).map(esriToGeoJSON).filter(f => f.geometry || params.returnGeometry === false);
}

export function polygonRings(geom) {
  if (!geom) return [];
  if (geom.type === 'Polygon') return geom.coordinates;
  if (geom.type === 'MultiPolygon') return geom.coordinates.flat();
  return [];
}

// Find a sublayer by name in an ArcGIS MapServer/FeatureServer.
export async function findSublayer(serviceUrl, re, fallbackId) {
  try {
    const j = await getJSON(`${serviceUrl}?f=json`);
    const l = (j.layers || []).find(x => re.test(x.name));
    if (l) return `${serviceUrl}/${l.id}`;
  } catch { /* fall through */ }
  return fallbackId == null ? null : `${serviceUrl}/${fallbackId}`;
}
