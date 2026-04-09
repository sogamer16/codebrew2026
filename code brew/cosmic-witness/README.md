# CosmicWitness 🌌
### *The night sky is a time machine*

Built for **Codebrew 2026 — Beyond The Horizon track**

---

## The Idea

Light travels at a fixed speed. If a star is 2,026 light-years away, the light currently arriving at it from Earth *left Earth 2,026 years ago*. That star is — right now — witnessing the birth of Jesus.

**CosmicWitness** lets you pick any moment in history and find which real stars in our galaxy are currently receiving light from that exact moment on Earth.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python app.py

# 3. Open in your browser
open http://localhost:5000
```

On first run, the app will automatically download the **HYG Star Database v3** (~120,000 real stars) from GitHub and cache it locally. Subsequent starts are instant.

If you're offline or the download fails, the app falls back to a bundled dataset of ~200 famous named stars — still fully functional for demo purposes.

---

## How It Works

```
User selects "Moon Landing (1969)"
        ↓
App calculates: 2026 - 1969 = 57 light-years
        ↓
Queries HYG Database for stars within 57 ± 15% light-years
        ↓
Returns: Megrez (58.4 ly, UMa), Castor (51.5 ly, Gem), Caph (54.7 ly, Cas)…
        ↓
Shows: "Right now, Megrez is receiving light that left Earth in 1968,
        witnessing the Moon Landing"
```

---

## Data Sources

| Source | Purpose |
|---|---|
| [HYG Database v3](https://github.com/astronexus/HYG-Database) | 120,000 real stars with accurate distances, RA/Dec, magnitude, spectral type |
| [SIMBAD Astronomical Database](https://simbad.u-strasbg.fr) | Live API enrichment for named star details |
| `bundled_stars.json` | 196 famous named stars — offline fallback |

---

## Project Structure

```
cosmic-witness/
├── app.py                  # Flask backend + HYG loader + SIMBAD API
├── events.json             # 52 curated historical events
├── bundled_stars.json      # 196 named stars (offline fallback)
├── build_bundled_stars.py  # Script that generated bundled_stars.json
├── requirements.txt
├── README.md
└── static/
    └── index.html          # Full frontend (D3.js star map + UI)
```

---

## API Endpoints

```
GET /                               → Frontend
GET /api/events                     → List of 52 historical events
GET /api/stars?light_years=57       → Stars at target distance
GET /api/stars?light_years=57&tolerance=0.2  → Custom search window
GET /api/star-detail/<name>         → SIMBAD enrichment for a named star
GET /api/status                     → Server status + star count
```

---

## Tech Stack

- **Backend**: Python / Flask
- **Data**: HYG Database v3 (Pandas in-memory)
- **External API**: SIMBAD TAP service (star enrichment)
- **Frontend**: Vanilla JS + D3.js (celestial map)
- **Styling**: Pure CSS with space aesthetic

---

## Deployment (Heroku / Render)

```bash
# Add a Procfile:
echo "web: python app.py" > Procfile

# Push to Render (free tier works)
git init && git add . && git commit -m "CosmicWitness"
# Then connect to render.com and deploy
```

---

*Codebrew 2026 · Beyond The Horizon · Team CosmicWitness*
