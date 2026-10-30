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

## One-click Pokémon discovery

Open **Browse cards** and click **Scan all cards automatically**. A background worker drives Chrome through broad eBay and Facebook Marketplace searches, deduplicates listings and imports candidates into **Scan results** on that page. It does not require any card targets. Choose eBay, Marketplace or both. Existing watchlist card names, grades, conditions and exclusions do not restrict this scan.

Each click runs one pass: at most eight searches, up to 60 rows per search, with a 60-second cooldown after completion. eBay server errors get one retry using the same keywords in eBay's normal homepage search bar; those results are labelled as an unfiltered retry, since eBay's default ordering and filters apply. Verification blocks stop that source immediately; two consecutive failed searches also stop it. One transient query failure does not discard the other categories. Other sources can still finish. **Stop after current page** ends the pass without discarding candidates already collected. Scans do not repeat on a timer. Status polling only reads the local app.

The scan covers promotions/coupons, newest listings, ending auctions, offers, lots, sealed products and Marketplace collections. Prices, currencies, reported shipping, conditions, source routes and visible promotion terms are saved. Variable or unknown prices stay unknown. The shared watchlist budget does not cap broad scan results, so you can review any price. Unknown shipping is marked explicitly. Candidates are not labelled as independently verified discounts, and a bid is not a final purchase price.

Filter imported candidates using **Min price** and **Max price** together under **Scan results**. Bounds include reported shipping, before tax and other charges; unknown totals are hidden while either bound is set. Blank bounds leave that side open. Optional **Set in title** and **Type in title** fields combine with the price, site and keyword filters. They match seller titles, not verified card metadata. **Clear price** resets only the price range. Filters update immediately and do not trigger scans or judge whether a card is a value play.

**Buying format** filters the same saved candidates to auctions, Buy Now/fixed-price listings, or both. Marketplace listings count as fixed price. The filter combines with price, site, set, type and keywords. Auction prices are current bids, not final prices.

`Config.BROWSER_SCANS_ENABLED` permits these explicit read-only Chrome scans and scanner sign-in. `Config.EXTERNAL_ACCESS_ENABLED` stays hard-disabled: no eBay API, TCGplayer/PriceCharting calls, exchange-rate requests, Collectr sync, career-board fetches or paid AI services run from this workflow. Existing API keys are stripped from the broad scanner settings. The old scanner CLI and targeted network/valuation endpoints remain disabled. The app never bids, buys, or sends seller messages.

The scanner uses a persistent, separate Chrome profile. Your normal browser's Facebook login is not copied into it. If Marketplace asks for authentication, expand **Marketplace scanner sign-in**, sign in once, and click **Finish scanner sign-in**. The sign-in window stays open until you finish or cancel. Do not enter credentials into a short-lived scan window.

Open **Browse cards** to hunt across all Pokémon cards without specifying a card, set, grade or watchlist. Blank keywords default to `pokemon cards`. Broad discovery includes every buying format, with separate eBay routes for **Sales & coupons**, **Auctions ending soon** and **Accepts offers**. Product types such as singles, any grading company, lots, collections, sealed and promos are optional shortcuts. Seller promotions, current bids and negotiable prices are leads, not verified below-market deals. Coupon requirements and final auction prices need checking.

The collapsed **Open searches manually (optional)** section retains direct eBay/Marketplace links. Each route and **Search all Pokémon on eBay** opens results in a new tab. Enter optional keywords and press **Search eBay**, or use **Search Marketplace** for the same query. These links preserve the saved budget and refresh after budget edits. **Open eBay home** opens [ebay.ca](https://www.ebay.ca/) if you prefer its own search bar. No eBay account or API key is required. Manual Marketplace links use the Facebook session in your normal browser. These manual links do not import results; use the automatic scan button for that.

**My portfolio** is a dated local snapshot. It does not automatically sync with Collectr. To update it without external fetching, open **Update portfolio from Collectr**, select USD on your public showcase, clear filters, load every card, copy the page and paste it into the dashboard. Preview the cards, conditions and quantities, then choose **Replace local snapshot**. Non-USD figures and incomplete totals are rejected before saved data changes. Collectr figures remain source estimates in their original USD, separate from independent market references. A new import leaves independent values unpriced. Played and unknown raw condition never receive Near Mint reference prices. Reload and focus refresh the local snapshot only, without contacting Collectr.

Browser search links include the shared price cap; individual saved-card links use the lower shared or per-card cap. Shipping, tax and import charges still need checking. The app never bids, purchases, sends seller messages or submits job applications.

**Reload saved results** only reads local storage. Historical scans and references remain available with their original dates. Values are saved estimates, not current quotes. Collection currency conversion uses the configured exchange-rate estimate without contacting an exchange-rate API. **Re-judge saved listings** uses saved, unexpired references only.

Automatic discovery reads browser listings; it does not fetch independent current market prices. Review exact card number, set, language, grading company, condition, authenticity, promotion terms and all-in cost before treating a candidate as a bargain.

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
