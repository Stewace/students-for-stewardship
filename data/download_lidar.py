"""
LiDAR / DEM Download Script — South Carolina (+ optional NC)
Piedmont Ecosystem Classification Project

Downloads from USGS 3DEP (The National Map) via TNM Access API.
No account required. All data is public domain.

Usage:
    # Download 1/3 arc-second DEM for entire SC (recommended starting point)
    python data/download_lidar.py --state SC --resolution 13

    # Download 1-meter LiDAR-derived DEM for study area only (Hunnicutt Creek)
    python data/download_lidar.py --bbox -82.6,34.7,-82.1,35.1 --resolution 1

    # Download full 1m DEM tiles for SC Upstate (faster than whole state)
    python data/download_lidar.py --bbox -83.4,34.5,-81.5,35.2 --resolution 1

    # Download point cloud (LAZ) for study area — LARGE FILES, use small bbox
    python data/download_lidar.py --bbox -82.6,34.7,-82.1,35.1 --type lidar

    # Download both SC and NC
    python data/download_lidar.py --state SC NC --resolution 13

Options:
    --state       SC, NC, or both (downloads by state boundary)
    --bbox        west,south,east,north (decimal degrees) — overrides --state
    --resolution  1 (1-meter), 13 (1/3 arc-second ~10m), 1 (1 arc-second ~30m)
    --type        dem (default) or lidar (LAZ point clouds — very large)
    --output      Output directory (default: data/raw/dem/ or data/raw/lidar/)
    --dry-run     List files that would be downloaded without downloading
    --max         Max number of tiles to download (default: all)
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

# ---------------------------------------------------------------------------
# USGS State bounding boxes
# ---------------------------------------------------------------------------

STATE_BBOX = {
    "SC": (-83.36, 32.03, -78.54, 35.22),   # west, south, east, north
    "NC": (-84.33, 33.83, -75.46, 36.59),
}

# ---------------------------------------------------------------------------
# USGS TNM API dataset names
# ---------------------------------------------------------------------------

TNM_DATASETS = {
    "1":  "Digital Elevation Model (DEM) 1 meter",
    "13": "National Elevation Dataset (NED) 1/3 arc-second",
    "1s": "National Elevation Dataset (NED) 1 arc-second",
    "lidar": "Lidar Point Cloud (LPC)",
}

TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"

# ---------------------------------------------------------------------------
# Query TNM API
# ---------------------------------------------------------------------------

def query_tnm(
    bbox: tuple,
    dataset_key: str,
    max_results: int = 500,
) -> list:
    """
    Query USGS The National Map API for available products.

    Parameters
    ----------
    bbox : (west, south, east, north) in decimal degrees
    dataset_key : key into TNM_DATASETS dict

    Returns
    -------
    list of product dicts with downloadURL, title, size, etc.
    """
    dataset_name = TNM_DATASETS[dataset_key]
    west, south, east, north = bbox
    bbox_str = f"{west},{south},{east},{north}"

    params = {
        "datasets": dataset_name,
        "bbox": bbox_str,
        "outputFormat": "json",
        "max": max_results,
    }

    url = TNM_API + "?" + urllib.parse.urlencode(params)
    print(f"  Querying: {url}")

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"  ERROR querying TNM API: {e}")
        return []

    items = data.get("items", [])
    total = data.get("total", 0)

    print(f"  Found {total} products ({len(items)} returned)")
    return items


# ---------------------------------------------------------------------------
# Download a single file with progress
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path, retries: int = 3) -> bool:
    """
    Download a file with retry logic and progress display.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        print(f"  [skip] {dest.name} already exists")
        return True

    for attempt in range(1, retries + 1):
        try:
            print(f"  Downloading {dest.name} ... ", end="", flush=True)
            start = time.time()

            def reporthook(count, block_size, total_size):
                if total_size > 0:
                    pct = min(100, int(count * block_size * 100 / total_size))
                    mb = count * block_size / 1e6
                    print(f"\r  Downloading {dest.name} ... {pct}% ({mb:.1f} MB)",
                          end="", flush=True)

            urllib.request.urlretrieve(url, str(dest), reporthook=reporthook)
            elapsed = time.time() - start
            size_mb = dest.stat().st_size / 1e6
            print(f"\r  {dest.name} — {size_mb:.1f} MB in {elapsed:.1f}s")
            return True

        except Exception as e:
            print(f"\n  Attempt {attempt} failed: {e}")
            if dest.exists():
                dest.unlink()
            if attempt < retries:
                wait = 2 ** attempt
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)

    print(f"  FAILED after {retries} attempts: {dest.name}")
    return False


# ---------------------------------------------------------------------------
# Main download logic
# ---------------------------------------------------------------------------

def download_elevation(
    bbox: tuple,
    resolution: str,
    output_dir: Path,
    dry_run: bool = False,
    max_tiles: int = None,
) -> list:
    """
    Download DEM tiles for a bounding box.

    Returns list of downloaded file paths.
    """
    print(f"\nQuerying USGS 3DEP for {TNM_DATASETS[resolution]}...")
    print(f"Bounding box: {bbox}")

    items = query_tnm(bbox, resolution)
    if not items:
        print("No products found.")
        return []

    if max_tiles:
        items = items[:max_tiles]
        print(f"Limiting to {max_tiles} tiles")

    # Show what we found
    total_size_mb = sum(item.get("sizeInBytes", 0) for item in items) / 1e6
    print(f"\n{len(items)} tiles to download — estimated total: {total_size_mb:.0f} MB")
    print()

    if dry_run:
        for item in items:
            size = item.get("sizeInBytes", 0) / 1e6
            print(f"  [dry-run] {item.get('title','?'):60s} {size:6.1f} MB")
            print(f"            {item.get('downloadURL','')}")
        return []

    # Download
    downloaded = []
    failed = []

    for i, item in enumerate(items, 1):
        url = item.get("downloadURL")
        title = item.get("title", "unknown")
        size_mb = item.get("sizeInBytes", 0) / 1e6

        if not url:
            print(f"  [{i}/{len(items)}] No URL for: {title}")
            continue

        # Build filename from URL or title
        filename = url.split("/")[-1].split("?")[0]
        if not filename.endswith((".tif", ".zip", ".laz", ".las")):
            filename = title.replace(" ", "_").replace("/", "-") + ".tif"

        dest = output_dir / filename
        print(f"[{i}/{len(items)}] {title} ({size_mb:.0f} MB)")

        if download_file(url, dest):
            downloaded.append(str(dest))
        else:
            failed.append(title)

    print(f"\nDownloaded: {len(downloaded)} files")
    if failed:
        print(f"Failed: {len(failed)} files")
        for f in failed:
            print(f"  - {f}")

    return downloaded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download USGS 3DEP LiDAR/DEM data for South Carolina"
    )
    parser.add_argument(
        "--state", nargs="+", choices=["SC", "NC"], default=["SC"],
        help="State(s) to download (default: SC)"
    )
    parser.add_argument(
        "--bbox", type=str, default=None,
        help="Custom bbox: west,south,east,north (overrides --state)"
    )
    parser.add_argument(
        "--resolution", choices=["1", "13", "1s"], default="13",
        help="DEM resolution: 1=1-meter, 13=1/3 arc-second 10m (default), 1s=1 arc-second 30m"
    )
    parser.add_argument(
        "--type", choices=["dem", "lidar"], default="dem",
        help="Download DEM rasters (default) or raw LiDAR point clouds (large)"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory (default: data/raw/dem/ or data/raw/lidar/)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List files without downloading"
    )
    parser.add_argument(
        "--max", type=int, default=None,
        help="Maximum number of tiles to download"
    )
    args = parser.parse_args()

    # Determine download type and resolution key
    if args.type == "lidar":
        resolution_key = "lidar"
    else:
        resolution_key = args.resolution

    # Determine output directory
    if args.output:
        out_dir = Path(args.output)
    else:
        out_dir = Path("data/raw/lidar" if args.type == "lidar" else "data/raw/dem")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve bounding box
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        if len(parts) != 4:
            print("ERROR: --bbox must be west,south,east,north")
            sys.exit(1)
        bbox = tuple(parts)
        print(f"\nUsing custom bbox: {bbox}")
        download_elevation(bbox, resolution_key, out_dir, args.dry_run, args.max)
    else:
        for state in args.state:
            bbox = STATE_BBOX[state]
            print(f"\n{'='*60}")
            print(f"State: {state}")
            print(f"{'='*60}")
            download_elevation(bbox, resolution_key, out_dir, args.dry_run, args.max)

    print("\nDone. Next steps:")
    print("  1. Reproject to UTM Zone 17N (EPSG:26917):")
    print("     gdalwarp -t_srs EPSG:26917 -tr 10 10 -r bilinear input.tif output_utm.tif")
    print("  2. Run terrain analysis:")
    print("     python map-system/stack/python/terrain_analysis.py --dem data/processed/dem/dem_utm.tif --output data/processed/terrain/")
    print("  3. Run full pipeline:")
    print("     python run_pipeline.py --dem data/processed/dem/dem_1m_utm.tif")


if __name__ == "__main__":
    main()
