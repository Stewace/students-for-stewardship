"""
NEON LiDAR Download — South Carolina Piedmont Sites
National Ecological Observatory Network

NEON has airborne LiDAR (1m resolution) at multiple SC/NC sites
including sites in the Piedmont region. Data is free and open.

Relevant NEON sites near the Piedmont SC project area:
  - TALL  — Talladega National Forest, AL (nearest NEON to Hunnicutt)
  - ORNL  — Oak Ridge National Lab, TN (TVA Piedmont)
  - SCBI  — Smithsonian Conservation Bio Institute, VA
  - SERC  — Smithsonian Environmental Research Center, MD
  - LENO  — Lenoir Landing, AL

For direct Piedmont SC data use USGS 3DEP (download_lidar.py) — NEON
sites do not currently cover Greenville/Pickens county directly.
NEON is best used for training data validation and model cross-checking.

Usage:
    # List available NEON sites and products
    python data/download_neon.py --list-sites

    # Download LiDAR for a specific site and year
    python data/download_neon.py --site TALL --year 2022

    # Download CHM (Canopy Height Model) + DTM for site
    python data/download_neon.py --site TALL --products DTM CHM --year 2022

NEON API docs: https://data.neonscience.org/data-api

No account required. Products are CC BY 4.0 licensed.
"""

import argparse
import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

NEON_API = "https://data.neonscience.org/api/v0"

# LiDAR-derived raster products
NEON_PRODUCTS = {
    "DTM":  "DP3.30024.001",   # Elevation - LiDAR (Digital Terrain Model)
    "DSM":  "DP3.30024.001",   # Same product, includes DSM
    "CHM":  "DP3.30015.001",   # Ecosystem structure (Canopy Height Model)
    "LPC":  "DP1.30003.001",   # Discrete return LiDAR point cloud
    "SLOPE": "DP3.30025.001",  # Slope and aspect
}

# Closest NEON sites to Piedmont SC
SITES_PIEDMONT_REGION = {
    "TALL": "Talladega National Forest, AL — closest to SC Piedmont",
    "ORNL": "Oak Ridge, TN — TVA Piedmont comparison site",
    "SCBI": "Front Royal, VA — Blue Ridge comparison site",
    "GRSM": "Great Smoky Mountains, TN — elevation gradient reference",
    "JERC": "Jones Ecological Research Center, GA — Coastal Plain (contrast)",
}


def list_available_sites():
    """Fetch and display NEON site list."""
    print("Fetching NEON site list...")
    url = f"{NEON_API}/sites"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        sites = data.get("data", [])
        print(f"\nTotal NEON sites: {len(sites)}")
        print("\nRelevant Piedmont/Southeast sites:")
        for code, desc in SITES_PIEDMONT_REGION.items():
            print(f"  {code:6s} — {desc}")
        print("\nAll sites:")
        for site in sorted(sites, key=lambda s: s.get("siteCode", "")):
            print(f"  {site.get('siteCode',''):6s} {site.get('siteName',''):40s} "
                  f"{site.get('siteType',''):20s} {site.get('stateCode','')}")
    except Exception as e:
        print(f"Error: {e}")


def list_available_data(site_code: str, product_code: str) -> list:
    """
    Query NEON API for available months of data for a site + product.
    """
    url = f"{NEON_API}/products/{product_code}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        site_data = data.get("data", {}).get("siteCodes", [])
        for site in site_data:
            if site.get("siteCode") == site_code:
                months = site.get("availableMonths", [])
                return months
    except Exception as e:
        print(f"Error querying NEON product {product_code}: {e}")
    return []


def download_neon_product(
    site_code: str,
    product_code: str,
    year: str,
    out_dir: Path,
    dry_run: bool = False,
) -> list:
    """
    Download NEON raster product for a site and year.
    """
    print(f"\nQuerying NEON: site={site_code}, product={product_code}, year={year}")

    # Find available months for this year
    months = list_available_data(site_code, product_code)
    target_months = [m for m in months if m.startswith(str(year))]

    if not target_months:
        print(f"  No data available for {site_code} {product_code} in {year}")
        print(f"  Available months: {months}")
        return []

    print(f"  Available in {year}: {target_months}")
    downloaded = []

    for month in target_months:
        # Get file URLs for this month
        url = f"{NEON_API}/data/{product_code}/{site_code}/{month}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                month_data = json.loads(resp.read().decode())
        except Exception as e:
            print(f"  Error getting file list for {month}: {e}")
            continue

        files = month_data.get("data", {}).get("files", [])
        # Filter for GeoTIFF files (DTM, CHM, etc.) — skip quality flags and metadata
        tif_files = [
            f for f in files
            if f.get("name", "").endswith(".tif") and
            not any(x in f.get("name", "") for x in ["browse", "kmz", "qa", "QA"])
        ]

        print(f"  {month}: {len(tif_files)} GeoTIFF files found")

        for f in tif_files:
            name = f.get("name", "unknown.tif")
            file_url = f.get("url", "")
            size_mb = f.get("size", 0) / 1e6

            if dry_run:
                print(f"    [dry-run] {name:60s} {size_mb:6.1f} MB")
                continue

            dest = out_dir / site_code / name
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists():
                print(f"    [skip] {name}")
                downloaded.append(str(dest))
                continue

            print(f"    Downloading {name} ({size_mb:.0f} MB)...")
            try:
                urllib.request.urlretrieve(file_url, str(dest))
                downloaded.append(str(dest))
                print(f"    ✓ {name}")
            except Exception as e:
                print(f"    ✗ Failed: {e}")

    return downloaded


def main():
    parser = argparse.ArgumentParser(
        description="Download NEON LiDAR data for Piedmont SC validation"
    )
    parser.add_argument("--list-sites", action="store_true",
                        help="List available NEON sites and exit")
    parser.add_argument("--site", type=str, default=None,
                        help="NEON site code (e.g. TALL, ORNL, SCBI)")
    parser.add_argument("--products", nargs="+",
                        choices=list(NEON_PRODUCTS.keys()),
                        default=["DTM"],
                        help="Products to download (default: DTM)")
    parser.add_argument("--year", type=str, default="2022",
                        help="Year of data collection (default: 2022)")
    parser.add_argument("--output", type=str, default="data/raw/neon",
                        help="Output directory (default: data/raw/neon)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List files without downloading")
    args = parser.parse_args()

    if args.list_sites:
        list_available_sites()
        return

    if not args.site:
        print("ERROR: --site required. Use --list-sites to see options.")
        print("Suggested sites for Piedmont SC comparison:")
        for code, desc in SITES_PIEDMONT_REGION.items():
            print(f"  {code:6s} — {desc}")
        return

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    for product_name in args.products:
        product_code = NEON_PRODUCTS[product_name]
        download_neon_product(
            site_code=args.site,
            product_code=product_code,
            year=args.year,
            out_dir=out_dir,
            dry_run=args.dry_run,
        )

    if not args.dry_run:
        print("\nDone. NEON DTM files can be used directly with terrain_analysis.py")
        print("Note: NEON data is already in UTM projection — no reprojection needed")


if __name__ == "__main__":
    main()
