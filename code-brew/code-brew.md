# CosmicWitness — About the Project

## Inspiration

We started with a simple question: *what was the sky doing the night you were born?*

Every star you see tonight is a time capsule. The light reaching your eyes left that star years, decades, even centuries ago — meaning right now, somewhere out there, a star is receiving the light from the moment the Moon Landing happened. Another is receiving the light from World War II. Another from your mother's birthday.

We wanted to make that real and tangible. Not an infographic, not a Wikipedia article — an actual, navigable universe where history lives.

## What It Does

**CosmicWitness** (built as *Sirius*) lets you search any historical event or year and instantly see which real stars in the night sky are receiving the light from that exact moment *right now*. The light that left Earth at that moment is currently arriving at those stars — meaning in a very real sense, those stars are *witnessing* that event today.

Key features built and working:

- **Cosmic Search** — type any year or choose a preset event (Moon Landing, Big Bang, Fall of Rome, World War II, and 60+ more across every era of history) and we query live astronomical databases to find the exact stars at that distance
- **3D Star Map** — a live Three.js WebGL visualisation places you inside the universe, with stars rendered at accurate relative distances; drag to orbit in 3D space
- **Era Mode** — color-codes every star by the historical era it is currently "watching" on Earth, with a live legend (Prehistoric → Ancient → Medieval → Renaissance → Early Modern → Modern)
- **Family Constellation** — enter full birth dates for family members and the system finds the star currently receiving each person's birth moment; it then draws connecting lines between them on a sky canvas and plots them as a named constellation in 3D
- **Find It Tonight** — real-time altitude and azimuth calculations tell you exactly which direction to point in the sky to see your star tonight, with compass bearing and best-visibility window
- **Letters to Stars** — write a message tied to a real star; it is stored server-side and will be there when someone else finds that same star
- **Reverse Lookup** — enter a star name or a distance in light-years and find out which year that star is currently "watching" on Earth
- **Archive** — save any star moment to a personal collection
- **Certificate** — generate and download a star certificate for any witnessed moment

## How We Built It

The backend is a **Flask REST API** that queries three astronomical catalogues in parallel:

- **HYG v3** (120,000 stars, local cache) for instant offline results
- **SIMBAD TAP** (U. Strasbourg) for named and bright stars with confirmed identifiers
- **Gaia DR3** (ESA, 1.5 billion stars) for high-precision parallax measurements on nearby stars

Distance is converted from parallax using:

$$d_{\text{ly}} = \frac{3261.56}{\varpi_{\text{mas}}}$$

where $\varpi_{\text{mas}}$ is the parallax in milliarcseconds.

The frontend is a single-page app using **Three.js r128** for the 3D WebGL scene. The background star field is built from four distinct layers totalling 18,050 points:

| Layer | Count | Technique |
|-------|-------|-----------|
| Pixel stars | 10,000 | `PointsMaterial`, fixed pixel size, no texture |
| Glow stars | 2,000 | `PointsMaterial` + radial-gradient canvas texture, additive blending |
| Milky Way band | 6,000 | Gaussian-distributed along galactic plane |
| Hero stars | 50 | Large vivid points with glow texture |

Glow effects are produced by painting a radial gradient onto an offscreen `<canvas>` element and using it as a `PointsMaterial` map — no custom GLSL shaders. Sky position calculations use a full Julian Date → GMST → hour angle → altitude/azimuth pipeline computed server-side in Python.

## Challenges

**Rendering:** WebGL clears its drawing buffer after every frame by default (`preserveDrawingBuffer: false`). Getting circular glowing stars — instead of pixel squares — required carefully ordering `PointsMaterial` layers with a canvas-generated glow texture, additive blending, and placing glow layers beyond the camera's orbit radius so they are never clipped.

**Data:** Merging three live astronomical catalogues in real time (different schemas, coordinate systems, and response times) while keeping the UI snappy required a custom deduplication pass based on great-circle angular separation:

$$\Delta\theta = \sqrt{(\Delta\text{RA} \cdot \cos\bar{\delta})^2 + (\Delta\text{dec})^2}$$

combined with a source-priority ranking (HYG named > SIMBAD > HYG unnamed > Gaia DR3) and a parallel `ThreadPoolExecutor` with per-source timeouts and fallback logic.

**UX:** The biggest conceptual challenge was making something scientifically grounded feel *emotional*. The key decision was removing manual interaction barriers — star cards auto-spawn the moment a search completes, so the first thing you see when you search "Moon Landing" is three real stars already telling you their stories.

## What We Learned

- How parallax measurements translate to real cosmic distances across 120,000 catalogued stars
- How to build a multi-catalogue astronomical query pipeline with deduplication and graceful fallback
- That Three.js background star layers must be placed *beyond* the camera's orbit radius, or they vanish inside the scene
- That the most powerful UX decision was removing clicks — auto-spawning star cards made the product feel alive instead of like a query tool
- That the sky has been quietly recording everything. It just needed someone to build a search bar for it.
