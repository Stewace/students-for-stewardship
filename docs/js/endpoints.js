// Public data services. None of these could be verified from the build sandbox,
// so every consumer discovers layer ids at runtime and degrades per-layer.
export const CESIUM_ION_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI2YjVjM2Y1Ni1jMGI4LTQ3MjktYWY4My1iMTI3ZDQ2ZDIzN2YiLCJpZCI6NDAzMTA5LCJpYXQiOjE3NzM0MTAzNTd9.VidG6jNAvEQCUxzW6iPCk8Awlv8-Zwx-0c1XcYBBa-o';

export const PICKENS_MAP_ITEM = '558caa53cb1842f298a94983d6a14b9b';
export const PICKENS_MAP_DATA = `https://www.arcgis.com/sharing/rest/content/items/${PICKENS_MAP_ITEM}/data?f=json`;

export const USGS_BASEMAP = 'https://basemap.nationalmap.gov/arcgis/rest/services';
export const USGS_3DEP = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer';
export const USGS_CONTOURS = 'https://carto.nationalmap.gov/arcgis/rest/services/contours/MapServer';
export const ESRI_IMAGERY = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

export const FEMA_NFHL = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer';
export const NWI = 'https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer';
export const PADUS = 'https://geo.dot.gov/server/rest/services/FLMA/PADUS/MapServer';

export const SDA_WMS = 'https://SDMDataAccess.sc.egov.usda.gov/Spatial/SDM.wms';
export const SDA_REST = 'https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest';
