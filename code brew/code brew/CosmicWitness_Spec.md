# CosmicWitness — Product Spec
### Codebrew 2026 | Beyond The Horizon Track

---

## The Idea (Plain English)

Light travels at a fixed speed. If a star is 2,026 light-years away, the light currently leaving it departed from there 2,026 years ago — and the light currently arriving *at* it from Earth also left Earth 2,026 years ago. That means right now, that star is "seeing" Earth as it was 2,026 years ago: the approximate year of the birth of Jesus, the height of the Roman Empire, the Han Dynasty in China.

**CosmicWitness** lets anyone type in a historical event, find which real stars are currently witnessing that moment, and visualise them on an interactive star map.

---

## Problem Statement

Space is abstract. People know intellectually that starlight is old, but they don't *feel* it. There's no tool that bridges the human experience of history with the physical reality of how light travels across the cosmos. CosmicWitness makes this connection tangible and personal — turning the night sky into a living archive of human history.

---

## Goals

1. **Make the concept visceral**: A user should be able to type "Battle of Hastings" and within seconds see the exact stars that are currently receiving light from that moment on Earth.
2. **Ground it in real data**: All stars displayed must come from a verified astronomical catalog with real measured distances (not fictional or approximate).
3. **Make it shareable**: Every result should be shareable as a link or image so users can post "the star watching the moon landing right now is Kepler-442."
4. **Work as a hackathon prototype**: A functional, impressive demo should be achievable within the hackathon timeframe (~24 hours of build time).
5. **Lay the groundwork for the on-theme prize**: The pitch should frame this as a foundational astronomy tool — the kind of thing early space-age mission planners would have used to communicate the scale of the cosmos.

---

## Non-Goals

- **Not a full planetarium app**: We are not building a real-time 3D sky renderer like Stellarium. The star map is a visualisation aid, not a simulation.
- **Not a historical database**: We are not building or maintaining a database of historical events. We use a curated list or a third-party API for event data.
- **Not mobile-first**: Desktop browser is the primary target for the hackathon prototype. Mobile responsiveness is a nice-to-have.
- **Not real-time telescope integration**: We are not connecting to live telescope feeds or observatories.
- **Not multi-language**: English only for the prototype.

---

## User Stories

### Curious Explorer (Primary User)
- As a curious person, I want to type a historical event (e.g. "Moon Landing") and see which stars are currently watching it, so that I can feel the scale of the cosmos in a personal way.
- As a curious person, I want to see the name, constellation, and distance of each star result so that I can look it up or find it in the night sky.
- As a curious person, I want to share my result with a friend so that they can experience the same moment of wonder.

### Educator / Presenter
- As an educator, I want to use this tool to show students that the night sky is a time machine, so that the concept of light-travel time becomes memorable and concrete.
- As an educator, I want to input a custom year rather than just searching by event name, so that I can explore any moment in history — including ones not in a preset list.

### Hackathon Judge
- As a judge, I want to see a working prototype that queries real star data, so that I can evaluate the technical depth of the submission.
- As a judge, I want to see a clear, beautiful interface that communicates the concept immediately, so that I can assess the design quality.

---

## Requirements

### Must-Have (P0)

**1. Historical Event Input**
- A search field where users can type a historical event name OR a specific year (e.g. "1969" or "Moon Landing").
- A curated list of ~30–50 well-known events with pre-set years as quick-select options (e.g. Moon Landing, WWII, Roman Empire fall, birth of Christ, Big Bang, dinosaur extinction).
- Acceptance criteria: User can either search/select an event OR manually type a year between 1 and 13,800,000,000 (age of the universe in years).

**2. Light-Year Distance Calculation**
- System calculates: `distance_in_light_years = current_year (2026) - event_year`
- For events BCE, correctly handle negative years.
- Acceptance criteria: Inputting "Moon Landing (1969)" returns a target distance of 57 light-years. Inputting "birth of Christ (~4 BCE)" returns ~2,030 light-years.

**3. Star Catalog Query**
- Query the **HYG Database** (free, ~120,000 stars, includes distance in parsecs) or the **ESA Hipparcos catalog** for stars within ±10% of the target light-year distance.
- Convert parsecs to light-years: `1 parsec = 3.2616 light-years`.
- Return up to 10 matching stars, sorted by how close their distance is to the target.
- Acceptance criteria: For a target of 57 light-years, return real named stars (e.g. Gliese 667, 61 Virginis) that are within 51–63 light-years of Earth.

**4. Results Display**
- For each matching star, display:
  - Star name (or catalog ID if unnamed)
  - Constellation
  - Exact distance in light-years
  - The year on Earth that the star is currently "watching" (i.e. `2026 - distance`)
  - Whether the star is visible to the naked eye (magnitude < 6.5)
- Acceptance criteria: All five data points display correctly for each result. Named stars are prioritised over unnamed catalog entries.

**5. Interactive Star Map**
- A 2D sky map (using RA/Dec coordinates) showing where the result stars appear in the sky.
- Stars are plotted as glowing points; clicking a star shows its detail card.
- Acceptance criteria: Map renders within 2 seconds. Stars are plotted in approximately correct sky positions.

---

### Nice-to-Have (P1)

**6. Shareable Result Link**
- Each result page has a unique URL (e.g. `/event/moon-landing` or `/?year=1969`) that can be shared.
- Optionally: a "Copy share link" button and a pre-formatted tweet/post text.

**7. "What is this star watching right now?" Reverse Mode**
- User clicks a star and sees *all* the historical events it is currently witnessing.
- E.g. clicking a star 57 light-years away shows: "This star is currently watching the Moon Landing (1969)."

**8. Animated Light Travel Visualisation**
- A short animation showing a pulse of light leaving Earth and travelling to the star, arriving "now."
- Helps non-technical users intuitively grasp the concept.

**9. Dark Mode / Space Aesthetic**
- Deep black background, starfield, glowing UI elements consistent with a space theme.
- Improves the emotional impact of the tool.

**10. "Tonight in your sky" feature**
- Using the user's location (or a default), indicate which result stars are visible above the horizon tonight.

---

### Future Considerations (P2)

- **3D visualisation**: Render the stars in 3D space using Three.js, showing Earth at the center and stars at their correct distances.
- **Galactic events**: Extend the timeline to geological and cosmic scales (extinction events, formation of Earth, Big Bang).
- **AR mode**: Point your phone at the sky and highlight which stars are witnessing specific historical events.
- **Multiplayer "cosmic moments"**: Show multiple events simultaneously — "this star is watching both the birth of Mozart and the death of Shakespeare at the same time."
- **API for educators**: A public API so teachers can embed CosmicWitness results in lesson plans and presentations.

---

## Technical Architecture

### Frontend
- **Framework**: React (Vite) or plain HTML/CSS/JS for simplicity
- **Star Map**: D3.js for 2D celestial projection (Aitoff or stereographic), or a lightweight canvas renderer
- **Styling**: Tailwind CSS with a custom dark space theme

### Backend / Data
- **Star Data**: HYG Database v3 (CSV, ~120,000 stars, free, public domain)
  - Fields: `id`, `proper` (name), `dist` (distance in parsecs), `ra`, `dec`, `mag`, `con` (constellation)
  - Download: [https://github.com/astronexus/HYG-Database](https://github.com/astronexus/HYG-Database)
- **Processing**: Pre-process the CSV into a lightweight JSON or SQLite file indexed by distance
- **API**: A simple Python (Flask/FastAPI) or Node.js backend with a single endpoint:
  - `GET /stars?light_years=57&tolerance=0.1` → returns matching stars
- **Historical Events**: A hand-curated JSON file of ~50 events with names, years, and brief descriptions

### Hosting (for demo)
- Frontend: Vercel or GitHub Pages
- Backend: Render.com free tier or a simple serverless function

---

## Data Pipeline Detail

```
HYG CSV (120k stars)
       ↓
Filter: remove stars with dist = 0 or dist > 100,000 ly
       ↓
Convert: dist_parsecs × 3.2616 = dist_light_years
       ↓
Add: visibility flag (mag < 6.5 = naked eye visible)
       ↓
Index: sort by dist_light_years, store as JSON
       ↓
Query: binary search for stars within [target × 0.9, target × 1.1]
       ↓
Return: top 10 by proximity to target distance
```

---

## Success Metrics (for Hackathon Demo)

| Metric | Target |
|---|---|
| Query response time | < 1 second from input to results |
| Star results returned | ≥ 3 named stars for any target distance 10–10,000 ly |
| Data accuracy | All distances verifiable against HYG catalog |
| Demo wow factor | Judge can input their birth year and get a named star result |
| Pitch clarity | Non-technical judge understands the concept within 30 seconds |

---

## Open Questions

| Question | Owner | Blocking? |
|---|---|---|
| Does the HYG database have enough named stars at all distances, or will most results be catalog IDs? | Data/Engineering | Yes — test this early |
| What tolerance range (±5%? ±10%? ±50 ly?) gives the best balance of accuracy and result count? | Engineering | Yes — affects UX significantly |
| For events BCE, is "year of Jesus birth" ~4 BCE or ~1 CE? How do we handle historical uncertainty? | Design/Content | No — use a note/disclaimer |
| Can we pre-compute and cache all results for the 50 curated events to avoid live queries during the demo? | Engineering | No — good optimisation |
| Should the star map show the full celestial sphere or just the visible hemisphere? | Design | No |

---

## Build Plan (24-Hour Hackathon Timeline)

### Hour 0–2: Setup & Data
- [ ] Download and pre-process HYG Database CSV
- [ ] Write distance query script and verify results manually
- [ ] Set up React + Vite project skeleton
- [ ] Curate list of 30–50 historical events with years

### Hour 2–6: Core Feature (P0)
- [ ] Build event search input + quick-select dropdown
- [ ] Wire up distance calculation
- [ ] Build backend query endpoint
- [ ] Display raw results (no map yet) — validate data accuracy

### Hour 6–10: Star Map + Polish
- [ ] Integrate D3.js star map
- [ ] Plot result stars on map with click-to-detail
- [ ] Apply space aesthetic styling
- [ ] Handle edge cases (no results, very old events, future dates)

### Hour 10–16: Nice-to-Haves + Demo Prep
- [ ] Add shareable URLs (P1)
- [ ] Add animated light-travel visualisation if time permits
- [ ] "What is this star watching?" reverse mode
- [ ] Test with 10+ different events end-to-end

### Hour 16–20: Video Pitch
- [ ] Record demo walkthrough
- [ ] Write pitch script covering:
  1. The concept (light travel time as a time machine)
  2. Inspiration (existing astronomy tools + the Pale Blue Dot)
  3. Technical decisions made (why HYG, why tolerance range chosen)
  4. What this could become (on-theme prize angle)

### Hour 20–24: Buffer + Submission
- [ ] Fix any last bugs
- [ ] Deploy to Vercel/Render
- [ ] Submit

---

## On-Theme Prize Angle (Beyond The Horizon Bonus)

Frame CosmicWitness not just as a fun visualisation, but as the kind of foundational tool that would have genuinely helped early space-age communicators and mission planners explain the scale of the cosmos to the public and to decision-makers.

**Pitch framing**: *"When Voyager 1 launched in 1977, there was no intuitive way for the public to grasp that the light from their TV sets was racing toward stars that were watching the American Revolution. CosmicWitness is the tool that should have existed then — and still needs to exist now."*

This captures the "weight and clarity of building something that genuinely matters" that the on-theme prize rewards.

---

## Recommended Team Split (3–4 people)

| Role | Responsibilities |
|---|---|
| Data/Backend | HYG processing, query API, distance calculations |
| Frontend/Map | React app, D3 star map, UI components |
| Design/Content | Visual design, event curation, copy, pitch script |
| Full-stack/Pitch | Ties everything together, records video, handles deployment |

---

*Spec version: 1.0 — Codebrew 2026, April 9*
