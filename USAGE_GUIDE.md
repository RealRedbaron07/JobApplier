# JobApplier Usage Guide

## Quick Start

```bash
# Navigate to the project folder
cd /Users/malpari/Desktop/JobApplier/JobApplier

# Run the main workflow
python3 run.py
```

---

## Commands Reference

### Resume Management
```bash
# Set your default resume (do this once)
python3 run.py --set-resume "/path/to/your/resume.pdf"

# Check which resume is currently set
python3 run.py --show-resume

# Use a different resume for just one run
python3 run.py --resume "/path/to/other_resume.pdf"
```

### Running the App
```bash
# Full workflow: Search → Match → Generate Materials → Apply (with confirmation)
python3 run.py

# Launch the web dashboard instead
python3 run.py --dashboard
# Then open: http://localhost:5000
```

---

## How It Works

### 1. LinkedIn Auto-Login
- The app uses your Chrome profile with saved passwords
- First time: A browser will open, you may need to log in manually once
- After that: It auto-logs in using your saved credentials
- If issues occur, set `USE_CHROME_PROFILE=false` in `.env`

### 2. Workday/Company Portals
When applying to Workday sites, the app will:
1. Open the job page
2. Click "Apply"
3. **If login is required**: Pause and prompt you to log in/create account
4. **You handle the login** in the browser
5. Press ENTER to continue
6. App fills out the form automatically
7. **Final check**: You review the form, then confirm submission

### 3. Final Confirmation
Before any application is submitted:
```
📋 FINAL CHECK - Review the application
-----------------------------------------
   Please review the form in the browser.
   Make any final edits if needed.
-----------------------------------------
>>> Submit this application? [y/n]: _
```

---

## Dashboard Usage

Launch: `python3 run.py --dashboard`

### Features:
- **Search for Jobs**: Click the button, wait for progress bar
- **Review Matches**: See all jobs sorted by match score
- **Select & Apply**: Check the jobs you want, click "Apply to Selected"
- **Track Status**: See which applications succeeded

---

## Configuration

Edit `.env` file (copy from `.env.example` if needed):

```bash
# Key settings:
USE_CHROME_PROFILE=true          # Use saved Chrome passwords
WAIT_FOR_LOGIN=true              # Wait for manual login if needed
MIN_MATCH_SCORE=60               # Only show jobs scoring 60+
```

---

## Workflow Summary

```
1. Set Resume    →  python3 run.py --set-resume ~/resume.pdf
2. Run Search    →  python3 run.py
3. Review Jobs   →  See list, type 'yes' or 'select 1,3,5'
4. Login Prompts →  Handle in browser, press ENTER to continue
5. Final Review  →  Check each form, type 'y' to submit
6. Done!         →  Check dashboard for results
```

---

## Tips

- **First run**: Keep browser visible to handle any login prompts
- **LinkedIn**: Log in once, credentials are saved in Chrome profile
- **Workday**: Each company may need separate account - handle once, then it's saved
- **Materials**: Cover letters and tailored resumes are saved in `cover_letters/` and `tailored_resumes/`

---

## File Locations

```
/Users/malpari/Desktop/JobApplier/JobApplier/
├── run.py                    # Main entry point
├── user_settings.json        # Your saved resume path
├── cover_letters/            # Generated cover letters
├── tailored_resumes/         # Job-specific resumes
├── job_applications.db       # Database of all jobs
└── chrome_profile/           # Saved browser session
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| LinkedIn won't auto-login | Close Chrome completely, then run again |
| Form fields not filling | Review manually, the app will pause for you |
| "No resume set" error | Run `python3 run.py --set-resume /path/to/resume.pdf` |
| Dashboard won't start | Check if port 5000 is free, or change in `.env` |
