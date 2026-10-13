# Land-app feature research (onX Hunt + land-development SaaS)

What the Pickens map at `docs/` copies, what it skips, and which public data services it depends on. We rebuild the features from public data; we don't use onX's or any vendor's proprietary data or APIs.

## onX Hunt features

| Feature | Status in our map |
|---|---|
| Private parcel boundaries + owner name | Built: county parcel layer, owner labels below ~2.5 km altitude |
| Public land by agency | Built: PAD-US overlay |
| Satellite / topo / hybrid basemaps | Built: Bing satellite and hybrid, USGS Topo, USGS Imagery+Topo, Esri Imagery |
| 3D terrain | Built: Cesium World Terrain with an exaggeration slider |
| Waypoints with notes | Built: pins (name and elevation), saved on the device |
| Distance line tool | Built |
| Area tool (acreage) | Built |
| GPS tracker | Built: records a track and saves it on the device |
| Live location | Built: GPS button |
| Share markups | Partial: shareable camera link; GPX/GeoJSON export and import |
| Offline maps | Not built (would need a service worker and a tile cache) |
| Wind / weather / sun and moon | Not built |
| Hunting units, cell coverage | Not applicable or no free source |

## SaaS features worth copying

- **Regrid:** parcel search by owner, TMS or address. *Built.* Standardized schema: we map county field names heuristically.
- **LandGlide:** "which parcel am I standing in" with an owner card. *Built* (GPS, then tap).
- **Land id:** contours, soils, flood and wetland overlays, measuring, 3D. *Built.*
- **Acres.com:** per-parcel percentages of soil, flood, wetland and slope. *Built* as the site report.
- **TerraFirma:** buildable-area screen (slope < 15%, outside the SFHA and wetlands). *Built* as a screening estimate.
  - No setbacks, easements or zoning yet.
- **LandVision:** drive-time rings. Not built; would need OpenRouteService (free key) or OSRM.
- **Acres.com and Regrid:** sale comparables. Not built; no free data source.
- **TerraFirma:** road frontage. Not built; the next step would be intersecting parcel edges with roads.

## Data services

None of these could be reached from the build sandbox: its network proxy blocks them, so no endpoint below was loaded live. Every consumer finds its layer ids at runtime and fails per layer, with a toast and a note in the Layers panel. **The first time the page runs on a phone or desktop, check the Layers panel for red "unavailable" notes.**

| Data | Endpoint | How it's used |
|---|---|---|
| Pickens parcels | ArcGIS Online web map item `558caa53cb1842f298a94983d6a14b9b` (county open data). The page reads the item's `operationalLayers` to find the layer titled *Parcels* | Vector `query` (`f=json`). Field names are guessed by regex, e.g. `OWNER*`, `TMS`/`PIN`, `ACRE*`, `SITUS*` |
| Pickens county boundary | Same web map, layer titled *County Boundary* | Masks the LEC grid. Falls back to a hand-drawn approximate outline |
| Parcel override | `?parcels=<FeatureServer/N url>` on the page URL | Use this if discovery picks the wrong layer |
| Terrain | Cesium ion asset 1 (World Terrain) | Rendering, LEC grid, profiles, site report |
| USGS Topo, Imagery+Topo, Hydro | `basemap.nationalmap.gov/arcgis/rest/services/*/MapServer/tile/{z}/{y}/{x}` | Basemaps and the streams overlay |
| Hillshade, slope | `elevation.nationalmap.gov/.../3DEPElevation/ImageServer/exportImage` with rendering rules `Hillshade Gray` and `Slope Map` | Overlays. The rule names are unverified |
| Contours | `carto.nationalmap.gov/arcgis/rest/services/contours/MapServer` | Overlay |
| FEMA NFHL | `hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`, layer *Flood Hazard Zones* (expected id 28) | Overlay, plus a query in the site report |
| NWI wetlands | `fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer` | Overlay, plus a query in the site report |
| SSURGO soils | WMS layer `mapunitpoly` at `SDMDataAccess.sc.egov.usda.gov/Spatial/SDM.wms`; SQL via `.../Tabular/post.rest` | Overlay, plus map units and acreage in the site report |
| PAD-US | `geo.dot.gov/server/rest/services/FLMA/PADUS/MapServer` (a DOT mirror) | Overlay |

If a service fails in the browser, the likely causes are:
- **CORS:** a missing `Access-Control-Allow-Origin` header. The SSURGO WMS is the most likely to have this problem.
- **Changed layer ids.**
- **Owner names not public:** if the county parcel layer has no owner field, owner data is probably only in qPublic, which has no API.

## Testing

`docs/` was smoke-tested in headless Chromium, with Cesium and turf served locally and terrain and ArcGIS responses mocked. The test covered:
- LEC compute
- Parcel identify
- Site report
- Search
- Area measure
- Elevation profile
- Pins with GPX export
- Layers panel

This exercises our own code paths, not the real services.
