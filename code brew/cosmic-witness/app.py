"""
CosmicWitness - Flask Backend
==============================
Queries the HYG Star Database (downloaded from GitHub) to find stars
at a given light-year distance. Also enriches named stars with data
from the SIMBAD astronomical API.
"""

import os
import io
import json
import math
import requests
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static")
CORS(app)

# ---------------------------------------------------------------------------
# HYG Database
# ---------------------------------------------------------------------------
HYG_URL = (
    "https://raw.githubusercontent.com/astronexus/HYG-Database/"
    "master/hyg/v3/hyg_v3.csv"
)
CACHE_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hyg_cache.pkl")
BUNDLED_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bundled_stars.json")
CURRENT_YEAR  = 2026

_star_df: pd.DataFrame | None = None


def _load_bundled() -> pd.DataFrame:
    """Load the hand-curated fallback dataset of ~200 named stars."""
    with open(BUNDLED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df.rename(columns={"name": "proper"}, inplace=True)
    print(f"📦  Using bundled dataset ({len(df)} named stars).")
    return df


def load_star_data() -> pd.DataFrame:
    """
    Load the full HYG star catalog (120k stars) with automatic fallback to the
    bundled named-star dataset when the download is unavailable.

    Priority:
      1. In-memory cache (_star_df)
      2. Local pickle cache (hyg_cache.pkl) — from a previous run
      3. Download HYG v3 from GitHub
      4. Fallback: bundled_stars.json (works offline / in sandboxes)
    """
    global _star_df
    if _star_df is not None:
        return _star_df

    if os.path.exists(CACHE_PATH):
        print("⭐  Loading star catalog from local cache…")
        _star_df = pd.read_pickle(CACHE_PATH)
        print(f"    {len(_star_df):,} stars ready.")
        return _star_df

    print("🌌  Downloading HYG star catalog from GitHub (one-time, ~20 MB)…")
    try:
        resp = requests.get(HYG_URL, timeout=60)
        resp.raise_for_status()

        df = pd.read_csv(io.StringIO(resp.text))
        df = df[df["dist"] > 0].copy()
        df["dist_ly"] = df["dist"] * 3.2616

        keep = ["id", "hip", "proper", "ra", "dec", "dist_ly", "mag", "spect", "con"]
        keep = [c for c in keep if c in df.columns]
        df = df[keep].copy()

        df.to_pickle(CACHE_PATH)
        print(f"✅  Catalog cached. {len(df):,} stars loaded.")
        _star_df = df
        return _star_df

    except Exception as e:
        print(f"⚠️  HYG download failed ({e}). Falling back to bundled dataset.")
        _star_df = _load_bundled()
        return _star_df


# ---------------------------------------------------------------------------
# SIMBAD API helper  (the external "API" component)
# ---------------------------------------------------------------------------
SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/tap/sync"


def simbad_lookup(star_name: str) -> dict:
    """
    Query SIMBAD's TAP service for extra info about a named star.
    Returns a dict with keys: object_type, spectral_type, parallax, url
    Falls back gracefully if the request fails.
    """
    adql = f"""
        SELECT TOP 1
            main_id, otype_txt, sp_type, plx_value
        FROM basic
        WHERE main_id = '{star_name}'
           OR ids LIKE '%{star_name}%'
    """
    try:
        resp = requests.get(
            SIMBAD_TAP,
            params={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": adql},
            timeout=6,
        )
        data = resp.json()
        rows = data.get("data", [])
        cols = [c["name"] for c in data.get("metadata", [])]
        if rows:
            row = dict(zip(cols, rows[0]))
            return {
                "simbad_id": row.get("main_id", ""),
                "object_type": row.get("otype_txt", ""),
                "spectral_type": row.get("sp_type", ""),
                "parallax_mas": row.get("plx_value"),
                "simbad_url": f"https://simbad.u-strasbg.fr/simbad/sim-id?Ident={requests.utils.quote(star_name)}",
            }
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/status")
def status():
    df = load_star_data()
    return jsonify(
        {
            "status": "ok",
            "stars_loaded": len(df),
            "data_source": "HYG Database v3 (github.com/astronexus/HYG-Database)",
            "enrichment_api": "SIMBAD TAP (simbad.u-strasbg.fr)",
            "current_year": CURRENT_YEAR,
        }
    )


@app.route("/api/events")
def get_events():
    events_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.json")
    with open(events_path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/stars")
def get_stars():
    """
    Query parameters:
      light_years  – target distance in light-years (required)
      tolerance    – fractional search window, default 0.15 (±15 %)
    """
    try:
        light_years = float(request.args.get("light_years"))
    except (TypeError, ValueError):
        return jsonify({"error": "Missing or invalid 'light_years' parameter"}), 400

    if light_years <= 0:
        return jsonify({"error": "light_years must be positive"}), 400

    # Very large distances — beyond individual stars in HYG
    if light_years > 100_000:
        return jsonify(
            {
                "target_ly": light_years,
                "out_of_range": True,
                "message": (
                    f"At {light_years:,.0f} light-years, we're beyond individual stars "
                    "in our catalog. You're looking at distant galaxies and quasars — "
                    "objects like the Andromeda Galaxy (2.5 million ly) or the cosmic "
                    "microwave background (46 billion ly)."
                ),
                "stars": [],
            }
        )

    tolerance = float(request.args.get("tolerance", 0.15))

    df = load_star_data()

    def search(tol):
        min_ly = max(0.0, light_years * (1 - tol))
        max_ly = light_years * (1 + tol)
        mask = (df["dist_ly"] >= min_ly) & (df["dist_ly"] <= max_ly)
        return df[mask].copy(), min_ly, max_ly

    subset, min_ly, max_ly = search(tolerance)

    # Widen search if nothing found
    if len(subset) == 0:
        subset, min_ly, max_ly = search(0.5)
        tolerance = 0.5

    if len(subset) == 0:
        return jsonify(
            {
                "target_ly": light_years,
                "count": 0,
                "stars": [],
                "message": "No stars found at this distance. Try a different year.",
            }
        )

    subset = subset.copy()
    subset["dist_diff"] = (subset["dist_ly"] - light_years).abs()

    # Prioritise named stars, then sort by distance proximity
    named = subset[subset["proper"].notna() & (subset["proper"].str.strip() != "")]
    unnamed = subset[~subset.index.isin(named.index)]

    named = named.sort_values("dist_diff")
    unnamed = unnamed.sort_values("dist_diff")

    results = pd.concat([named.head(8), unnamed.head(2)]).head(10)

    stars = []
    for _, row in results.iterrows():
        proper = row.get("proper", "")
        has_name = pd.notna(proper) and str(proper).strip() != ""
        name = str(proper).strip() if has_name else f"HYG-{int(row['id'])}"
        hip = row.get("hip")

        # Support both HYG column names (mag/spect/con) and bundled names
        mag   = row.get("mag")   if pd.notna(row.get("mag",   None)) else row.get("magnitude")
        spect = row.get("spect") if pd.notna(row.get("spect", None)) else row.get("spectral_type", "")
        con   = row.get("con")   if pd.notna(row.get("con",   None)) else row.get("constellation", "")

        dist = float(row["dist_ly"])
        year_watching = CURRENT_YEAR - round(dist)

        stars.append(
            {
                "id": int(row["id"]),
                "name": name,
                "has_proper_name": bool(has_name),
                "ra": float(row["ra"]),    # hours (0–24)
                "dec": float(row["dec"]),  # degrees (-90 to +90)
                "dist_ly": round(dist, 2),
                "magnitude": round(float(mag), 2) if mag is not None and pd.notna(mag) else None,
                "spectral_type": str(spect).strip() if spect and pd.notna(spect) else "Unknown",
                "constellation": str(con).strip() if con and pd.notna(con) else "Unknown",
                "naked_eye_visible": bool(mag is not None and pd.notna(mag) and float(mag) < 6.5),
                "year_watching": int(year_watching),
                "hip_id": int(hip) if pd.notna(hip) and float(hip) > 0 else None,
            }
        )

    return jsonify(
        {
            "target_ly": light_years,
            "tolerance": tolerance,
            "range_ly": [round(min_ly, 2), round(max_ly, 2)],
            "count": len(stars),
            "stars": stars,
        }
    )


@app.route("/api/star-detail/<star_name>")
def star_detail(star_name: str):
    """Enrich a named star with SIMBAD API data."""
    info = simbad_lookup(star_name)
    return jsonify(info)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    load_star_data()          # pre-load so first request is instant
    print("\n🚀  CosmicWitness running at http://localhost:5000\n")
    app.run(debug=False, port=5000)
