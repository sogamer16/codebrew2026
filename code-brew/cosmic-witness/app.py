"""
CosmicWitness / Sirius — Flask Backend
========================================
Star catalog priority (best match wins):

  1. HYG v3 local cache  — 120 k stars, instant, offline-friendly
  2. SIMBAD TAP range    — bright / named stars, 0-100 k ly
  3. Gaia DR3 TAP range  — 1.5 billion stars, sub-0.01 ly precision

All three are queried concurrently when needed; results are merged,
deduplicated by sky-position proximity, and sorted by distance accuracy.
"""

import os
import io
import json
import math
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
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
# Shared helpers
# ---------------------------------------------------------------------------

def _plx_range(target_ly: float, tolerance: float):
    """Return (plx_min, plx_max, plx_target) in milli-arcseconds."""
    # parallax_mas = 1000 / dist_pc  and  dist_pc = dist_ly / 3.26156
    # → parallax_mas = 3261.56 / dist_ly
    target_plx = 3261.56 / target_ly
    # A larger distance means a *smaller* parallax, so flip tolerance direction
    plx_min = 3261.56 / (target_ly * (1 + tolerance))
    plx_max = 3261.56 / (target_ly * (1 - tolerance))
    return plx_min, plx_max, target_plx


def _normalise_star(raw: dict) -> dict:
    """Ensure every star dict has the same keys regardless of source."""
    defaults = {
        "id": 0, "name": "Unknown", "has_proper_name": False,
        "ra": 0.0, "dec": 0.0, "dist_ly": 0.0,
        "magnitude": None, "spectral_type": "Unknown",
        "constellation": "Unknown", "naked_eye_visible": False,
        "year_watching": CURRENT_YEAR, "hip_id": None,
        "source": "HYG",
    }
    defaults.update(raw)
    return defaults


# ---------------------------------------------------------------------------
# SIMBAD TAP  (external catalog #1 — named / bright stars)
# ---------------------------------------------------------------------------
SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/tap/sync"


def simbad_lookup(star_name: str) -> dict:
    """Query SIMBAD TAP for extra info about a single named star."""
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


def query_simbad_range(target_ly: float, tolerance: float = 0.10, limit: int = 15) -> list[dict]:
    """
    Query SIMBAD TAP for stars whose parallax falls within ±tolerance of target_ly.
    Returns a list of normalised star dicts tagged with source="SIMBAD".
    """
    if target_ly <= 0 or target_ly > 100_000:
        return []

    plx_min, plx_max, target_plx = _plx_range(target_ly, tolerance)

    adql = (
        f"SELECT TOP {limit} "
        f"  main_id, ra, dec, plx_value, sp_type, flux "
        f"FROM basic "
        f"JOIN flux ON oidref = oid AND filter = 'V' "
        f"WHERE plx_value BETWEEN {plx_min:.6f} AND {plx_max:.6f} "
        f"  AND plx_value > 0 "
        f"ORDER BY ABS(plx_value - {target_plx:.6f}) ASC"
    )

    # Fallback without flux join if that fails
    adql_simple = (
        f"SELECT TOP {limit} "
        f"  main_id, ra, dec, plx_value, sp_type "
        f"FROM basic "
        f"WHERE plx_value BETWEEN {plx_min:.6f} AND {plx_max:.6f} "
        f"  AND plx_value > 0 "
        f"ORDER BY ABS(plx_value - {target_plx:.6f}) ASC"
    )

    stars = []
    for query in [adql_simple]:          # use simple query — flux join is unreliable
        try:
            resp = requests.get(
                SIMBAD_TAP,
                params={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": query},
                timeout=8,
            )
            data = resp.json()
            rows = data.get("data", [])
            cols = [c["name"] for c in data.get("metadata", [])]
            if not rows:
                continue

            for i, r in enumerate(rows):
                row = dict(zip(cols, r))
                plx = row.get("plx_value")
                if not plx or float(plx) <= 0:
                    continue
                dist = 3261.56 / float(plx)
                name = str(row.get("main_id", "")).strip() or f"SIMBAD-{i}"
                sp   = str(row.get("sp_type", "")).strip() or "Unknown"
                ra   = float(row.get("ra",  0) or 0)
                dec  = float(row.get("dec", 0) or 0)
                mag  = row.get("flux")
                if mag is not None:
                    try:
                        mag = float(mag)
                    except Exception:
                        mag = None

                stars.append(_normalise_star({
                    "id": abs(hash(name)) % 10_000_000,
                    "name": name,
                    "has_proper_name": True,
                    "ra": ra,
                    "dec": dec,
                    "dist_ly": round(dist, 4),
                    "magnitude": round(mag, 2) if mag is not None else None,
                    "spectral_type": sp,
                    "naked_eye_visible": bool(mag is not None and mag < 6.5),
                    "year_watching": int(CURRENT_YEAR - round(dist)),
                    "source": "SIMBAD",
                }))
            if stars:
                break
        except Exception as exc:
            print(f"⚠️  SIMBAD range query failed: {exc}")

    return stars


# ---------------------------------------------------------------------------
# Gaia DR3 TAP  (external catalog #2 — 1.5 billion stars, high precision)
# ---------------------------------------------------------------------------
GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"


def _bp_rp_to_spectral(bp_rp) -> str:
    """Convert Gaia BP-RP colour index to approximate spectral type."""
    try:
        v = float(bp_rp)
    except (TypeError, ValueError):
        return "Unknown"
    if v < -0.2: return "O"
    if v < 0.0:  return "B"
    if v < 0.3:  return "A"
    if v < 0.6:  return "F"
    if v < 0.8:  return "G"
    if v < 1.4:  return "K"
    return "M"


def query_gaia_range(target_ly: float, tolerance: float = 0.05, limit: int = 10) -> list[dict]:
    """
    Query Gaia DR3 via TAP for stars near target_ly.
    Uses parallax_error/parallax < 0.05 for high-precision results only.
    Returns normalised star dicts tagged with source="Gaia DR3".
    """
    # Gaia is most useful for nearby precise distances; beyond 50k ly parallaxes are noisy
    if target_ly <= 0 or target_ly > 50_000:
        return []

    plx_min, plx_max, target_plx = _plx_range(target_ly, tolerance)

    adql = (
        f"SELECT TOP {limit} "
        f"  source_id, ra, dec, parallax, parallax_error, "
        f"  phot_g_mean_mag, bp_rp "
        f"FROM gaiadr3.gaia_source "
        f"WHERE parallax BETWEEN {plx_min:.6f} AND {plx_max:.6f} "
        f"  AND parallax > 0 "
        f"  AND parallax_error / parallax < 0.05 "
        f"ORDER BY ABS(parallax - {target_plx:.6f}) ASC"
    )

    stars = []
    try:
        resp = requests.get(
            GAIA_TAP,
            params={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": adql},
            timeout=10,
        )
        data = resp.json()
        rows = data.get("data", [])
        cols = [c["name"] for c in data.get("metadata", [])]

        for r in rows:
            row = dict(zip(cols, r))
            plx = row.get("parallax")
            if not plx or float(plx) <= 0:
                continue
            dist = 3261.56 / float(plx)
            sid  = row.get("source_id", "?")
            ra   = float(row.get("ra",  0) or 0)
            dec  = float(row.get("dec", 0) or 0)
            mag  = row.get("phot_g_mean_mag")
            sp   = _bp_rp_to_spectral(row.get("bp_rp"))
            try:
                mag = float(mag) if mag is not None else None
            except Exception:
                mag = None

            stars.append(_normalise_star({
                "id": abs(int(sid)) % 10_000_000 if str(sid).lstrip("-").isdigit() else abs(hash(str(sid))) % 10_000_000,
                "name": f"Gaia DR3 {sid}",
                "has_proper_name": False,
                "ra": ra,
                "dec": dec,
                "dist_ly": round(dist, 4),
                "magnitude": round(mag, 2) if mag is not None else None,
                "spectral_type": sp,
                "naked_eye_visible": bool(mag is not None and mag < 6.5),
                "year_watching": int(CURRENT_YEAR - round(dist)),
                "source": "Gaia DR3",
            }))
    except Exception as exc:
        print(f"⚠️  Gaia DR3 query failed: {exc}")

    return stars


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _sky_dist_deg(ra1, dec1, ra2, dec2) -> float:
    """Great-circle angular separation in degrees (small-angle approximation is fine here)."""
    d_ra  = (ra1 - ra2) * math.cos(math.radians((dec1 + dec2) / 2))
    d_dec = dec1 - dec2
    return math.sqrt(d_ra ** 2 + d_dec ** 2)


def _deduplicate(stars: list[dict], sep_deg: float = 0.1) -> list[dict]:
    """
    Remove duplicates based on sky-position proximity.
    When two stars are within sep_deg of each other, keep the one with the
    best source priority: HYG (named) > SIMBAD > HYG (unnamed) > Gaia DR3.
    """
    source_priority = {"HYG": 0, "SIMBAD": 1, "Gaia DR3": 2}

    def priority(s):
        base = source_priority.get(s.get("source", "HYG"), 3)
        # named stars beat unnamed within same source
        return (base * 2) + (0 if s.get("has_proper_name") else 1)

    kept = []
    for star in stars:
        duplicate = False
        for i, k in enumerate(kept):
            sep = _sky_dist_deg(star["ra"], star["dec"], k["ra"], k["dec"])
            if sep < sep_deg:
                # Replace if new star has higher priority (lower number)
                if priority(star) < priority(k):
                    kept[i] = star
                duplicate = True
                break
        if not duplicate:
            kept.append(star)
    return kept


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    resp = send_from_directory("static", "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/status")
def status():
    df = load_star_data()
    return jsonify(
        {
            "status": "ok",
            "stars_loaded": len(df),
            "data_source": "HYG Database v3 (github.com/astronexus/HYG-Database)",
            "enrichment_api": "SIMBAD TAP (simbad.u-strasbg.fr)",
            "precision_api": "Gaia DR3 TAP (gea.esac.esa.int)",
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

    Returns up to 10 stars from three catalogs (HYG + SIMBAD + Gaia DR3),
    merged, deduplicated, and sorted by distance accuracy.
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

    # ------------------------------------------------------------------
    # Step 1: query HYG local catalog (always instant)
    # ------------------------------------------------------------------
    df = load_star_data()

    def hyg_search(tol):
        min_ly = max(0.0, light_years * (1 - tol))
        max_ly = light_years * (1 + tol)
        mask = (df["dist_ly"] >= min_ly) & (df["dist_ly"] <= max_ly)
        return df[mask].copy(), min_ly, max_ly

    subset, min_ly, max_ly = hyg_search(tolerance)

    # Widen HYG search if nothing found
    if len(subset) == 0:
        subset, min_ly, max_ly = hyg_search(0.5)
        tolerance = 0.5

    hyg_stars = []
    if len(subset) > 0:
        subset = subset.copy()
        subset["dist_diff"] = (subset["dist_ly"] - light_years).abs()

        named_mask = subset["proper"].notna() & (subset["proper"].str.strip() != "")
        named   = subset[named_mask].sort_values("dist_diff")
        unnamed = subset[~named_mask].sort_values("dist_diff")
        results = pd.concat([named.head(8), unnamed.head(2)]).head(10)

        for _, row in results.iterrows():
            proper = row.get("proper", "")
            has_name = pd.notna(proper) and str(proper).strip() != ""
            name = str(proper).strip() if has_name else f"HYG-{int(row['id'])}"
            hip  = row.get("hip")

            mag   = row.get("mag")   if pd.notna(row.get("mag",   None)) else row.get("magnitude")
            spect = row.get("spect") if pd.notna(row.get("spect", None)) else row.get("spectral_type", "")
            con   = row.get("con")   if pd.notna(row.get("con",   None)) else row.get("constellation", "")

            dist = float(row["dist_ly"])
            hyg_stars.append(_normalise_star({
                "id": int(row["id"]),
                "name": name,
                "has_proper_name": bool(has_name),
                "ra": float(row["ra"]),
                "dec": float(row["dec"]),
                "dist_ly": round(dist, 2),
                "magnitude": round(float(mag), 2) if mag is not None and pd.notna(mag) else None,
                "spectral_type": str(spect).strip() if spect and pd.notna(spect) else "Unknown",
                "constellation": str(con).strip() if con and pd.notna(con) else "Unknown",
                "naked_eye_visible": bool(mag is not None and pd.notna(mag) and float(mag) < 6.5),
                "year_watching": int(CURRENT_YEAR - round(dist)),
                "hip_id": int(hip) if pd.notna(hip) and float(hip) > 0 else None,
                "source": "HYG",
            }))

    # ------------------------------------------------------------------
    # Step 2: query SIMBAD and Gaia concurrently in a thread pool
    # Decide whether external queries are worth it:
    #   - Always query SIMBAD (fast, named stars)
    #   - Query Gaia only when best HYG match is >0.5 ly off OR target < 5000 ly
    # ------------------------------------------------------------------
    best_hyg_diff = min(
        (abs(s["dist_ly"] - light_years) for s in hyg_stars), default=9999
    )
    want_gaia = (light_years <= 50_000) and (
        best_hyg_diff > 0.5 or light_years < 5_000
    )

    external_stars: list[dict] = []
    ext_tolerance = max(tolerance, 0.10)   # external APIs get at least ±10 %

    futures = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures["simbad"] = pool.submit(query_simbad_range, light_years, ext_tolerance, 15)
        if want_gaia:
            futures["gaia"] = pool.submit(query_gaia_range, light_years, min(ext_tolerance, 0.05), 10)

        for key, fut in futures.items():
            try:
                external_stars.extend(fut.result(timeout=12))
            except Exception as exc:
                print(f"⚠️  {key} future failed: {exc}")

    # ------------------------------------------------------------------
    # Step 3: merge, deduplicate, sort
    # ------------------------------------------------------------------
    all_stars = hyg_stars + external_stars
    all_stars = _deduplicate(all_stars, sep_deg=0.1)

    # Sort: named first (within 1 ly of target), then by distance accuracy
    all_stars.sort(key=lambda s: (
        0 if (s["has_proper_name"] and abs(s["dist_ly"] - light_years) <= 1.0) else 1,
        abs(s["dist_ly"] - light_years)
    ))
    all_stars = all_stars[:10]

    if not all_stars:
        return jsonify(
            {
                "target_ly": light_years,
                "count": 0,
                "stars": [],
                "message": "No stars found at this distance. Try a different year.",
            }
        )

    return jsonify(
        {
            "target_ly": light_years,
            "tolerance": tolerance,
            "range_ly": [round(min_ly, 2), round(max_ly, 2)],
            "count": len(all_stars),
            "catalogs_used": list({s["source"] for s in all_stars}),
            "stars": all_stars,
        }
    )


@app.route("/api/star-detail/<star_name>")
def star_detail(star_name: str):
    """Enrich a named star with SIMBAD API data."""
    info = simbad_lookup(star_name)
    return jsonify(info)


@app.route("/api/search-by-name")
def search_by_name():
    """
    Search the full star catalog by name (case-insensitive, partial match).
    Query params:
      q  — the star name to search for
    Returns the best matching star (exact match preferred over partial).
    """
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"error": "Missing 'q' parameter"}), 400

    df = load_star_data()

    # Only look at named stars
    named = df[df["proper"].notna() & (df["proper"].str.strip() != "")].copy()
    named["proper_lower"] = named["proper"].str.lower().str.strip()

    # Exact match first
    exact = named[named["proper_lower"] == q]
    if len(exact) == 0:
        # Partial match
        exact = named[named["proper_lower"].str.contains(q, regex=False, na=False)]

    if len(exact) == 0:
        return jsonify({"found": False, "stars": []})

    # Pick the brightest / closest match
    exact = exact.copy()
    exact["_sort"] = exact.get("mag", exact.get("magnitude", pd.Series([99]*len(exact), index=exact.index))).fillna(99)
    exact = exact.sort_values("_sort")
    row = exact.iloc[0]

    proper = str(row.get("proper", "")).strip()
    dist = float(row.get("dist_ly", row.get("dist", 0) * 3.2616))
    mag = row.get("mag", row.get("magnitude"))
    spect = row.get("spect", row.get("spectral_type", ""))
    con = row.get("con", row.get("constellation", ""))
    hip = row.get("hip")

    star = _normalise_star({
        "id": int(row.get("id", 0)),
        "name": proper,
        "has_proper_name": True,
        "ra": float(row.get("ra", 0)),
        "dec": float(row.get("dec", 0)),
        "dist_ly": round(dist, 2),
        "magnitude": round(float(mag), 2) if mag is not None and pd.notna(mag) else None,
        "spectral_type": str(spect).strip() if spect and pd.notna(spect) else "Unknown",
        "constellation": str(con).strip() if con and pd.notna(con) else "Unknown",
        "naked_eye_visible": bool(mag is not None and pd.notna(mag) and float(mag) < 6.5),
        "year_watching": int(CURRENT_YEAR - round(dist)),
        "hip_id": int(hip) if pd.notna(hip) and float(hip) > 0 else None,
        "source": "HYG",
    })
    return jsonify({"found": True, "stars": [star]})


# ---------------------------------------------------------------------------
# Sky position — "Find It Tonight"
# ---------------------------------------------------------------------------

def _gmst(jd: float) -> float:
    """Greenwich Mean Sidereal Time in radians for a given Julian Date."""
    T = (jd - 2451545.0) / 36525.0
    gmst_deg = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
                + 0.000387933 * T * T - T * T * T / 38710000.0) % 360
    return math.radians(gmst_deg)

def _altaz(ra_deg: float, dec_deg: float, lat_deg: float, lon_deg: float,
           jd: float) -> tuple[float, float]:
    """Return (altitude_deg, azimuth_deg) for a star at given observer location/time."""
    ra  = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)

    lst  = (_gmst(jd) + lon) % (2 * math.pi)
    ha   = lst - ra                        # hour angle

    sin_alt = (math.sin(dec) * math.sin(lat)
               + math.cos(dec) * math.cos(lat) * math.cos(ha))
    alt = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))

    cos_az = ((math.sin(dec) - math.sin(lat) * sin_alt)
              / (math.cos(lat) * math.cos(math.radians(alt)) + 1e-10))
    az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
    if math.sin(ha) > 0:
        az = 360 - az

    return alt, az

def _compass(az: float) -> str:
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return dirs[round(az / 22.5) % 16]

def _jd_now() -> float:
    """Current Julian Date (UTC)."""
    import datetime
    now = datetime.datetime.utcnow()
    a = (14 - now.month) // 12
    y = now.year + 4800 - a
    m = now.month + 12 * a - 3
    jdn = (now.day + (153 * m + 2) // 5 + 365 * y
           + y // 4 - y // 100 + y // 400 - 32045)
    frac = (now.hour + now.minute / 60 + now.second / 3600) / 24 - 0.5
    return jdn + frac

@app.route("/api/sky-position")
def sky_position():
    """
    Return altitude/azimuth + visibility for a star at the user's location right now.
    Query params: ra (deg), dec (deg), lat (deg), lon (deg)
    Also sweeps tonight to find the best visibility window.
    """
    try:
        ra  = float(request.args["ra"])
        dec = float(request.args["dec"])
        lat = float(request.args.get("lat",  25.0))   # default Dubai
        lon = float(request.args.get("lon",  55.0))
    except (KeyError, ValueError):
        return jsonify({"error": "ra, dec required"}), 400

    jd_now = _jd_now()
    alt_now, az_now = _altaz(ra, dec, lat, lon, jd_now)

    # Sweep next 24 hours in 15-min steps to find peak altitude
    best_alt, best_az, best_jd = -90.0, 0.0, jd_now
    for step in range(96):
        jd_t = jd_now + step / (96)
        a, z = _altaz(ra, dec, lat, lon, jd_t)
        if a > best_alt:
            best_alt, best_az, best_jd = a, z, jd_t

    # Convert best_jd to UTC wall-clock
    import datetime
    jd_floor = int(best_jd + 0.5)
    frac     = (best_jd + 0.5) - jd_floor
    dt_base  = datetime.datetime(2000, 1, 1, 12) + datetime.timedelta(days=best_jd - 2451545.0)
    best_time_utc = dt_base.strftime("%H:%M UTC")

    visible_now = alt_now > 0
    above_horizon_pct = sum(
        1 for s in range(96)
        if _altaz(ra, dec, lat, lon, jd_now + s / 96)[0] > 0
    ) / 96 * 100

    return jsonify({
        "alt_now":    round(alt_now, 1),
        "az_now":     round(az_now, 1),
        "compass":    _compass(az_now),
        "visible_now": visible_now,
        "best_alt":   round(best_alt, 1),
        "best_az":    round(best_az, 1),
        "best_compass": _compass(best_az),
        "best_time_utc": best_time_utc,
        "above_horizon_pct": round(above_horizon_pct, 0),
    })


# ---------------------------------------------------------------------------
# Star Letters — time capsule messages on stars
# ---------------------------------------------------------------------------

import datetime as _dt

LETTERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "star_letters.json")

def _load_letters() -> dict:
    if os.path.exists(LETTERS_PATH):
        try:
            with open(LETTERS_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_letters(data: dict):
    with open(LETTERS_PATH, "w") as f:
        json.dump(data, f, indent=2)

@app.route("/api/letters/<star_id>", methods=["GET"])
def get_letters(star_id: str):
    letters = _load_letters()
    return jsonify(letters.get(star_id, []))

@app.route("/api/letters/<star_id>", methods=["POST"])
def post_letter(star_id: str):
    body = request.get_json(silent=True) or {}
    author  = str(body.get("author",  "Anonymous"))[:60]
    message = str(body.get("message", ""))[:1000]
    year    = str(body.get("year",    ""))[:20]

    if not message.strip():
        return jsonify({"error": "message required"}), 400

    letters = _load_letters()
    if star_id not in letters:
        letters[star_id] = []

    entry = {
        "id":      len(letters[star_id]),
        "author":  author,
        "message": message,
        "year":    year,
        "written": _dt.datetime.utcnow().strftime("%Y-%m-%d"),
    }
    letters[star_id].append(entry)
    _save_letters(letters)
    return jsonify({"ok": True, "total": len(letters[star_id])})


# ---------------------------------------------------------------------------
# Frame capture endpoint — for demo GIF assembly
# ---------------------------------------------------------------------------

FRAMES_DIR = "/sessions/great-dreamy-mccarthy/frames"

@app.route("/api/capture", methods=["POST"])
def capture_frame():
    """Accept a base64 PNG frame from the browser and save to disk."""
    import base64
    os.makedirs(FRAMES_DIR, exist_ok=True)
    body = request.get_json(silent=True) or {}
    data_url = body.get("dataUrl", "")
    label    = str(body.get("label", "frame"))[:40].replace(" ", "_")
    idx      = int(body.get("index", 0))
    # Strip data:image/png;base64, prefix
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    try:
        img_bytes = base64.b64decode(data_url)
        fname = os.path.join(FRAMES_DIR, f"{idx:03d}_{label}.png")
        with open(fname, "wb") as f:
            f.write(img_bytes)
        return jsonify({"ok": True, "file": fname})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    load_star_data()          # pre-load so first request is instant
    print("\n🚀  Sirius backend running at http://localhost:5000\n")
    print("📡  Catalogs: HYG v3 (local) + SIMBAD TAP + Gaia DR3 TAP\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
