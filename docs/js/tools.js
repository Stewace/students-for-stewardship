import { $, deg, esc, toast, openSheet, closeSheet, fmt, store, persist, download, pathDistance } from './util.js';

const C = Cesium;
const KEY = 'sfs.saved';
const COLORS = { line: '#4fc3f7', area: '#ff8a65', profile: '#ba68c8', track: '#ef5350', pin: '#ffeb3b' };

export function initTools(app) {
  const v = app.viewer;
  const savedDs = new C.CustomDataSource('saved');
  const drawDs = new C.CustomDataSource('draw');
  v.dataSources.add(savedDs);
  v.dataSources.add(drawDs);

  let saved = store(KEY, { pins: [], shapes: [], tracks: [] });
  const commit = () => { persist(KEY, saved); renderSaved(); };

  // ── Mode switching ────────────────────────────────────────────────────────
  const draw = { kind: null, pts: [] };

  function setMode(mode) {
    if (draw.kind && mode !== draw.kind) cancelDraw();
    app.mode = mode;
    document.querySelectorAll('#toolbar [data-mode]').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
    if (mode !== 'identify') closeSheet();
    if (['line', 'area', 'profile'].includes(mode)) startDraw(mode);
    if (mode === 'pin') toast('Tap the map to drop a pin');
  }

  document.querySelectorAll('#toolbar [data-mode]').forEach(b => b.onclick = () => setMode(b.dataset.mode));
  $('tb-track').onclick = toggleTrack;
  $('tb-saved').onclick = openSaved;

  // ── Drawing ───────────────────────────────────────────────────────────────
  const positions = () => draw.pts.map(c => C.Cartographic.toCartesian(c));
  const coords = () => draw.pts.map(c => [deg(c.longitude), deg(c.latitude)]);

  function startDraw(kind) {
    draw.kind = kind;
    draw.pts = [];
    drawDs.entities.removeAll();
    const color = C.Color.fromCssColorString(COLORS[kind]);
    drawDs.entities.add({
      polyline: {
        positions: new C.CallbackProperty(() => {
          const p = positions();
          return kind === 'area' && p.length > 2 ? [...p, p[0]] : p;
        }, false),
        width: 3, clampToGround: true, material: color,
      },
    });
    $('drawbar').hidden = false;
    $('draw-done').textContent = kind === 'profile' ? 'Profile' : 'Done';
    readout();
  }

  function readout() {
    const n = draw.pts.length;
    let txt = 'Tap the map to add points';
    if (draw.kind === 'area' && n >= 3) {
      const ring = [...coords(), coords()[0]];
      txt = `${fmt.acres(turf.area(turf.polygon([ring])))} · perimeter ${fmt.dist(pathDistance([...draw.pts, draw.pts[0]]))}`;
    } else if (n >= 2) {
      txt = fmt.dist(pathDistance(draw.pts));
    }
    $('draw-readout').textContent = txt;
  }

  function addPoint(carto) {
    draw.pts.push(C.Cartographic.clone(carto));
    // A dynamic polygon with <3 vertices is invalid, so add the fill only once it can exist.
    if (draw.kind === 'area' && draw.pts.length === 3 && !drawDs.entities.values.some(e => e.polygon)) {
      drawDs.entities.add({
        polygon: {
          hierarchy: new C.CallbackProperty(() => new C.PolygonHierarchy(positions()), false),
          material: C.Color.fromCssColorString(COLORS.area).withAlpha(0.25), classificationType: C.ClassificationType.TERRAIN,
        },
      });
    }
    drawDs.entities.add({
      position: C.Cartographic.toCartesian(carto),
      point: {
        pixelSize: 9, color: C.Color.WHITE, outlineColor: C.Color.fromCssColorString(COLORS[draw.kind]), outlineWidth: 2,
        heightReference: C.HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
    readout();
  }

  function cancelDraw() {
    draw.kind = null;
    draw.pts = [];
    drawDs.entities.removeAll();
    $('drawbar').hidden = true;
  }

  $('draw-undo').onclick = () => {
    if (!draw.pts.length) return;
    draw.pts.pop();
    const pts = drawDs.entities.values.filter(e => e.point);
    drawDs.entities.remove(pts[pts.length - 1]);
    if (draw.pts.length < 3) drawDs.entities.values.filter(e => e.polygon).forEach(e => drawDs.entities.remove(e));
    readout();
  };
  $('draw-cancel').onclick = () => setMode('identify');
  $('draw-done').onclick = async () => {
    const kind = draw.kind, pts = draw.pts.slice();
    if ((kind === 'area' && pts.length < 3) || pts.length < 2) { toast(kind === 'area' ? 'Need 3+ points' : 'Need 2+ points'); return; }
    if (kind === 'profile') { await showProfile(pts); return; }
    const name = prompt(`Save ${kind === 'area' ? 'area' : 'line'} as:`, `${kind === 'area' ? 'Area' : 'Line'} ${saved.shapes.length + 1}`);
    if (name !== null) {
      saved.shapes.push({ id: Date.now(), kind, name: name || 'Untitled', coords: pts.map(c => [deg(c.longitude), deg(c.latitude)]) });
      commit();
      toast('Saved');
    }
    setMode('identify');
  };

  // ── Elevation profile ─────────────────────────────────────────────────────
  async function showProfile(pts) {
    const total = pathDistance(pts);
    const N = 200;
    const samples = [];
    let acc = 0;
    for (let i = 1; i < pts.length; i++) {
      const g = new C.EllipsoidGeodesic(pts[i - 1], pts[i]);
      const segN = Math.max(2, Math.round(N * g.surfaceDistance / total));
      for (let k = 0; k < segN; k++) {
        const d = g.surfaceDistance * k / segN;
        samples.push({ d: acc + d, c: g.interpolateUsingSurfaceDistance(d) });
      }
      acc += g.surfaceDistance;
    }
    samples.push({ d: total, c: C.Cartographic.clone(pts[pts.length - 1]) });
    openSheet('Elevation profile', '<p class="muted">Sampling terrain…</p>');
    try {
      await C.sampleTerrainMostDetailed(app.terrain, samples.map(s => s.c));
    } catch (e) {
      openSheet('Elevation profile', `<p class="err">${esc(e.message)}</p>`);
      return;
    }
    const z = samples.map(s => s.c.height);
    let gain = 0, loss = 0, maxGrade = 0;
    for (let i = 1, j = 0; i < z.length; i++) {
      const dz = z[i] - z[i - 1];
      if (dz > 0) gain += dz; else loss -= dz;
      // Grade over a ≥30 m run so sample noise doesn't dominate
      while (j < i && samples[i].d - samples[j + 1].d >= 30) j++;
      const run = samples[i].d - samples[j].d;
      if (run >= 30) maxGrade = Math.max(maxGrade, Math.abs((z[i] - z[j]) / run));
    }
    const lo = Math.min(...z), hi = Math.max(...z);
    const W = 600, H = 200, P = 34;
    const x = d => P + (W - P - 8) * d / total;
    const y = h => H - 22 - (H - 34) * (h - lo) / Math.max(hi - lo, 1);
    const line = samples.map((s, i) => `${i ? 'L' : 'M'}${x(s.d).toFixed(1)},${y(z[i]).toFixed(1)}`).join('');
    const svg = `<svg class="profile" viewBox="0 0 ${W} ${H}">
      <path d="${line}L${x(total)},${H - 22}L${P},${H - 22}Z" class="fill"/><path d="${line}" class="ln"/>
      <text x="2" y="${y(hi) + 4}">${fmt.ft(hi)}</text><text x="2" y="${y(lo)}">${fmt.ft(lo)}</text>
      <text x="${P}" y="${H - 4}">0</text><text x="${W - 8}" y="${H - 4}" text-anchor="end">${fmt.dist(total)}</text></svg>`;
    openSheet('Elevation profile', `${svg}
      <table class="kv"><tr><td>Distance</td><td>${fmt.dist(total)}</td></tr>
      <tr><td>Climb / descent</td><td>+${fmt.ft(gain)} / −${fmt.ft(loss)}</td></tr>
      <tr><td>Low / high</td><td>${fmt.ft(lo)} / ${fmt.ft(hi)}</td></tr>
      <tr><td>Steepest grade</td><td>${Math.round(maxGrade * 100)}%</td></tr></table>`);
  }

  // ── Pins ──────────────────────────────────────────────────────────────────
  async function dropPin(carto) {
    const name = prompt('Pin name:', `Pin ${saved.pins.length + 1}`);
    if (name === null) return;
    const c = C.Cartographic.clone(carto);
    try { await C.sampleTerrainMostDetailed(app.terrain, [c]); } catch { /* elevation optional */ }
    saved.pins.push({ id: Date.now(), name: name || 'Pin', lon: deg(c.longitude), lat: deg(c.latitude), elev: c.height, ts: new Date().toISOString() });
    commit();
    setMode('identify');
  }

  // ── GPS: locate + track ───────────────────────────────────────────────────
  const gps = { watch: null, last: null, dot: null, track: null, flown: false };

  function ensureGps(onFix) {
    if (!navigator.geolocation) { toast('Location not available'); return; }
    if (gps.watch == null) {
      gps.watch = navigator.geolocation.watchPosition(p => {
        gps.last = p.coords;
        const pos = C.Cartesian3.fromDegrees(p.coords.longitude, p.coords.latitude);
        if (!gps.dot) {
          gps.dot = v.entities.add({
            position: pos,
            point: { pixelSize: 14, color: C.Color.fromCssColorString('#2196f3'), outlineColor: C.Color.WHITE, outlineWidth: 3, heightReference: C.HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: Number.POSITIVE_INFINITY },
          });
        } else gps.dot.position = pos;
        if (gps.track) recordTrackPoint(p.coords);
        if (gps.pendingFix) { const fn = gps.pendingFix; gps.pendingFix = null; fn(p.coords); }
      }, e => toast(`Location error: ${e.message}`), { enableHighAccuracy: true, maximumAge: 5000 });
    }
    if (onFix) { if (gps.last) onFix(gps.last); else gps.pendingFix = onFix; }
  }

  $('btn-locate').onclick = () => ensureGps(c => v.camera.flyTo({
    destination: C.Cartesian3.fromDegrees(c.longitude, c.latitude, 1500),
    orientation: { heading: v.camera.heading, pitch: C.Math.toRadians(-60), roll: 0 }, duration: 1.5,
  }));

  function recordTrackPoint(c) {
    const t = gps.track;
    const prev = t.pts[t.pts.length - 1];
    if (prev && C.Cartesian3.distance(C.Cartesian3.fromDegrees(prev[0], prev[1]), C.Cartesian3.fromDegrees(c.longitude, c.latitude)) < 4) return;
    t.pts.push([c.longitude, c.latitude, c.altitude ?? null, new Date().toISOString()]);
    $('tb-track').querySelector('span').textContent = fmt.dist(pathDistance(t.pts.map(p => C.Cartographic.fromDegrees(p[0], p[1]))));
  }

  function toggleTrack() {
    if (!gps.track) {
      gps.track = { pts: [], started: new Date().toISOString() };
      gps.trackEnt = v.entities.add({
        polyline: {
          positions: new C.CallbackProperty(() => gps.track ? gps.track.pts.map(p => C.Cartesian3.fromDegrees(p[0], p[1])) : [], false),
          width: 4, clampToGround: true, material: C.Color.fromCssColorString(COLORS.track),
        },
      });
      $('tb-track').classList.add('rec');
      ensureGps();
      toast('Recording track — keep this page open');
      return;
    }
    const t = gps.track;
    gps.track = null;
    v.entities.remove(gps.trackEnt);
    $('tb-track').classList.remove('rec');
    $('tb-track').querySelector('span').textContent = 'Track';
    if (t.pts.length < 2) { toast('Track too short — discarded'); return; }
    const name = prompt('Save track as:', `Track ${saved.tracks.length + 1}`);
    if (name === null) return;
    saved.tracks.push({ id: Date.now(), name: name || 'Track', started: t.started, pts: t.pts });
    commit();
  }

  // ── Saved items ───────────────────────────────────────────────────────────
  function renderSaved() {
    savedDs.entities.removeAll();
    const lbl = text => ({
      text, font: '600 12px sans-serif', fillColor: C.Color.WHITE, outlineColor: C.Color.BLACK, outlineWidth: 3,
      style: C.LabelStyle.FILL_AND_OUTLINE, pixelOffset: new C.Cartesian2(0, -18),
      heightReference: C.HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: Number.POSITIVE_INFINITY,
      distanceDisplayCondition: new C.DistanceDisplayCondition(0, 30000),
    });
    for (const p of saved.pins) {
      savedDs.entities.add({
        position: C.Cartesian3.fromDegrees(p.lon, p.lat),
        point: { pixelSize: 12, color: C.Color.fromCssColorString(COLORS.pin), outlineColor: C.Color.BLACK, outlineWidth: 2, heightReference: C.HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        label: lbl(p.name),
      });
    }
    for (const s of saved.shapes) {
      const pos = C.Cartesian3.fromDegreesArray(s.coords.flat());
      const color = C.Color.fromCssColorString(COLORS[s.kind]);
      savedDs.entities.add({ polyline: { positions: s.kind === 'area' ? [...pos, pos[0]] : pos, width: 3, clampToGround: true, material: color } });
      if (s.kind === 'area') {
        savedDs.entities.add({ polygon: { hierarchy: pos, material: color.withAlpha(0.18), classificationType: C.ClassificationType.TERRAIN } });
      }
    }
    for (const t of saved.tracks) {
      savedDs.entities.add({ polyline: { positions: C.Cartesian3.fromDegreesArray(t.pts.flatMap(p => [p[0], p[1]])), width: 3, clampToGround: true, material: C.Color.fromCssColorString(COLORS.track) } });
    }
  }

  function itemSummary(kind, it) {
    if (kind === 'pins') return `${fmt.ll(it.lon, it.lat)}${Number.isFinite(it.elev) ? ` · ${fmt.ft(it.elev)}` : ''}`;
    if (kind === 'tracks') return `${fmt.dist(pathDistance(it.pts.map(p => C.Cartographic.fromDegrees(p[0], p[1]))))} · ${new Date(it.started).toLocaleDateString()}`;
    const cs = it.coords.map(p => C.Cartographic.fromDegrees(p[0], p[1]));
    return it.kind === 'area' ? fmt.acres(turf.area(turf.polygon([[...it.coords, it.coords[0]]]))) : fmt.dist(pathDistance(cs));
  }

  function itemCoords(kind, it) {
    if (kind === 'pins') return [[it.lon, it.lat]];
    if (kind === 'tracks') return it.pts.map(p => [p[0], p[1]]);
    return it.coords;
  }

  function openSaved() {
    const sec = (kind, title) => saved[kind].length ? `<h3>${title}</h3><ul class="results">${saved[kind].map(it => `
      <li><button data-go="${kind}:${it.id}"><b>${esc(it.name)}</b><span>${itemSummary(kind, it)}</span></button>
      <button class="del" data-del="${kind}:${it.id}" aria-label="Delete">✕</button></li>`).join('')}</ul>` : '';
    const empty = !saved.pins.length && !saved.shapes.length && !saved.tracks.length;
    const body = openSheet('Saved', `${empty ? '<p class="muted">Nothing saved yet. Use Pin, Distance, Area or Track.</p>' : ''}
      ${sec('pins', 'Pins')}${sec('shapes', 'Lines & areas')}${sec('tracks', 'Tracks')}
      <div class="actions"><button id="ex-gpx">Export GPX</button><button id="ex-geojson">Export GeoJSON</button>
      <label class="btn">Import<input type="file" id="ex-import" accept=".geojson,.json" hidden></label></div>
      <p class="fine">Saved on this device only.</p>`);
    const find = key => { const [kind, id] = key.split(':'); return [kind, saved[kind].find(x => String(x.id) === id)]; };
    body.querySelectorAll('[data-go]').forEach(b => b.onclick = () => {
      const [kind, it] = find(b.dataset.go);
      const cs = itemCoords(kind, it);
      const lons = cs.map(c => c[0]), lats = cs.map(c => c[1]);
      const pad = 0.003;
      v.camera.flyTo({ destination: C.Rectangle.fromDegrees(Math.min(...lons) - pad, Math.min(...lats) - pad, Math.max(...lons) + pad, Math.max(...lats) + pad), duration: 1.5 });
      closeSheet();
    });
    body.querySelectorAll('[data-del]').forEach(b => b.onclick = () => {
      const [kind, it] = find(b.dataset.del);
      if (!confirm(`Delete “${it.name}”?`)) return;
      saved[kind] = saved[kind].filter(x => x !== it);
      commit(); openSaved();
    });
    $('ex-gpx').onclick = () => download('pickens-saved.gpx', toGPX(), 'application/gpx+xml');
    $('ex-geojson').onclick = () => download('pickens-saved.geojson', JSON.stringify(toGeoJSON(), null, 1), 'application/geo+json');
    $('ex-import').onchange = async e => {
      try { importGeoJSON(JSON.parse(await e.target.files[0].text())); openSaved(); } catch (err) { toast(`Import failed: ${err.message}`); }
    };
  }

  function toGeoJSON() {
    const F = (geometry, properties) => ({ type: 'Feature', geometry, properties });
    return {
      type: 'FeatureCollection',
      features: [
        ...saved.pins.map(p => F({ type: 'Point', coordinates: [p.lon, p.lat] }, { name: p.name, kind: 'pin', elev_m: p.elev, ts: p.ts })),
        ...saved.shapes.map(s => F(s.kind === 'area' ? { type: 'Polygon', coordinates: [[...s.coords, s.coords[0]]] } : { type: 'LineString', coordinates: s.coords }, { name: s.name, kind: s.kind })),
        ...saved.tracks.map(t => F({ type: 'LineString', coordinates: t.pts.map(p => [p[0], p[1]]) }, { name: t.name, kind: 'track', started: t.started })),
      ],
    };
  }

  function importGeoJSON(gj) {
    let n = 0;
    for (const f of gj.features || []) {
      const g = f.geometry, name = String(f.properties?.name || 'Imported');
      if (!g) continue;
      if (g.type === 'Point') saved.pins.push({ id: Date.now() + n, name, lon: g.coordinates[0], lat: g.coordinates[1], elev: f.properties?.elev_m ?? null, ts: new Date().toISOString() });
      else if (g.type === 'LineString') saved.shapes.push({ id: Date.now() + n, kind: 'line', name, coords: g.coordinates.map(c => [c[0], c[1]]) });
      else if (g.type === 'Polygon') saved.shapes.push({ id: Date.now() + n, kind: 'area', name, coords: g.coordinates[0].slice(0, -1).map(c => [c[0], c[1]]) });
      else continue;
      n++;
    }
    commit();
    toast(`Imported ${n} item${n === 1 ? '' : 's'}`);
  }

  function toGPX() {
    const x = s => esc(s);
    const wpts = saved.pins.map(p => `<wpt lat="${p.lat}" lon="${p.lon}">${Number.isFinite(p.elev) ? `<ele>${p.elev.toFixed(1)}</ele>` : ''}<name>${x(p.name)}</name></wpt>`);
    const trks = saved.tracks.map(t => `<trk><name>${x(t.name)}</name><trkseg>${t.pts.map(p => `<trkpt lat="${p[1]}" lon="${p[0]}">${p[2] != null ? `<ele>${p[2]}</ele>` : ''}<time>${p[3]}</time></trkpt>`).join('')}</trkseg></trk>`);
    const rtes = saved.shapes.map(s => `<rte><name>${x(s.name)}</name>${[...s.coords, ...(s.kind === 'area' ? [s.coords[0]] : [])].map(c => `<rtept lat="${c[1]}" lon="${c[0]}"/>`).join('')}</rte>`);
    return `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Students for Stewardship" xmlns="http://www.topografix.com/GPX/1/1">\n${[...wpts, ...rtes, ...trks].join('\n')}\n</gpx>`;
  }

  // ── Shareable camera link ─────────────────────────────────────────────────
  function writeHash() {
    const c = v.camera.positionCartographic;
    const h = `#@${deg(c.longitude).toFixed(5)},${deg(c.latitude).toFixed(5)},${Math.round(c.height)},${Math.round(deg(v.camera.heading))},${Math.round(deg(v.camera.pitch))}`;
    history.replaceState(null, '', h);
  }
  v.camera.moveEnd.addEventListener(writeHash);
  $('btn-share').onclick = async () => {
    writeHash();
    try { await navigator.clipboard.writeText(location.href); toast('Link copied'); } catch { prompt('Copy this link:', location.href); }
  };

  app.handlers.line = app.handlers.area = app.handlers.profile = addPoint;
  app.handlers.pin = dropPin;
  renderSaved();
  return { setMode };
}

export function readHashView() {
  const m = location.hash.match(/^#@(-?[\d.]+),(-?[\d.]+),(\d+),(-?\d+),(-?\d+)/);
  if (!m) return null;
  const [lon, lat, h, heading, pitch] = m.slice(1).map(Number);
  return { lon, lat, h, heading, pitch };
}
