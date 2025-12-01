# 🚀 Run These Commands Now

## Step 1: Apply to Jobs (With Review!)

```bash
python3 apply_jobs.py
```

**What happens:**
1. Shows you all jobs ready to apply (score 55+)
2. Generates cover letters for each job
3. Generates tailored resumes for each job
4. **Shows you a REVIEW summary with:**
   - Job title and company
   - Match score
   - Platform (Workday, LinkedIn, etc.)
   - Cover letter path
   - Tailored resume path
   - Job URL
5. **Asks for confirmation:** "Proceed with automatic application? (yes/no)"
6. **If you say yes:** Applies automatically
7. **If you say no:** Cancels, but saves all materials

**You can review everything before it applies!**

---

## What You'll See

```
📋 APPLICATION REVIEW - Review Before Applying
======================================================================

[1] Software Engineer Intern (Summer 2026) at Notion
    Match Score: 57/100
    Platform: linkedin
    URL: https://...
    Cover Letter: ✓ cover_letters/20250101_Notion_Software_Engineer_Intern.txt
    Tailored Resume: ✓ tailored_resumes/20250101_Notion_Software_Engineer_Intern_Resume.docx

[2] Software Developer Co-op, Fall 2025 at Company
    Match Score: 54/100
    Platform: workday
    URL: https://...
    ...

======================================================================
📊 Summary: 3 jobs ready to apply
======================================================================

This will:
  • Generate cover letters (if not already done)
  • Generate tailored resumes (if not already done)
  • Apply automatically to Workday/Intern Insider/Greenhouse/etc.
  • Track everything in the database

======================================================================

🤖 Proceed with automatic application? (yes/no, default=yes):
```

**Type `yes` or `y` to proceed, or `no` to cancel.**

---

## After Confirmation

If you confirm:
- **Workday jobs:** Fully automated ✅
- **Intern Insider:** Fully automated ✅
- **Greenhouse:** Fully automated ✅
- **LinkedIn:** Opens form (you complete)
- **Others:** Provides materials (you apply manually)

All applications are tracked in the database!

---

## Quick Commands

```bash
# Apply to jobs (with review step)
python3 apply_jobs.py

# View all your applications
python3 view_applications.py

# Export to CSV
python3 export_applications.py
```

---

## That's It!

Run `python3 apply_jobs.py` and you'll see everything before it applies! 🎯

