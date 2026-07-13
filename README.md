# JobApplier OS

JobApplier is Mustafa Alp ARI's local-first, human-reviewed job search operating system. It helps ingest, rank, tailor, track, and analyze internship/co-op/new-grad-adjacent opportunities without blindly auto-applying.

## What it does

- Parses pasted public job descriptions and safely imports CSV files.
- Scores roles from 0–100 across ten explainable dimensions.
- Flags sponsorship, graduation, seniority, unpaid/suspicious, pay, and unsupported-skill risks.
- Tracks the complete application lifecycle, contacts, reminders, deadlines, documents, and portal links.
- Creates truthful resume-tailoring plans, editable LaTeX drafts, keyword-gap reports, one-page estimates, cover-letter/short-answer drafts, and application checklists.
- Reports response, interview, rejection, source, role-category, missing-skill, deadline, stale-application, and funnel analytics.
- Exports tracker data as CSV or JSON and a dashboard summary as JSON.

## Safety boundary

JobApplier does not submit applications. The code hard-enforces `AUTO_MODE=false`, `AUTO_APPLY_ENABLED=false`, and `STOP_BEFORE_SUBMIT=true`. Legacy commands either stop with a dashboard redirect or prepare drafts only. It does not bypass CAPTCHAs, authentication, rate limits, protected flows, or job-board terms. Generated content is always a draft for review.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 dashboard/app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The SQLite database and private profile override are gitignored.

## Add or update the profile

Open **Settings & profile**, change the fields, and select **Save locally**. This creates `data/candidate_profile.json`. The built-in baseline already reflects the truthful profile in `docs/USER_PROFILE.md`, including Canadian permanent residence and May 2029 as the default expected graduation date.

## Add a job

Open **Add job**, enter any known title/company/location/source/application URL, paste the public job description, then:

1. Select **Preview score** to inspect parsed skills, fit, and risk flags.
2. Select **Add & score job** to store it locally.

For a spreadsheet you control, upload a CSV from the same screen. Accepted aliases include `job_title`, `application_url`, `url`, `date_found`, and `status`. Use official APIs only when an employer or provider offers one under terms you can follow.

## Generate resume suggestions

Open **Resume tailor**, select a job and a profile such as `web_frontend`, `qa_testing`, or `fintech`, then select **Generate resume suggestions**. JobApplier saves a `.tex` draft under `data/drafts/`, leaves the base resume untouched, and displays:

- skills to move higher;
- missing or unverified keyword gaps;
- factual experience bullets to consider;
- the project to emphasize;
- a one-page length estimate;
- a claim-safety report.

**Prepare full package** also creates editable application-answer drafts and a manual submission checklist. Review the compiled PDF visually before using it.

## Track and export applications

Use **Application tracker** to move jobs through:

`discovered → interested → resume_tailored → applied → follow_up_needed → interview → offer/rejected → archived`

Mark `applied` only after submitting on the official portal. Export using **Export CSV** or **Export JSON**. The API also supports:

```text
GET /api/export?format=csv
GET /api/export?format=json
GET /api/export?format=summary
```

## Test

```bash
pytest -q
python3 -m py_compile config.py database/models.py job_os/*.py dashboard/app.py
```

See [PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md), [ETHICAL_AUTOMATION_POLICY.md](docs/ETHICAL_AUTOMATION_POLICY.md), [USER_PROFILE.md](docs/USER_PROFILE.md), and [RESUME_TAILORING_RULES.md](docs/RESUME_TAILORING_RULES.md).
