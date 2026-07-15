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

## Test

```bash
python3 -m pytest -q
python3 -m py_compile config.py database/models.py job_os/*.py dashboard/app.py
```

## Known limits

- Parsing and scoring are deterministic decision support, not a prediction of employer behavior.
- Claim checks catch known prohibited patterns, unsupported skills in claim contexts, GPA, graduation mismatch, and years-of-experience claims, but human fact checking remains mandatory.
- The LaTeX one-page check is an estimate; compile and visually inspect the final PDF.
- The ignored source resume is visually clean but factually inconsistent with the configured May 2029 profile and must be corrected before use.
- Level 4 is limited to a reviewed official-link and manual-checklist handoff. No protected-board field automation is implemented.

See [PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md), [ETHICAL_AUTOMATION_POLICY.md](docs/ETHICAL_AUTOMATION_POLICY.md), [USER_PROFILE.md](docs/USER_PROFILE.md), and [RESUME_TAILORING_RULES.md](docs/RESUME_TAILORING_RULES.md).
