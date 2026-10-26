# Audit: REint Full Stack SWE Challenge v4

Audit date: 26 Oct 2026. Source of truth: `REint Full Stack SWE challenge v4 Shared.docx`
(kept in the repo root, git-ignored).

This file records the state of the project **after** this audit's fixes, with the
evidence behind each status.

## A. Executive summary

**What the project does.** Wind Forecast Insights is a web app for a UK utility's
day-ahead trading desk. For each purchase decision in January 2026 it shows the national
wind forecast the desk could actually have seen at decision time: the latest Elexon
WINDFOR value published at or before a chosen UK-time cutoff on the day before delivery.
It also measures how accurate that forecast was against Elexon FUELHH wind outturn.
Stack: React + TypeScript (Vite, Recharts), FastAPI, PostgreSQL, Redis, Celery, Docker.

**Overall compliance.** The product requirements in the brief are implemented and
verified:
- shows the forecasts available at decision time;
- measures their accuracy quantitatively;
- uses only Elexon WINDFOR and FUELHH WIND;
- covers January 2026 decisions only;
- React frontend, Python backend, Docker.

The headline metrics were recomputed by an independent script working from raw Elexon
JSON and match the API exactly. The **submission deliverables are not done yet**:
- the app is not deployed to Heroku or Vercel;
- the README has no live link;
- no git remote / public GitHub repo is configured;
- the video has not been recorded (a ready-to-record script is in `YT.md`);
- the form has not been submitted.

These need the author's own accounts and actions.

**Most important issues found.** No P0 or P1 defects; the business logic was correct.
The issues found were:
- P2: a deployment defect for the documented Heroku setup. Heroku Redis `rediss://`
  URLs were rejected by Celery and would fail TLS verification in redis-py.
- P2: weak loading and error handling in the UI.
- P3: several UX, accessibility and documentation accuracy gaps.

**Most important fixes.**
- `rediss://` URL normalisation.
- A UI load-state rework: stale-while-loading, error with Retry that keeps the last good
  view, an empty state, and invalid shared links.
- Chart units and accessible chart summaries.
- A mobile grid overflow fix.
- An honest in-sample caveat on the likely-range band.
- 15 new tests.

**Remaining material risks.**
- The Heroku deploy itself has not been executed, so `heroku.yml`'s release phase is
  unverified on Heroku.
- The 80% likely-range band is measured in-sample on January, so it is not a validated
  forecast interval.
- The default 09:00 cutoff is an assumption to confirm with the desk.

## B. Original assignment requirements

R-rows are from the DOCX. D-rows are business rules *derived* from R1/R2 that the
correctness of those requirements depends on; they are not extra requirements.

| ID | Requirement | Relevant files | Initial status | Final status | Verification evidence |
|---|---|---|---|---|---|
| R1 | Users can clearly understand the latest renewable (wind) forecasts available when they make day-ahead purchase decisions | `backend/app/analytics.py` (`select_forecasts`), `frontend/src/App.tsx`, `components/ForecastChart.tsx`, `components/DailyTable.tsx` | PASS | PASS | `test_uses_latest_forecast_published_before_cutoff`, `test_later_cutoff_selects_newer_forecast`. Live: every delivery day of 2 Jan–1 Feb has 24/24 forecast hours at 09:00. The UI shows the run used ("Forecast published 27 Jan, 07:30 UK…") per day. Browser flow "table selects day" passed. |
| R2 | Evaluate forecast accuracy quantitatively so decisions can account for quantified error | `analytics.py` (`compute_metrics`, breakdowns), `components/Kpis.tsx`, `BarCharts.tsx` | PASS | PASS | `test_metrics_formulae`, new MAPE/nMAE edge tests. An independent script on raw Elexon JSON gives MAE 2038.9 MW, bias +1747.9 MW and RMSE 2504.8 MW over 744 h at 09:00, identical to `/api/v1/dashboard`. 13:00 also matches (MAE 1904.0). |
| R3 | National-level wind actuals and forecasts from Elexon only, no other data | `backend/app/elexon.py`, `ingestion.py` | PASS | PASS | Code inspection: only the two `/datasets/{FUELHH,WINDFOR}/stream` calls exist. |
| R4 | Actuals from FUELHH stream, `fuelType` = WIND, using `startTime` and `generation` | `elexon.py` (`fetch_actuals`, `actual_values`) | PASS | PASS | `test_actuals_request_filters_to_wind`. Live sync: 1,488 half-hours (31 days × 48), no duplicates and no negatives, checked from raw JSON. |
| R5 | Forecasts from WINDFOR stream using `startTime`, `publishTime`, `generation` | `elexon.py` (`fetch_forecasts`, `forecast_values`) | PASS | PASS | `test_forecast_request_uses_publish_window_and_parses_rows`. Live sync: 17,864 forecast rows, publish times 31 Dec 02:30 – 31 Jan 22:30 UTC. |
| R6 | Only data relevant to purchase decisions made in January 2026 | `backend/app/period.py`, `ingestion.py` (`fetch_window`), `main.py` (date validation) | PASS | PASS | `test_targets_outside_delivery_window_are_ignored`, `test_dashboard_rejects_out_of_range_parameters`. Live: stored targets run 2 Jan 00:00 – 1 Feb 23:00 UTC. `decision_date=2026-02-01` → HTTP 422. |
| R7 | Purchase decisions are made one day before the delivery day | `period.py` (`decision_date_for`, `cutoff_for`) | PASS | PASS | `test_early_cutoff_falls_back_to_previous_day_forecast`; new `test_decision_cutoff_is_uk_local_time_across_daylight_saving`. |
| R8 | React frontend | `frontend/` | PASS | PASS | `npm run build` succeeds; React 18.3.1. |
| R9 | Python backend | `backend/app/` | PASS | PASS | FastAPI app; 58 pytest tests pass. |
| R10 | Use Docker | `Dockerfile`, `compose.yaml` | PASS | PASS | `docker compose up --build -d`: postgres and redis healthy; migrate completed; api, worker and beat running; `/api/v1/health/ready` → postgres ok, redis ok. |
| R11 | Deploy the sample app on Vercel or Heroku | `heroku.yml`, `Dockerfile`, `backend/app/config.py` | FAIL | FAIL | Not deployed: no Heroku CLI, credentials or authorisation in this environment. The config was improved (`rediss://` fix), but the release phase and runtime on Heroku are unverified. |
| R12 | README states explicitly whether AI tools were used | `README.md` ("Use of AI tools") | PASS | PASS | Section present. |
| R13 | Unlisted YouTube video: Part 1 customer pitch (≤5 min), Part 2 tech-lead review (≤5 min), ≤10 min total | `YT.md` | FAIL | FAIL | No video is referenced anywhere in the repo, and any earlier recording would predate this audit's UI changes. `YT.md` is a ready-to-record script timed to 4:45 + 4:50. |
| R14 | Public GitHub repo with an anonymous name | git config | FAIL | FAIL | `git remote -v` is empty. |
| R15 | README: details of files and directories | `README.md` ("Repository layout") | PASS | PASS | Table checked against the tree; `AUDIT.md` and `YT.md` rows added. |
| R16 | README: how to start the application | `README.md` ("Running it") | PASS | PASS | The Docker path was followed as written and works. The non-Docker path was partly exercised: uvicorn ran from `backend/` against a local DB. |
| R17 | README: link to the Vercel/Heroku app | `README.md` | FAIL | FAIL | Placeholder text only; depends on R11. |
| R18 | Submit details through the challenge form | none | UNVERIFIED | UNVERIFIED | Outside the repo; needs R11, R13 and R14 first. |
| R19 | Open each submitted URL in incognito to confirm access | none | UNVERIFIED | UNVERIFIED | No URLs exist yet. |
| D1 | No look-ahead: a decision only uses forecasts with `publishTime` ≤ cutoff on the decision day (inclusive) | `analytics.py` | PASS | PASS | `test_later_cutoff_selects_newer_forecast` (09:30 inclusive, 09:29 excludes). |
| D2 | Like-for-like pairing: hourly WINDFOR vs mean of the hour's two half-hourly FUELHH values | `analytics.py` (`hourly_actuals`) | PASS | PASS | `test_uses_latest_forecast_published_before_cutoff` (110 = mean of 100 and 120); the independent recompute matches. |
| D3 | Missing data is never scored as zero: hours missing either half-hour, or with no forecast, are excluded and shown as such | `analytics.py`, `DailyTable.tsx` (paired/forecast hours) | PASS | PASS | `test_hour_missing_a_half_hour_actual_is_not_paired`, `test_unmatched_forecast_is_visible_but_excluded_from_accuracy`, new `test_empty_database_returns_a_full_month_with_no_metrics`. |
| D4 | Invalid upstream data cannot corrupt results; ingestion is atomic and idempotent | `elexon.py`, `ingestion.py` | PASS | PASS | `test_invalid_records_are_reported`, `test_failed_sync_leaves_existing_data_and_cache_untouched`, `test_sync_is_idempotent_and_updates_revised_values`. A live re-sync gave the same counts. |
| D5 | Times handled in UK local time (Europe/London), stored in UTC | `period.py`, `models.py` (`UTCDateTime`) | PASS | PASS | New DST test; naive datetimes rejected at bind time. |

The 16-hour time guideline in the brief is a process constraint and cannot be
verified from the code, so it is not scored.

## C. Defects discovered

| # | Severity | Description | Root cause | Impact | Fix applied |
|---|---|---|---|---|---|
| 1 | P2 | Heroku Redis URLs (`rediss://`, self-signed cert) break Celery and the cache | Celery raises `ValueError: A rediss:// URL must have parameter ssl_cert_reqs` (reproduced). redis-py verifies certs by default. | On the README's documented Heroku setup: the manual sync endpoint fails and caching silently degrades. The worker cannot start. | `Settings.normalise_redis_url` appends `ssl_cert_reqs=none` to `rediss://` URLs that do not set it (Heroku's documented setting). Tests cover the parsing and that Celery resolves it to `ssl.CERT_NONE`. |
| 2 | P2 | Switching the cutoff showed no loading feedback | Single `LoadState`; a refetch kept the old payload in the `ready` state silently | The cutoff select showed 11:00 while the 09:00 numbers were still displayed, with no indication | Separate `data` / `loading` / `error` state. Old content is dimmed with `aria-busy` and a live "Loading the 11:00 cutoff…" notice. |
| 3 | P2 | A failed refresh wiped the whole dashboard, and there was no Retry anywhere | Error state replaced data | One transient network error left the user with nothing but reloading the page | The last good view stays, with an alert naming which cutoff is shown, plus a Retry button. Network errors get a readable message instead of "Failed to fetch". |
| 4 | P3 | Mobile grid could overflow | `.page` grid had an implicit `auto` column; new wrappers lacked `min-width: 0`; `.grid-2` used `minmax(320px, 1fr)`, wider than a 320 px phone's content area | Horizontal overflow and chart mis-sizing on narrow phones (found by inspection) | `minmax(0, 1fr)` columns and `minmax(min(320px, 100%), 1fr)`. Measured after the fix at 320–1600 px: no page overflow, charts fit their cards. |
| 5 | P3 | A shared link with an unknown `?day=` dimmed every bar and left the day select out of step | `selected` was never validated against the data | Confusing view from a bad link | Unknown days reset to the whole month; the URL is cleaned up. |
| 6 | P3 | No empty state | — | An empty DB showed blank charts and dashes | An empty-state card explains how to load data. |
| 7 | P3 | Bar charts had no units or axis titles; month-wide breakdowns were not labelled when a day was selected | — | Readers could misread GW values, or think the breakdowns were per day | GW axis labels, x-axis titles and "all of January" captions. KPI header says "Accuracy across January" or "Accuracy for the selected day". The daily axis shows "1 Feb" instead of "1". |
| 8 | P3 | Bias hint read "Forecast below actual" when bias was exactly 0 | Two-way ternary | Wrong text in an edge case | `biasHint()` handles zero; unit tested. |
| 9 | P3 | The likely-range band was presented as usable at decision time without saying it is computed from the same month | Documentation and copy | Overstates the predictive validity of the band | The UI caption and README now state that it is in-sample. |
| 10 | P3 | README said WINDFOR runs cover "about 48 hours ahead" | Not checked against data | Factual error in docs | Corrected from live data: targets run to 21:00 UTC two days after publication, about 46–66 h ahead. |
| 11 | P3 | Accessibility gaps | — | Screen-reader and keyboard users | Text summaries on charts (`role="img"` + `aria-label` with real values); table `<caption>`; row headers; `aria-pressed` on day buttons; `:focus-visible` ring; spinner respects `prefers-reduced-motion`. |

Known and **not** fixed: the production JS bundle is 578 kB (165 kB gzip), mostly
Recharts, and Vite warns about it. It is a single dashboard page, so code-splitting
would not reduce what the page needs, and the item was left alone.

## D. Implementation changes

- **Backend:** `backend/app/config.py`: `normalise_redis_url` validator.
- **Frontend:**
  - `frontend/src/App.tsx`: load-state rework, retry, invalid-day reset, empty
    states, a day facts strip (forecast energy, peak and lowest forecast hour, hours
    compared), and scope captions.
  - `frontend/src/api.ts`: network-error message.
- **Business logic:** none changed. It was verified correct (see R1, R2, D1–D5).
  `frontend/src/lib.ts` gained a pure `resolveView()` (client-side day filter, moved
  out of `App.tsx` so it can be tested) and `biasHint()`.
- **Data processing / Database:** no changes. Migrations round-trip cleanly on
  Postgres 16 and `alembic check` reports no drift.
- **UI/UX:**
  - `components/BarCharts.tsx`: axis units and titles, summaries.
  - `components/ForecastChart.tsx`: summary, signed error in the tooltip.
  - `components/Kpis.tsx`: scope header.
  - `components/DailyTable.tsx`: caption, row headers, `aria-pressed`, sticky first
    column.
  - `frontend/src/styles.css`: status, spinner, empty state, day facts, focus ring,
    grid fixes, mobile KPI span.
- **Testing:** `backend/tests/test_analytics.py` (+4), `backend/tests/test_support.py`
  (+6 cases), `frontend/src/lib.test.ts` (+5).
- **Security and reliability:** defect 1. No secrets were added; `.env` does not exist
  and `.env.example` contains only placeholders.
- **Documentation:** `README.md` corrections and additions; this file; `YT.md`.

## E. UI/UX improvements

All on the single dashboard page (`frontend/src/App.tsx` and components):
- **Feedback:**
  - A loading notice with a spinner and dimmed previous content while a cutoff loads.
  - An error banner with Retry that keeps the last good data and names which cutoff it
    shows.
  - An empty-database card.
  - A "no forecast before cutoff" note for an empty day.
- **Clarity:**
  - A one-line rule under the filters: only forecasts published at or before the
    cutoff are used; D buys for D+1.
  - KPI scope header.
  - "All of January" captions on the breakdowns.
  - GW axis labels and axis titles on all bar charts.
  - Signed error in the forecast tooltip.
  - "Last synced … UK".
  - In-sample caveat on the band.
- **Day drill-down:** a facts strip with forecast energy (GWh), peak and lowest forecast
  hour, and hours compared with outturn.
- **Responsive:**
  - Grid overflow fixed.
  - Lone fifth KPI spans both columns on phones.
  - Sticky decision-day column while the table scrolls sideways.
- **Accessibility:** see defect 11.

## F. Test results

All commands below were run during this audit.

| Command | Result |
|---|---|
| `ruff check backend` | Passed |
| `ruff format --check backend` | Passed (22 files) |
| `pytest -q` (SQLite) | **58 passed** (was 48 before the audit) |
| `pytest -q --cov=app` with `TEST_DATABASE_URL` → throwaway `postgres:16-alpine` | **58 passed**, coverage 94% |
| `alembic upgrade head && alembic downgrade base && alembic upgrade head && alembic check` (Postgres 16) | Passed; "No new upgrade operations detected" |
| `npx tsc -b` | Passed |
| `npm test` (Vitest) | **10 passed** (was 5) |
| `npm run build` | Passed; chunk-size warning (578 kB JS) |
| `docker compose up --build -d` | All services up; api healthy |
| `docker compose run --rm migrate python -m app.ingestion` (live Elexon) | Passed in about 10 s: 17,864 forecasts, 1,488 actuals |

**Runtime and API checks** (against the compose stack, live data):
- `GET /` and `GET /docs` → 200.
- `/api/v1/health/ready` → `{"postgres":"ok","redis":"ok"}`.
- `decision_date=2026-02-01` → 422.
- `POST /api/v1/ingestion/sync` without a configured token → 503.
- Unknown `/api/...` → 404.
- `decision_date=2026-01-27` → 24 points, MAE 5,375 MW.
- Cache: 0.43 s uncached, then 0.015–0.021 s cached; TTL 3600 s; payload 161 kB.
- Celery worker: "Connected to redis… ready"; beat started.

**Independent calculation check.** A standalone Python script working from raw Elexon
JSON, sharing no app code, reproduced the following exactly:

| Cutoff | Hours | MAE | Bias | RMSE | Over-forecast hours |
|---|---|---|---|---|---|
| 09:00 | 744 | 2038.9 MW | +1747.9 MW | 2504.8 MW | 84.9% |
| 13:00 | 744 | 1904.0 MW | +1692.5 MW | n/a | n/a |

**Browser checks.** Headless Chrome was driven over the DevTools protocol with device
emulation.

Layout at 320, 375, 414, 768, 1024, 1440 and 1600 px:
- no horizontal page overflow (`scrollWidth` ≤ viewport) at any width;
- chart SVGs fit their cards (e.g. 309 px at 375);
- legends stay inside their cards;
- the table scrolls inside its own container on narrow screens;
- **no console errors or failed requests**.

Interaction flows, all passed:
1. Initial load shows MAE 2.04 GW.
2. Switching to 13:00 updates the KPI to 1.90 GW and the URL.
3. With the API blocked, switching to 11:00 keeps the 13:00 view and shows an
   explanatory alert.
4. Retry loads 11:00 (2.01 GW) and clears the alert.
5. `?day=2026-02-14` falls back to the month and cleans the URL.
6. Clicking "Tue 27 Jan" in the table selects that day: KPI 5.37 GW, select synced,
   `aria-pressed`.
7. "Show all of January" resets.
8. A failure on first load shows the error and Retry.

The empty-DB state was checked against uvicorn with an empty SQLite DB (screenshot).

**Manual inspection.** Screenshots before and after at 375, 768 and 1440 px and of the
day view; dark mode tokens were reviewed in CSS.

**Not verified:**
- Heroku deployment and release phase;
- the Celery `rediss://` connection against real Heroku Redis (parsing is tested, the
  connection is not);
- Firefox and Safari rendering;
- real screen-reader output;
- the GitHub Actions run (the workflow was not triggered; its steps were reproduced
  locally above).

## G. Final requirement status

| Status | Count | IDs |
|---|---|---|
| PASS | 18 | R1–R10, R12, R15, R16, D1–D5 |
| PARTIAL | 0 | none |
| FAIL | 4 | R11, R13, R14, R17 |
| UNVERIFIED | 2 | R18, R19 |
| **Total** | **24** | |

The project is **not fully compliant**. The product and engineering requirements pass;
the submission deliverables (deploy, repo, video, form) are outstanding.

## H. Remaining limitations

1. **Deployment (R11, R17).** Run the Heroku steps in `README.md` → "Deployment
   (Heroku)", then put the URL in the README. This needs the author's Heroku account;
   it was not attempted here because it is an outward-facing action needing
   credentials.
2. **Public repo (R14).** Create an anonymously named public GitHub repo, add it as a
   remote and push. `REint…docx` is git-ignored, so it will not be published.
3. **Video (R13).** Record from `YT.md` after deploying, so the app is shown at its
   public URL.
4. **Form and incognito checks (R18, R19)** after 1–3.
5. **Business assumptions to confirm with the client:**
   - the 09:00 UK default cutoff;
   - the decision-day → delivery-day mapping (decisions 1–31 Jan, delivery 2 Jan–1 Feb).
6. **Modelling caveat.** The likely-range band and all metrics are measured on January
   2026 only; the band is in-sample.
7. **Heroku worker.** `heroku.yml` defines only `web`; nightly refresh on Heroku needs
   a worker process added as the README describes. The data loads at release either
   way.
