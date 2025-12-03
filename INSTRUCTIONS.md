# 📋 Complete Instructions to Run the Job Applier

## 🎯 Quick Start (3 Steps)

### Step 1: Setup Your Profile (One-Time, 30 seconds)

```bash
python3 setup_profile.py '/Users/malpari/Desktop/Mustafa Alp ARI Resume.pdf'
```

**What to enter when prompted:**
- Email: `malpari@icloud.com` (or your email)
- Phone: Press Enter to skip (or enter your phone)
- First Name: `Mustafa Alp` (or press Enter)
- Last Name: `ARI` (or press Enter)

**Expected output:**
```
✅ Profile setup complete!
```

---

### Step 2: Find Jobs (5-10 minutes)

```bash
python3 main.py
```

**What happens:**
- ✅ Searches LinkedIn, Indeed, Glassdoor
- ✅ Finds jobs in:
  - **Canada:** Toronto, Mississauga, Brampton, Markham, etc.
  - **Turkey:** Istanbul, Ankara (with Turkish job titles!)
  - **Remote:** Worldwide
- ✅ Scores each job (0-100)
- ✅ Detects Workday, Intern Insider, Greenhouse URLs
- ✅ Saves all jobs to database

**Expected output:**
```
Job search completed!
Total jobs found: X
New jobs added: Y
```

**Note:** This may take 5-10 minutes. Let it run. You'll see it searching:
- English job titles in all locations
- Turkish job titles (Yazılım Stajyeri, etc.) in Istanbul/Ankara only
- Optimized to skip unnecessary searches

---

### Step 3: Apply to Jobs (Fully Automated!)

```bash
python3 apply_jobs.py
```

**What happens:**
1. Shows you all jobs ready to apply (score 55+)
2. Asks for your resume path (or uses default)
3. **Automatically generates:**
   - Cover letters (in English or Turkish, auto-detected!)
   - Tailored resumes for each job
4. **Shows you a REVIEW summary** with:
   - Job title, company, match score
   - Platform (Workday, LinkedIn, etc.)
   - Cover letter and resume paths
   - Job URL
5. **Asks for confirmation:** "Proceed with automatic application? (yes/no)"
6. **If you say `yes`:**
   - ✅ **Workday:** Fully automated
   - ✅ **Intern Insider:** Fully automated
   - ✅ **Greenhouse:** Fully automated
   - ✅ **Lever:** Fully automated
   - ✅ **SmartRecruiters:** Fully automated
   - ⚠️ **LinkedIn:** Opens form (you complete)
   - 📄 **Others:** Provides materials (you apply manually)
7. **Tracks everything** in database

**Expected output:**
```
📋 APPLICATION REVIEW - Review Before Applying
======================================================================
[1] Software Engineer Intern at Company
    Match Score: 57/100
    Platform: workday
    Cover Letter: ✓ cover_letters/...
    Tailored Resume: ✓ tailored_resumes/...

🤖 Proceed with automatic application? (yes/no, default=yes): yes

✅ Successfully applied to 3 jobs!
```

---

## 📊 View Your Applications

```bash
python3 view_applications.py
```

Shows all your applications with status, dates, and details.

---

## 📤 Export to CSV

```bash
python3 export_applications.py
```

Exports all applications to `applications_export.csv` for tracking in Excel/Google Sheets.

---

## 🔄 Optional: Review Jobs Before Applying

If you want to review and approve/reject jobs first:

```bash
python3 review_ui.py
```

Then run `python3 apply_jobs.py` to apply to approved ones.

---

## 🌍 Turkish Support

The system automatically:
- ✅ Searches Turkish job titles (Yazılım Stajyeri, Stajyer Yazılım Mühendisi, etc.)
- ✅ Finds jobs in Istanbul and Ankara
- ✅ Matches Turkish job descriptions
- ✅ Generates Turkish cover letters when needed (auto-detects language)
- ✅ Applies to Turkish internships automatically

**No extra steps needed!** Just run the commands above.

---

## 🚨 Troubleshooting

### Database Errors
```bash
python3 migrate_database.py
```

### Start Fresh
```bash
rm job_applications.db
python3 setup_profile.py '/Users/malpari/Desktop/Mustafa Alp ARI Resume.pdf'
```

### No Jobs Found
- Run `python3 main.py` again
- Check your `.env` file for `MIN_MATCH_SCORE` (lower = more jobs)
- Make sure you ran `setup_profile.py` first

---

## 📝 Complete Workflow

```bash
# 1. Setup (one-time, 30 seconds)
python3 setup_profile.py '/Users/malpari/Desktop/Mustafa Alp ARI Resume.pdf'

# 2. Find jobs (5-10 minutes)
python3 main.py

# 3. Apply automatically (with review step)
python3 apply_jobs.py

# 4. View applications
python3 view_applications.py

# 5. Export to CSV
python3 export_applications.py
```

**That's it!** 🎉

---

## ✅ What Gets Automated

**Fully Automated:**
- ✅ Workday applications
- ✅ Intern Insider applications
- ✅ Greenhouse applications
- ✅ Lever applications
- ✅ SmartRecruiters applications
- ✅ Cover letter generation (English/Turkish)
- ✅ Resume tailoring
- ✅ Application tracking

**Partially Automated:**
- ⚠️ LinkedIn (opens form, you complete)

**Materials Provided:**
- 📄 Cover letters (saved to `cover_letters/`)
- 📄 Tailored resumes (saved to `tailored_resumes/`)
- 📊 All tracked in database

---

## 🎯 Ready to Start?

Run these 3 commands:

```bash
python3 setup_profile.py '/Users/malpari/Desktop/Mustafa Alp ARI Resume.pdf'
python3 main.py
python3 apply_jobs.py
```

**The system will handle everything else automatically!** 🚀

