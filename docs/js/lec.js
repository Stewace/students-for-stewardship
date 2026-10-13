import { $ } from './util.js';

export const LON_MIN = -83.00, LON_MAX = -82.35;
export const LAT_MIN = 34.67, LAT_MAX = 35.22;
export const GRES = 0.002; // ~220 m
export const GCOLS = Math.round((LON_MAX - LON_MIN) / GRES);
export const GROWS = Math.round((LAT_MAX - LAT_MIN) / GRES);

export const LEC_COLORS = {
  1: [198, 40, 40, 215],
  2: [245, 127, 23, 215],
  3: [85, 139, 47, 215],
  4: [21, 101, 192, 215],
  5: [0, 105, 92, 220],
  6: [158, 158, 158, 170],
};
export const LEC_NAMES = {
  1: 'Xeric Ridge', 2: 'Dry-Mesic Slope', 3: 'Mesic Slope',
  4: 'Cove / Hollow', 5: 'Bottomland', 6: 'Upland Flat',
};
export const lecCss = k => `rgb(${LEC_COLORS[k].slice(0, 3).join(',')})`;

let lecGrid = null;

export function lecAt(lon, lat) {
  if (!lecGrid) return null;
  const c = Math.floor((lon - LON_MIN) / GRES);
  const r = Math.floor((LAT_MAX - lat) / GRES);
  if (c < 0 || r < 0 || c >= GCOLS || r >= GROWS) return null;
  return lecGrid[r * GCOLS + c] || null;
}

function pctRank(arr) {
  const n = arr.length;
  const idx = Array.from({ length: n }, (_, i) => i).sort((a, b) => arr[a] - arr[b]);
  const rank = new Float32Array(n);
  for (let i = 0; i < n; i++) rank[idx[i]] = i / Math.max(n - 1, 1);
  return rank;
}

// Percentile thresholds make this scale-invariant: classes are relative landscape position within the county.
function classify(elev, slope, aspect, tsi, twi) {
  const sp = pctRank(slope), tp = pctRank(tsi), wp = pctRank(twi), ep = pctRank(elev);
  const fa = aspect.map(a => Math.abs(180 - Math.abs(a - 225)));
  const fp = pctRank(fa);
  const out = new Uint8Array(elev.length).fill(6);
  for (let i = 0; i < out.length; i++) {
    if (sp[i] > 0.35 && sp[i] < 0.80 && tp[i] > 0.35 && fp[i] > 0.50) out[i] = 3;
    if (sp[i] > 0.40 && sp[i] < 0.82 && tp[i] > 0.18 && tp[i] < 0.55 && fp[i] < 0.50) out[i] = 2;
    if (tp[i] > 0.65 && wp[i] > 0.55 && sp[i] > 0.12 && sp[i] < 0.78) out[i] = 4;
    if (wp[i] > 0.93 && sp[i] < 0.18) out[i] = 5;
    if (sp[i] > 0.74 && tp[i] < 0.28 && ep[i] > 0.58) out[i] = 1;
  }
  return out;
}

function setStatus(msg, pct) {
  $('lec-status').textContent = msg;
  $('lec-bar').style.width = `${pct}%`;
}

export async function computeLEC(app, insideFn) {
  const N = GROWS * GCOLS;
  setStatus('LEC: sampling terrain…', 3);

  const positions = new Array(N);
  for (let r = 0; r < GROWS; r++) {
    for (let c = 0; c < GCOLS; c++) {
      positions[r * GCOLS + c] = Cesium.Cartographic.fromDegrees(LON_MIN + (c + 0.5) * GRES, LAT_MAX - (r + 0.5) * GRES);
    }
  }

  const BATCH = 4000;
  for (let s = 0; s < N; s += BATCH) {
    await Cesium.sampleTerrain(app.terrain, 12, positions.slice(s, s + BATCH));
    setStatus(`LEC: terrain ${Math.min(s + BATCH, N).toLocaleString()} / ${N.toLocaleString()}`, 3 + 77 * Math.min(s + BATCH, N) / N);
  }

  setStatus('LEC: terrain indices…', 82);
  const elev = new Float32Array(N), slope = new Float32Array(N), aspect = new Float32Array(N);
  const tsi = new Float32Array(N), twi = new Float32Array(N);
  for (let i = 0; i < N; i++) elev[i] = Number.isFinite(positions[i].height) ? positions[i].height : 0;

  const midLat = (LAT_MIN + LAT_MAX) / 2;
  const dx = GRES * 111320 * Math.cos(midLat * Math.PI / 180);
  const dy = GRES * 110950;
  const E = (r, c) => elev[r * GCOLS + c];

  for (let r = 1; r < GROWS - 1; r++) {
    for (let c = 1; c < GCOLS - 1; c++) {
      const i = r * GCOLS + c;
      // Horn (1981); rows run north→south so +r is south
      const gx = ((E(r - 1, c + 1) + 2 * E(r, c + 1) + E(r + 1, c + 1)) - (E(r - 1, c - 1) + 2 * E(r, c - 1) + E(r + 1, c - 1))) / (8 * dx);
      const gy = ((E(r - 1, c - 1) + 2 * E(r - 1, c) + E(r - 1, c + 1)) - (E(r + 1, c - 1) + 2 * E(r + 1, c) + E(r + 1, c + 1))) / (8 * dy);
      slope[i] = Math.hypot(gx, gy);
      aspect[i] = (Math.atan2(-gx, -gy) * 180 / Math.PI + 360) % 360;
      tsi[i] = (E(r - 1, c - 1) + E(r - 1, c) + E(r - 1, c + 1) + E(r, c - 1) + E(r, c + 1) + E(r + 1, c - 1) + E(r + 1, c) + E(r + 1, c + 1)) / 8 - elev[i];
    }
  }

  const WIN = 3;
  for (let r = WIN; r < GROWS - WIN; r++) {
    for (let c = WIN; c < GCOLS - WIN; c++) {
      const i = r * GCOLS + c;
      let sum = 0;
      for (let a = -WIN; a <= WIN; a++) for (let b = -WIN; b <= WIN; b++) sum += E(r + a, c + b);
      const depression = Math.max(sum / ((2 * WIN + 1) ** 2) - elev[i], 0);
      twi[i] = Math.log((dx * (1 + depression * 0.4)) / Math.max(slope[i], 0.0087));
    }
  }

  setStatus('LEC: classifying…', 90);
  const inside = [];
  for (let r = 0; r < GROWS; r++) {
    for (let c = 0; c < GCOLS; c++) {
      if (insideFn(LON_MIN + (c + 0.5) * GRES, LAT_MAX - (r + 0.5) * GRES)) inside.push(r * GCOLS + c);
    }
  }
  const pick = arr => Float32Array.from(inside, i => arr[i]);
  const cls = classify(pick(elev), pick(slope), pick(aspect), pick(tsi), pick(twi));
  lecGrid = new Uint8Array(N);
  inside.forEach((i, k) => { lecGrid[i] = cls[k]; });

  setStatus('LEC: rendering…', 96);
  const canvas = Object.assign(document.createElement('canvas'), { width: GCOLS, height: GROWS });
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(GCOLS, GROWS);
  for (let i = 0; i < N; i++) {
    const col = LEC_COLORS[lecGrid[i]];
    if (col) img.data.set(col, i * 4);
  }
  ctx.putImageData(img, 0, 0);

  const provider = await Cesium.SingleTileImageryProvider.fromUrl(canvas.toDataURL('image/png'), {
    rectangle: Cesium.Rectangle.fromDegrees(LON_MIN, LAT_MIN, LON_MAX, LAT_MAX),
  });
  setStatus('LEC ready', 100);
  setTimeout(() => $('lec-chip').classList.add('done'), 800);
  return new Cesium.ImageryLayer(provider, { magnificationFilter: Cesium.TextureMagnificationFilter.NEAREST });
}
