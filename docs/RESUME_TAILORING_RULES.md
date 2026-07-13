# Resume Tailoring Rules

## Invariants

1. Never overwrite the base resume.
2. Save every tailored variant as a draft under a gitignored path.
3. Use only facts in the configured profile.
4. Treat missing keywords as gaps, not permission to add them.
5. Never invent metrics, ownership, production scale, GPA, eligibility, dates, or years of experience.
6. Keep MalpariBot paper-only and S.E.N.S.E. clearly team-built.
7. Use May 2029 unless the user changes the configured graduation date.
8. Require human review before compiling, sharing, or submitting.

## Profiles

- `general_software`: balanced languages, debugging, Git, code review, testing.
- `web_frontend`: TypeScript, JavaScript, React, Next.js, HTML/CSS/Tailwind.
- `qa_testing`: manual/regression testing, bug reports, debugging, pytest where supported.
- `data_reporting_bi`: Python, SQL/MySQL, Pandas, processing, reporting and automation.
- `fintech`: truthful finance-platform, data, risk, and paper-research experience.
- `applied_ai_automation`: Python, Gemini API, accessibility, hardware/software integration, automation.
- `food_service_survival_job`: transferable teamwork, events, reliability, and communication; kept separate from technical resumes.

## Tailoring process

1. Extract required and preferred skills.
2. Match them case-insensitively against the approved skill inventory.
3. Select a resume profile from the role language, or let the user override it.
4. Select the most relevant factual experience and project bullets.
5. Reorder supported skills; list unknown requirements as gaps.
6. Generate editable LaTeX with a one-page line estimate.
7. Run the claim guard.
8. Compile and visually inspect the PDF outside the current automatic flow.
9. Human-review every line against the source profile and job post.

## One-page rule

The current checker estimates content lines against a 58-line target. This is an early warning, not a layout proof. A final PDF must be rendered and visually checked for clipping, overflow, unreadable text, broken links, and excessive density.
