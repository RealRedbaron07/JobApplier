# Ethical Automation Policy

## Core rule

JobApplier may automate organization and preparation. It may not automate the final decision or submission.

## Automation levels

- **Level 0:** manual tracking.
- **Level 1:** description parsing and fit scoring.
- **Level 2:** truthful resume and answer drafts.
- **Level 3:** complete application-package preparation.
- **Level 4:** a user-confirmed handoff that exposes the reviewed official link and a manual-action checklist. It never opens protected flows, fills fields, authenticates, or submits.
- **Level 5:** blind auto-apply is not implemented.

The default is Level 3. Environment variables cannot enable automatic submission.

## Prohibited conduct

JobApplier must not bypass CAPTCHAs, authentication walls, rate limits, platform protections, or terms; scrape restricted sites; evade bot detection; invent skills, experience, dates, education, eligibility, GPA, pay expectations, or project outcomes; send messages without approval; or submit AI-generated answers without review.

## Human approval boundary

The user must review the target role, eligibility, safety flags, resume, short answers, cover letter, requested documents, and application form. A Level-4 handoff may organize the link and checklist after review; the user still opens and completes the portal, performs the final submit action, and then manually marks the application as applied.

## Safety flags

The app warns about sponsorship conflicts, graduation-date conflicts, unknown required technologies, seniority mismatch, unpaid work, suspicious payment/training fees, low pay, and dishonest requirements. The configured Ontario general-wage floor is $17.60/hour through September 30, 2026; Ontario publishes $17.95/hour beginning October 1, 2026. A warning is not legal advice, and current rates must be verified against the [Ontario Employment Standards guide](https://www.ontario.ca/book/export/html/95373).

## Data and privacy

Private operational data is local by default. Database, `.env`, private profile JSON, generated drafts, exports, logs, and browser profiles are gitignored. Secrets and job-portal passwords must never be committed. Exports are user-triggered.

The supported dashboard uses deterministic local generation and does not send candidate or posting content to an external AI provider.

## Generated content

Every generated item is labeled a draft. Missing skills remain gaps. Claim validation blocks known prohibited MalpariBot/S.E.N.S.E./JobApplier overclaims and unsupported years-of-experience language. Deterministic safeguards complement, but do not replace, human review.
