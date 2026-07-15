# JobApplier Usage Guide

## Start the local app

```bash
python3 run.py
```

Open <http://127.0.0.1:5000>. JobApplier refuses a non-loopback host in the supported launchers because the dashboard contains private profile and CRM data and has no network authentication.

## Configure Mustafa's profile

Open **Settings & profile**. The built-in source of truth already contains the approved identity, education, eligibility, experience, projects, skills, targets, May 2029 graduation default, and automation level 3. Saving creates the gitignored `data/candidate_profile.json`; partial updates preserve fields not shown or changed.

Automation levels are enforced:

- 0: manual tracking;
- 1: parse and score;
- 2: resume and answer drafts;
- 3: package preparation;
- 4: user-confirmed reviewed link-and-checklist handoff; no protected-board field automation is included;
- 5: unavailable.

## Add and rank a job

Use **Add job** to enter structured fields and paste the complete public posting. **Preview score** shows the 0–100 breakdown, matched and missing skills, strategy, and safety flags. **Add & score job** stores it in local SQLite.

CSV import accepts owned data and preserves tracker fields such as status and dates. JSON restore accepts only a JobApplier backup. The app does not search or scrape LinkedIn, Workday, Indeed, Glassdoor, or another protected board.

## Prepare an application

Open a job or use **Resume tailor**:

1. Generate resume suggestions at level 2 or higher.
2. Review supported skills, gaps, factual bullets, selected project, and claim-safety report.
3. Generate editable cover-letter and short-answer drafts.
4. At level 3, prepare the combined package, edit and save answers, and review the checklist and claim-safety result.
5. Compile the versioned `.tex` file yourself and visually inspect the one-page PDF.
6. At optional level 4, create a reviewed handoff that exposes the official link and a manual-action checklist.
7. Open, complete, and submit the official portal application yourself.
8. Return to the tracker. Marking `applied` requires an explicit confirmation and creates one local application record plus a follow-up reminder.

The supplied base PDF is reference-only because its factual wording does not fully match the configured profile. Do not upload it without resolving the warnings in `docs/USER_PROFILE.md`.

## Contacts and follow-ups

Contacts store recruiter context, relationship strength, last contact, and follow-up state. Message templates are editable drafts only. Follow-ups can target a job or contact, use business-day defaults, and be marked completed. Nothing is emailed or posted.

## Export and restore

- **Export CSV** creates a spreadsheet-friendly tracker.
- **Backup JSON** includes jobs, profile, contacts, follow-ups, draft records and safe `.tex` contents, and application events.
- **Summary** exports current analytics as JSON.
- **Restore JSON backup** restores local data and keeps existing jobs with the same application URL.

Private exports can contain sensitive notes and must be stored accordingly.

## Test

```bash
python3 -m pytest -q
python3 -m py_compile config.py database/models.py job_os/profile.py job_os/parser.py job_os/scoring.py job_os/tailoring.py dashboard/app.py
```

See [README.md](README.md) and [docs/ETHICAL_AUTOMATION_POLICY.md](docs/ETHICAL_AUTOMATION_POLICY.md).
