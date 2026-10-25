# JobApplier OS

JobApplier is Mustafa Alp ARI's local-first, human-reviewed job search operating system. It helps ingest, rank, tailor, track, and analyze internship/co-op/new-grad-adjacent opportunities without blindly auto-applying.

## What it does

- Parses pasted public job descriptions, safely imports CSV, and restores complete local JSON backups.
- Scores roles from 0–100 across ten explainable dimensions.
- Flags sponsorship, graduation, seniority, unpaid/suspicious, pay, and unsupported-skill risks.
- Tracks the complete application lifecycle, contacts, reminders, deadlines, documents, and portal links.
- Creates truthful resume-tailoring plans, editable LaTeX drafts, keyword-gap reports, one-page estimates, cover-letter/short-answer drafts, and application checklists.
- Reports response, interview, rejection, source, role-category, missing-skill, deadline, stale-application, and funnel analytics.
- Exports tracker CSV, a full JSON backup (profile, jobs, contacts, reminders, draft records and safe `.tex` contents, and application events), and a dashboard summary.

## Safety boundary

JobApplier does not submit applications. Protected-board scraping, anti-detection browsers, login/form automation, sensitive-answer selection, and final-submit code have been removed or replaced by inert compatibility shims. It does not bypass CAPTCHAs, authentication, rate limits, protected flows, or job-board terms. Generated content is always a draft for review, and marking a job applied requires explicit confirmation that the user submitted it outside JobApplier.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 run.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The SQLite database and private profile override are gitignored. Supported launchers and request checks enforce a loopback-only host and reject cross-site mutations because there is no network authentication.

## Add or update the profile

Open **Settings & profile**, change the fields, and select **Save locally**. This creates `data/candidate_profile.json`. The built-in baseline already reflects the truthful profile in `docs/USER_PROFILE.md`, including Canadian permanent residence and May 2029 as the default expected graduation date.

## Add a job

Open **Add job**, enter any known title/company/location/source/application URL, paste the public job description, then:

1. Select **Preview score** to inspect parsed skills, fit, and risk flags.
2. Select **Add & score job** to store it locally.

For a spreadsheet you control, upload a CSV from the same screen. Accepted aliases include `job_title`, `application_url`, `url`, `date_found`, and `status`. A JobApplier JSON backup can restore local data. Use official APIs only when an employer or provider offers one under terms you can follow.

## Generate resume suggestions

Open **Resume tailor**, select a job and a profile such as `web_frontend`, `qa_testing`, or `fintech`, then select **Generate resume suggestions**. JobApplier saves a `.tex` draft under `data/drafts/`, leaves the base resume untouched, and displays:

- skills to move higher;
- missing or unverified keyword gaps;
- factual experience bullets to consider;
- the project to emphasize;
- a one-page length estimate;
- a claim-safety report.

**Prepare full package** also creates editable, locally savable application-answer drafts, shows the combined claim-safety result, and provides a manual submission checklist. Review the compiled PDF visually before using it. Optional Level 4 creates a user-confirmed reviewed link-and-checklist handoff; it does not open, fill, or submit a portal.

## Track and export applications

Use **Application tracker** to move jobs through:

`discovered → interested → resume_tailored → applied → follow_up_needed → interview → offer/rejected → archived`

Mark `applied` only after submitting on the official portal; the UI asks for explicit confirmation and creates a follow-up reminder once. Export using **Export CSV**, **Backup JSON**, or **Summary**. The API also supports:

```text
GET /api/export?format=csv
GET /api/export?format=json
GET /api/export?format=summary
POST /api/import/json
```

## Pokémon card sniper (eBay + Facebook Marketplace)

`snipe.py` is a separate tool in this repo (package `cardsnipe/`) that watches for newly listed Pokémon cards under your price caps, alerts you instantly, snipes eBay auctions in the last seconds, and can send the first message to Facebook Marketplace sellers.

```bash
make login        # one time: sign in to eBay + Facebook in the sniper's Chrome profile
make list         # watchlist lives in data/cardsnipe_watchlist.json (edit by hand or use add/rm)
make add NAME="Moonbreon" MAX=550 MIN=250 BID=600 KW="umbreon vmax 'alt art|215/203'" REGRADE=1
make scan         # one pass, dry-run: alerts fire, bids/messages are simulated with screenshots
make snipe        # continuous dry-run every SNIPE_POLL_SECONDS
make live         # real snipes (up to max_bid) and real Facebook messages
make dash         # dashboard for both tools: http://127.0.0.1:5000 (jobs) and /snipe (cards)
make deals | make bids | make cancel ID=3 | make test
```

`make help` lists everything; `python3 snipe.py` (bare = watch) with aliases `s`/`w`/`a`/`rm`/`l`/`d`/`b` also works.

How it decides: every keyword must appear (`"a|b"` = either), no exclude term may appear (whole-word, see `global_exclude` for the fakes/metal/display/novelty list), total price incl. shipping must be `min_price`–`max_price` (the floor is skipped for auctions, where a low current bid is normal), and grade rules (`graded_only`, `min_grade`) apply when set.

**Crack-and-regrade lane** (`regrade: true` / `--regrade` / `REGRADE=1`): also flags graded copies between `regrade_min_grade`–`regrade_max_grade` (default 8–9.5) priced at or under `regrade_max_price` (default = `max_price`, i.e. cheaper than a raw NM copy). TAG cards whose 1000-point score is within `tag_near_margin` (15) of `tag_ten_score` (950) qualify regardless of grade range — the "TAG 9 @ 945 that came back PSA 10" case. Alerts show ♻️, the TAG score and gap, and seller "clean copy" hints (clean, pack fresh, looks like a 10, undergraded, no whitening, ...). Both TAG numbers are editable in the watchlist JSON.

- **eBay**: uses the official Browse API when `EBAY_APP_ID`/`EBAY_CERT_ID` are set (fastest); otherwise reads search pages in a real Chrome window. Auction snipes open the bid-confirmation page ~30 s early, re-read the exact countdown from the item page, and confirm `SNIPE_LEAD_SECONDS` (default 6) before the end. Buy-It-Now deals are opened in your browser (max `SNIPE_MAX_OPEN_PER_SCAN` per scan); nothing is purchased automatically.
- **Facebook Marketplace**: newest listings in `FB_CITY` under the cap; with `FB_AUTO_MESSAGE=true` and `--live` it sends `FB_MESSAGE_TEMPLATE` to the seller. Facebook's DOM changes often, so verify with a dry run (screenshots land in `data/cardsnipe_screens/`).
- Alerts: console, macOS notification, optional `SNIPE_WEBHOOK_URL` (Discord/Slack-compatible). State is in `cardsnipe.db` (gitignored).
- **Dashboard**: `make jobs` (or `make dash`) and open [http://127.0.0.1:5000/snipe](http://127.0.0.1:5000/snipe). Every feature stores its data and shows up there: deals (filter by deal/♻️ regrade lane and source), scheduled/placed/failed snipes (cancel from the page), the watchlist (add, pause, remove targets), every scan run (duration, counts, errors such as "Facebook not logged in"), and every listing the sniper ever looked at. It refreshes itself every 30 s while `make snipe` runs.

Use your own eBay/Facebook accounts and keep the caps honest: `--live` places binding bids.

## Test

```bash
python3 -m pytest -q
python3 -m py_compile config.py database/models.py job_os/*.py dashboard/app.py cardsnipe/*.py snipe.py
```

## Known limits

- Parsing and scoring are deterministic decision support, not a prediction of employer behavior.
- Claim checks catch known prohibited patterns, unsupported skills in claim contexts, GPA, graduation mismatch, and years-of-experience claims, but human fact checking remains mandatory.
- The LaTeX one-page check is an estimate; compile and visually inspect the final PDF.
- The ignored source resume is visually clean but factually inconsistent with the configured May 2029 profile and must be corrected before use.
- Level 4 is limited to a reviewed official-link and manual-checklist handoff. No protected-board field automation is implemented.

See [PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md), [ETHICAL_AUTOMATION_POLICY.md](docs/ETHICAL_AUTOMATION_POLICY.md), [USER_PROFILE.md](docs/USER_PROFILE.md), and [RESUME_TAILORING_RULES.md](docs/RESUME_TAILORING_RULES.md).
