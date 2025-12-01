# 🚀 Quick Start Guide - Upload Resume and Start!

## Super Simple Setup (3 Steps)

### Step 1: Upload Your Resume
```bash
python3 setup_profile.py /path/to/your/resume.pdf
```

**What it does:**
- Extracts your skills, experience, education
- Extracts contact info (email, phone, name)
- Saves everything to database
- **Takes 30 seconds!**

### Step 2: Find Jobs (Automatic)
```bash
python3 main.py
```

**What it does:**
- Searches LinkedIn, Indeed, Glassdoor
- Finds jobs matching your profile
- Scores each job (0-100)
- Saves to database
- **Runs automatically, no input needed!**

### Step 3: Apply Automatically! 🎯
```bash
python3 apply_jobs.py
```

**What it does:**
- **Automatically applies to all jobs above match score**
- Generates cover letters (AI-powered if API key set)
- Tailors resumes for each job
- **Workday: Fully automated** ✅
- **Intern Insider: Fully automated** ✅
- **Greenhouse, Lever, SmartRecruiters: Fully automated** ✅
- **LinkedIn: Opens form** (you complete)
- **Others: Provides materials** (you apply manually)

**NO CONFIRMATION NEEDED - APPLIES AUTOMATICALLY!**

## That's It! 🎉

The system will:
1. ✅ Find jobs automatically
2. ✅ Generate materials automatically
3. ✅ Apply automatically (where possible)
4. ✅ Track everything automatically

## Supported Platforms

### Fully Automated ✅
- **Workday** - Fills forms, uploads files, submits
- **Intern Insider** - Fills forms, uploads files, submits
- **Greenhouse** - Fills forms, uploads files, submits
- **Lever** - Fills forms, uploads files, submits
- **SmartRecruiters** - Fills forms, uploads files, submits

### Partially Automated ⚠️
- **LinkedIn** - Opens Easy Apply form (you complete)

### Manual (Materials Provided) 📋
- **Indeed** - Provides cover letter + tailored resume
- **Glassdoor** - Provides cover letter + tailored resume
- **Other platforms** - Provides all materials

## What You Need

### Required:
- ✅ Resume (PDF or DOCX)
- ✅ Email in profile (for automated applications)

### Optional (but recommended):
- ✅ OpenAI API key (for better cover letters/resumes)
- ✅ Phone number (for form filling)
- ✅ First/Last name (for form filling)

## Example Workflow

```bash
# 1. Setup (one-time, 30 seconds)
python3 setup_profile.py ~/Desktop/my_resume.pdf

# 2. Find jobs (runs automatically, 5-10 minutes)
python3 main.py

# 3. Apply (fully automated, no confirmation!)
python3 apply_jobs.py
```

**That's it!** The system handles everything else automatically.

## Check Your Applications

```bash
# View all applications
python3 view_applications.py

# Export to CSV/Excel
python3 export_applications.py
```

## Tips

1. **Set OpenAI API key** for better cover letters:
   ```bash
   echo "OPENAI_API_KEY=your-key-here" >> .env
   ```

2. **Adjust match score** in `.env`:
   ```bash
   MIN_MATCH_SCORE=60  # Lower = more jobs, Higher = better matches
   ```

3. **Check applications regularly**:
   ```bash
   python3 view_applications.py
   ```

## Troubleshooting

**"No jobs found"**
- Run `python3 main.py` again
- Check your job titles in `config.py`

**"Email not set"**
- Run `python3 setup_profile.py` again
- Enter email when prompted

**"Resume not found"**
- Provide full path: `/Users/yourname/Desktop/resume.pdf`
- Or use relative path from project directory

## Ready to Start?

```bash
python3 setup_profile.py your_resume.pdf
python3 main.py
python3 apply_jobs.py
```

**That's it! The system will automatically apply to jobs!** 🚀
