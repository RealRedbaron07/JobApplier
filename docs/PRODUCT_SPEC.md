# JobApplier Product Specification

## Purpose

JobApplier reduces repetitive job-search work while Mustafa retains control of every claim, external interaction, and application submission. The initial market is Canadian internship/co-op/new-grad-adjacent roles in software, web, QA, data/BI, fintech, applied AI/automation, and technical analysis.

## Product flow

1. **Ingest:** manual form, pasted text, owned CSV, or a terms-compliant official API.
2. **Parse and score:** extract requirements and compute an explainable 0–100 fit score.
3. **Decide:** show strengths, missing skills, safety flags, resume profile, project emphasis, and strategy.
4. **Prepare:** generate truthful resume and answer drafts plus a checklist.
5. **Approve:** the user reviews, edits, and manually submits on the official portal.
6. **Track:** record outcome, materials, contacts, reminders, deadlines, and notes.
7. **Learn:** analyze conversion, sources, categories, and recurring skill gaps.

## Scoring model

| Dimension | Weight |
|---|---:|
| Technical skill match | 24 |
| Internship/co-op suitability | 15 |
| Location/commute fit | 12 |
| Start-date fit | 10 |
| Role-type fit | 12 |
| Industry fit | 7 |
| Resume-strength fit | 8 |
| Missing-requirements risk | 6 |
| Application effort | 3 |
| Likelihood worth applying | 3 |

Categories are `strong_apply` (82+), `apply` (68–81), `maybe` (52–67), `low_priority` (35–51), and `skip` (below 35). Blocking safety flags cap the score at 15; high-severity flags cap it at 54. Scores are decision support, not predictions of employer behavior.

## Data model

SQLite stores jobs, application records, drafts, contacts, follow-ups, saved links, and the user profile. Existing databases are upgraded with additive local SQLite columns. Generated drafts and private profile overrides live under gitignored `data/` paths.

## Screens

- Dashboard: metrics, priority queue, warnings and next actions.
- Add Job: paste/preview/add and CSV import.
- Job Detail: score, explanation, gaps, safety, checklist, notes, and official link.
- Resume Tailor: profile selection, suggestions, LaTeX draft, answers, package.
- Application Tracker: filters, statuses, deadlines, next actions, exports.
- Follow-ups: local reminders and editable drafts.
- Contacts: recruiter/referral CRM.
- Analytics: funnel, rates, sources, categories, and gaps.
- Settings/Profile: personal details, preferences, and automation level.

## Non-goals

- blind or bulk application submission;
- protected-site scraping or anti-detection behavior;
- CAPTCHA/authentication/rate-limit bypass;
- automated email or LinkedIn messages;
- inferred or fabricated candidate facts;
- claims that a score guarantees an interview.

## Future, only if safe

- bookmarklet/extension for user-selected public text;
- official employer/ATS APIs with documented permission;
- local PDF compilation and render preview;
- encrypted local backups;
- user-approved Level 4 field-filling helpers that stop before final submission.
