#!/usr/bin/env bash
# BM-2 — Download, crop and freeze the Copernicus GLO-30 tile covering Interlagos.
# Source: AWS Open Data, bucket copernicus-dem-30m (public, no AWS account needed).
# Tile names refer to the SOUTH-WEST corner: S24/W047 covers lat [-24,-23], lon [-47,-46]; Interlagos is at ~(-23.70, -46.70).
# Requirements: aws CLI (or curl), GDAL (gdal_translate, gdalinfo), sha256sum (macOS: shasum -a 256).
set -euo pipefail

TILE="Copernicus_DSM_COG_10_S24_00_W047_00_DEM"
OUT="data/external/terrain"
# Crop window (ulx uly lrx lry) — Interlagos area + margin; must contain RoI ⊕ R_max (see tools/make_roi.py report).
PROJWIN="-46.80 -23.60 -46.60 -23.80"

mkdir -p "$OUT"

echo "1) Confirm the tile is in the public list and inspect the folder"
aws s3 ls --no-sign-request "s3://copernicus-dem-30m/${TILE}/"
aws s3 cp --no-sign-request s3://copernicus-dem-30m/tileList.txt "$OUT/tileList.txt"
grep -q "$TILE" "$OUT/tileList.txt" && echo "   tile listed: OK"

echo "2) Download the full tile (kept out of git; only its hash is versioned)"
aws s3 cp --no-sign-request "s3://copernicus-dem-30m/${TILE}/${TILE}.tif" "$OUT/${TILE}.tif"
# Alternative without the AWS CLI:
# curl -fL -o "$OUT/${TILE}.tif" "https://copernicus-dem-30m.s3.amazonaws.com/${TILE}/${TILE}.tif"

echo "3) Crop to the study window (this file IS versioned)"
gdal_translate -projwin $PROJWIN -of GTiff -co COMPRESS=DEFLATE \
  "$OUT/${TILE}.tif" "$OUT/glo30_interlagos_crop.tif"

echo "4) Record metadata: CRS, vertical datum, nodata, size"
gdalinfo "$OUT/${TILE}.tif"            > "$OUT/gdalinfo_full.txt"
gdalinfo -stats "$OUT/glo30_interlagos_crop.tif" > "$OUT/gdalinfo_crop.txt"
echo "   -> open gdalinfo_full.txt and copy the vertical datum line into terrain.yaml (do NOT assume EGM2008)"

echo "5) Hashes"
( cd "$OUT" && sha256sum "${TILE}.tif" glo30_interlagos_crop.tif tileList.txt > SHA256SUMS )
cat "$OUT/SHA256SUMS"

cat > "$OUT/terrain.yaml" <<YAML
# Frozen terrain source (BM-2). Fill the ⚠ fields from gdalinfo_full.txt and the product handbook.
dem: copernicus_glo30
type: DSM            # includes buildings and vegetation (declared limitation)
release: "Copernicus DEM 2021 release (per AWS Open Data registry page)"
bucket: s3://copernicus-dem-30m
key: ${TILE}/${TILE}.tif
accessed: $(date -u +%Y-%m-%d)
licence: "Copernicus DEM licence (see dataspace.copernicus.eu)"
horizontal_crs: ⚠ from gdalinfo
vertical_datum: ⚠ from gdalinfo / product handbook (expected EGM2008 — confirm)
crop_projwin: "$PROJWIN"
sha256_full: $(cut -d' ' -f1 < <(grep "${TILE}.tif" "$OUT/SHA256SUMS"))
sha256_crop: $(cut -d' ' -f1 < <(grep glo30_interlagos_crop.tif "$OUT/SHA256SUMS"))
YAML
echo "Done. Commit: terrain.yaml, SHA256SUMS, glo30_interlagos_crop.tif, gdalinfo_*.txt. Add the full tile to .gitignore."
