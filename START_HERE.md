# 🚀 START HERE - Exact Instructions

## Step 1: Setup Your Profile (One-Time Setup)

```bash
python3 setup_profile.py '/Users/malpari/Desktop/Mustafa Alp ARI Resume.pdf'
```

**What happens:**
- Parses your resume
- Extracts skills, experience, education
- Asks for your email (enter: `malpari@icloud.com`)
- Asks for phone (press Enter to skip)
- Asks for first name (enter: `Mustafa Alp` or press Enter)
- Asks for last name (enter: `ARI` or press Enter)
- Saves everything to database

**Expected output:**
```
✅ Profile setup complete!
```

---

## Step 2: Find Jobs (Automatic)

```bash
python3 main.py
```

**What happens:**
- Searches LinkedIn, Indeed, Glassdoor
- Finds jobs matching your profile
- Scores each job (0-100)
- Detects Workday/Intern Insider/Greenhouse URLs
- Saves all jobs to database
- Takes 5-10 minutes

**Expected output:**
```
Job search completed!
Total jobs found: X
New jobs added: Y
```

**Note:** This may take a while. Let it run. You can press Ctrl+C to stop early if needed.

---

## Step 3: Apply to Jobs (Fully Automated!)

```bash
python3 apply_jobs.py
```

**What happens:**
- Shows you jobs ready to apply to
- Asks for resume path (or uses default)
- **Automatically generates:**
  - Cover letters for each job
  - Tailored resumes for each job
- **Automatically applies:**
  - Workday jobs: Fully automated ✅
  - Intern Insider: Fully automated ✅
  - Greenhouse: Fully automated ✅
  - Lever: Fully automated ✅
  - SmartRecruiters: Fully automated ✅
  - LinkedIn: Opens form (you complete)
  - Others: Provides materials (you apply manually)
- **Tracks everything** in database

**Expected output:**
```
🚀 Starting automatic application to X jobs...
✅ Successfully applied!
📝 Application recorded in database
```

---

## Optional: Review Jobs Before Applying

If you want to review jobs first:

```bash
python3 review_ui.py
```

This lets you:
- See all found jobs
- Review match scores
- Approve/reject jobs
- Then run `apply_jobs.py` to apply to approved ones

---

## Optional: View Your Applications

```bash
python3 view_applications.py
```

Shows all your applications with status.

---

## Optional: Export to CSV

```bash
python3 export_applications.py
```

Exports all applications to a CSV file for tracking.

---

## Quick Reference

```bash
# 1. Setup (one-time)
python3 setup_profile.py '/Users/malpari/Desktop/Mustafa Alp ARI Resume.pdf'

# 2. Find jobs
python3 main.py

# 3. Apply automatically
python3 apply_jobs.py
```

**That's it!** The system handles everything else automatically.

---

## Troubleshooting

**If you get database errors:**
```bash
python3 migrate_database.py
```

**If you want to start fresh:**
```bash
rm job_applications.db
python3 setup_profile.py '/Users/malpari/Desktop/Mustafa Alp ARI Resume.pdf'
```

---

## What Gets Automated

✅ **Fully Automated:**
- Workday applications
- Intern Insider applications
- Greenhouse applications
- Lever applications
- SmartRecruiters applications

✅ **Partially Automated:**
- LinkedIn (opens form, you complete)

✅ **Materials Provided:**
- Cover letters generated
- Tailored resumes generated
- All saved and tracked

---

## Ready to Start?

Run these 3 commands in order:

```bash
python3 setup_profile.py '/Users/malpari/Desktop/Mustafa Alp ARI Resume.pdf'
python3 main.py
python3 apply_jobs.py
```

**That's it!** 🎉

