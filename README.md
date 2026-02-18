# Job Applier Bot

An automated job application system that scrapes job listings from LinkedIn, Indeed, and Glassdoor, matches them to your profile, and helps you apply to relevant positions.

## Features

- 📄 **Resume Parsing**: Extracts skills, experience, and education from PDF/DOCX resumes (for matching only)
- 🔍 **Multi-Platform Scraping**: Searches jobs from LinkedIn, Indeed, and Glassdoor (finds jobs that redirect to Workday, company sites, etc.)
- 🎯 **Smart Matching**: Scores jobs based on your profile (skills, experience, location)
- 📊 **Review Interface**: Review and approve/reject jobs before applying
- 📝 **Cover Letter Generator**: Automatically generates personalized cover letters for each job
- ✂️ **Resume Tailoring**: Creates customized resume versions highlighting relevant skills
- 📎 **Per-Job Resume Selection**: Choose which resume to use for each application (no memorization)
- 🤖 **Automated Application**: Attempts to apply via LinkedIn Easy Apply and Workday (fully automated)
- 📈 **Complete Application Tracking**: Records all applications with materials, status, responses, and interviews

## Prerequisites

- Python 3.8 or higher
- Chrome browser installed
- A resume file (PDF or DOCX format)

## Installation

1. **Clone or navigate to the project directory:**
   ```bash
   cd JobApplier
   ```

2. **Install dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Create a `.env` file** (optional but recommended):
   ```bash
   touch .env
   ```

4. **Configure environment variables** (edit `.env` file):
   ```env
   # Optional: For better resume parsing (uses rule-based parsing if not provided)
   OPENAI_API_KEY=your-openai-api-key-here

   # Optional: For LinkedIn Easy Apply feature
   LINKEDIN_EMAIL=your-email@example.com
   LINKEDIN_PASSWORD=your-password

   # Optional: For Glassdoor (usually not needed)
   GLASSDOOR_EMAIL=
   GLASSDOOR_PASSWORD=

   # Optional: Customize job search
   MIN_MATCH_SCORE=60
   
   # IMPORTANT: Enable full automation (no prompts during application)
   # Set to true for unattended operation (e.g., scheduled runs)
   AUTO_APPLY_ENABLED=false
   
   # Optional: Set preferred locations for job matching
   # Example: PREFERRED_LOCATIONS=Toronto,Canada,Remote,New York
   PREFERRED_LOCATIONS=
   
   # Optional: Override resume path (uses profile resume by default)
   # Example: RESUME_PATH=/Users/username/Documents/resume.pdf
   RESUME_PATH=
   ```

   **Note**: The system works without any API keys or credentials! It will:
   - Use rule-based resume parsing (no OpenAI needed)
   - Scrape public job listings (no login needed for Indeed/Glassdoor)
   - Provide job links for manual application
   
   **For Full Automation**:
   - Set `AUTO_APPLY_ENABLED=true` to skip manual confirmation prompts
   - Configure `PREFERRED_LOCATIONS` for location-based matching
   - Set `RESUME_PATH` to override the default resume from your profile

## Quick Start

### ⚠️ IMPORTANT: Set Up Your Profile FIRST

**You MUST upload your resume before the system can match jobs to you!**

The system needs to extract your skills, experience, and education from your resume to match jobs. Without this, job matching won't work.

### Step 1: Set Up Your Profile (REQUIRED)

Parse your resume and create your profile:

```bash
python3 setup_profile.py /path/to/your/resume.pdf
```

Or run interactively:
```bash
python3 setup_profile.py
# It will prompt you for the resume path
```

**What happens:**
1. System reads your resume (PDF or DOCX)
2. Extracts your skills (Python, Java, SQL, etc.)
3. Extracts your work experience
4. Extracts your education
5. Saves everything to the database as your "profile"
6. Stores the resume path for later use

**This is how matching works:**
- The system compares job descriptions to your extracted skills/experience
- Calculates a match score (0-100) based on how well you fit
- Higher scores = better matches for you

**See `QUICK_START.md` for detailed explanation of how matching works.**

### Step 2: Search for Jobs

Run the main job search script:

```bash
python3 main.py
```

This will:
- Search for jobs across LinkedIn, Indeed, and Glassdoor
- Match each job to your profile and calculate a score (0-100)
- Save jobs to the database
- Show jobs with scores above the threshold (default: 60)

**Expected output:**
```
Starting Job Applier Bot...
==================================================
[1/3] Initializing scrapers...
✓ Indeed scraper ready
✓ Glassdoor scraper ready
⊘ LinkedIn credentials not configured (optional)

[2/3] Initializing job matcher...
✓ Job matcher ready (no API key needed)

[3/3] Searching for jobs...
--- Indeed ---
Searching: Software Engineering Intern in Remote
Found 15 jobs
  ⭐ Software Engineering Intern - Score: 75
  ⭐ Backend Intern - Score: 68
  ...
```

### Step 3: Review Jobs

Review and approve jobs before applying:

```bash
python3 review_ui.py
```

**Commands:**
- `[Enter]` or `n` - Next job
- `a` - Approve (mark for application)
- `r` - Reject (skip this job)
- `s` - Show full description
- `c` - Generate/view cover letter
- `t` - Generate tailored resume
- `q` - Quit

**Cover Letter Generation:**
- Press `c` to generate a personalized cover letter for the current job
- View existing cover letters
- Edit cover letters if needed
- Cover letters are saved in `cover_letters/` directory

**Resume Tailoring:**
- Press `t` to create a tailored resume highlighting relevant skills
- Tailored resumes are saved in `tailored_resumes/` directory
- Each resume is customized for the specific job

**List all jobs:**
```bash
python3 review_ui.py --list
```

### Step 4: Apply to Jobs

Apply to approved jobs:

```bash
python3 apply_jobs.py
```

**What happens:**
1. **Resume Selection** (once at start): You'll be asked which resume to use for all jobs
   - Can use default resume (if set in profile)
   - Can upload a different resume
   - Same resume used for all jobs in this batch
2. **Automatic Material Generation**: For all jobs automatically:
   - Generates personalized cover letters
   - Creates tailored resumes highlighting relevant skills
3. **Review Summary**: Shows complete summary of all jobs and materials
4. **Final Confirmation**: Review everything, then confirm to proceed
5. **Application**: After confirmation, attempts to apply to all jobs
6. **Complete Tracking**: All application details are recorded in the database

**Application Materials:**
- Cover letters saved in: `cover_letters/YYYYMMDD_Company_Position.txt`
- Tailored resumes saved in: `tailored_resumes/YYYYMMDD_Company_Position_Resume.docx`
- Original resume path stored for each application
- All paths are stored in the database for easy access

**Safety Features:**
- ✅ **Complete Application Records**: Every application is recorded with:
  - Which resume was used
  - Cover letter and tailored resume paths
  - Application method (LinkedIn, manual, etc.)
  - Application status (submitted, pending, interview, etc.)
  - Response tracking
  - Interview dates
  - Notes and follow-ups
- ✅ **Material Tracking**: All files are tracked - know exactly what was sent to each company
- ✅ **Status Management**: Update application status as you get responses

**Automated Platforms:**
- ✅ **Workday**: Fully automated - fills forms, uploads resume/cover letter, submits application
- ⚠️ **LinkedIn Easy Apply**: Partially automated - opens form, requires manual completion
- 📋 **Other platforms**: Provides job URLs with ready-to-use cover letters and resumes for manual application

**Workday Automation:**
- Automatically detects Workday URLs (myworkdayjobs.com)
- Fills application forms with your contact information (from profile)
- Uploads tailored resume and cover letter automatically
- Handles multi-step forms
- Submits application automatically
- **Requires**: Email in profile (set during setup_profile.py)

**Note**: All jobs are tracked in the database with complete application records

### Step 5: Track Your Applications

View and manage all your applications:

```bash
python3 view_applications.py
```

**Features:**
- View all applications with status
- See which resume/cover letter was used for each
- Track responses and interviews
- Update application status
- View detailed application records

**Commands:**
- `python3 view_applications.py` - List all applications
- `python3 view_applications.py --details` - View most recent application details
- `python3 view_applications.py --update` - Update application status interactively
- `python3 view_applications.py --export` - Export all applications to CSV

### Step 6: Export Applications to Table

Export all your applications to a CSV file:

```bash
python3 export_applications.py
```

**Export Options:**
- `python3 export_applications.py` - Full export with all details
- `python3 export_applications.py --summary` - Summary table (key info only)
- `python3 export_applications.py filename.csv` - Custom filename

**Exported Data Includes:**
- Application date and status
- Job title, company, location
- Match score and platform
- Resume, cover letter, tailored resume paths
- Response tracking
- Interview dates
- Notes and follow-ups

### Step 7: Auto-Complete Pending Applications

Applications are automatically marked for follow-up after 2 hours. Check and auto-complete:

```bash
python3 auto_complete_applications.py
```

**Commands:**
- `python3 auto_complete_applications.py` - Check pending applications
- `python3 auto_complete_applications.py --check` - Show pending applications
- `python3 auto_complete_applications.py --auto-complete` - Mark applications pending 2+ hours as completed

**Auto-Complete Feature:**
- Applications with no response after 2 hours are marked as 'completed'
- Helps keep your application list clean
- Run periodically to update status

## Testing the System

### Test 1: Database Initialization

```bash
python3 -c "from database.models import Session; print('Database OK' if Session else 'Database FAILED')"
```

Expected: `Database OK`

### Test 2: Resume Parsing

```bash
python3 setup_profile.py /path/to/test/resume.pdf
```

Check for:
- ✓ Skills extracted
- ✓ Experience/Education detected
- ✓ Profile saved successfully

### Test 3: Job Scraping (Minimal Test)

Create a test script `test_scraper.py`:

```python
from scrapers.indeed_scraper import IndeedScraper

scraper = IndeedScraper()
scraper.login()
jobs = scraper.search_jobs("Software Engineering Intern", "Remote")
print(f"Found {len(jobs)} jobs")
for job in jobs[:3]:
    print(f"  - {job['title']} at {job['company']}")
scraper.close_driver()
```

Run:
```bash
python3 test_scraper.py
```

Expected: Should find at least a few jobs

### Test 4: Job Matching

```python
from matcher.job_matcher import JobMatcher

matcher = JobMatcher({
    'skills': ['python', 'java', 'sql'],
    'experience': [],
    'education': []
})

test_job = {
    'title': 'Software Engineering Intern',
    'description': 'Looking for a Python developer intern with SQL experience',
    'location': 'Remote'
}

score = matcher.calculate_match_score(test_job)
print(f"Match score: {score}/100")
```

Expected: Score should be > 60 for relevant jobs

### Test 5: Full Workflow

1. **Setup profile:**
   ```bash
   python3 setup_profile.py your_resume.pdf
   ```

2. **Run job search (limit to 1-2 searches for testing):**
   ```bash
   python3 main.py
   ```
   Wait for it to complete (may take 5-10 minutes)

3. **Check database:**
   ```bash
   python3 review_ui.py --list
   ```

4. **Review jobs:**
   ```bash
   python3 review_ui.py
   ```

## Configuration

### Customize Job Search

Edit `config.py` or set environment variables:

```env
# Job titles to search for
JOB_TITLES=Software Engineering Intern,Data Science Intern,Backend Intern

# Locations to search
LOCATIONS=Remote,Toronto, ON,New York, NY

# Minimum match score (0-100)
MIN_MATCH_SCORE=60
```

### Database Location

Default: `job_applications.db` in project root

Change via `.env`:
```env
DATABASE_URL=sqlite:///path/to/your/database.db
```

## Cover Letter & Resume Tailoring

### Cover Letter Generation

The system automatically generates personalized cover letters for each job application:

**Features:**
- **AI-Powered** (with OpenAI API): Creates compelling, personalized cover letters
- **Template-Based** (without API): Uses smart templates with job-specific customization
- **Auto-Saved**: All cover letters saved in `cover_letters/` directory
- **Editable**: Review and edit cover letters in the review interface

**Usage:**
- Cover letters are automatically generated when you run `apply_jobs.py`
- Or generate manually in `review_ui.py` by pressing `c`
- Edit cover letters directly in the review interface

**File Format:**
- Saved as: `YYYYMMDD_Company_Position.txt`
- Stored in: `cover_letters/` directory
- Path tracked in database for easy access

### Resume Tailoring

Creates customized resume versions for each job application:

**Features:**
- **Keyword Matching**: Highlights skills mentioned in job description
- **Reordering**: Emphasizes relevant experience and skills
- **Format Preservation**: Maintains original resume structure
- **Auto-Saved**: All tailored resumes saved in `tailored_resumes/` directory

**Usage:**
- Tailored resumes are automatically created when you run `apply_jobs.py`
- Or generate manually in `review_ui.py` by pressing `t`
- Each resume is customized for the specific job

**File Format:**
- Saved as: `YYYYMMDD_Company_Position_Resume.docx`
- Stored in: `tailored_resumes/` directory
- Path tracked in database for easy access

**Best Practices:**
1. **Review before applying**: Always check generated cover letters and resumes
2. **Customize as needed**: Edit cover letters to add personal touches
3. **Keep originals**: Original resume is never modified
4. **Track everything**: All materials are linked to jobs in the database

## Troubleshooting

### Issue: "Database not initialized"

**Solution**: Check if SQLite is available:
```bash
python3 -c "import sqlite3; print('SQLite OK')"
```

### Issue: "ChromeDriver not found" or Selenium errors

**Solution**: The `undetected-chromedriver` package should auto-download ChromeDriver. If issues persist:
1. Make sure Chrome browser is installed
2. Update Chrome to latest version
3. Reinstall: `pip3 install --upgrade undetected-chromedriver`

### Issue: SSL Certificate Verification Failed (macOS)

**Symptoms**: `[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed`

**Solution**: This is a common macOS issue. Try one of these:

**Option 1 (Recommended)**: Install Python certificates:
```bash
# Find your Python installation and run:
/Applications/Python\ 3.x/Install\ Certificates.command
# Or locate it in your Python installation directory
```

**Option 2**: Install certifi package:
```bash
pip3 install certifi
```

**Option 3**: The code includes a workaround that should handle this automatically, but if it persists, you may need to install system certificates.

**Note**: The SSL fix is already included in the code, so this should work automatically in most cases.

### Issue: Scrapers not finding jobs

**Possible causes:**
- Websites changed their HTML structure (scrapers need updates)
- Rate limiting (wait a few minutes)
- Network issues

**Solution**: Check if you can manually access the job sites. If yes, the selectors may need updating.

### Issue: Resume parsing returns empty results

**Solution**: 
- Ensure resume is in PDF or DOCX format
- Check if resume has text (not just images)
- Try with OpenAI API key for better parsing:
  ```env
  OPENAI_API_KEY=your-key-here
  ```

### Issue: LinkedIn login fails

**Solution**: 
- LinkedIn may require 2FA or captcha
- Try without LinkedIn credentials (system works without it)
- Use LinkedIn credentials only if you need Easy Apply feature

## Current Limitations

1. **Auto-Apply**: LinkedIn Easy Apply automation is partially implemented - requires manual completion
2. **Scraper Stability**: Job site HTML changes may break scrapers (selectors need updates)
3. **Rate Limiting**: No built-in rate limiting - may get blocked with too many requests
4. **Cover Letters**: Not automatically generated (can be added manually in review_ui.py)

## Project Structure

```
JobApplier/
├── main.py                 # Main job search script
├── setup_profile.py        # Resume parsing and profile setup
├── review_ui.py           # Job review interface
├── apply_jobs.py          # Application automation
├── config.py              # Configuration settings
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
├── job_applications.db    # SQLite database (auto-created)
├── database/
│   └── models.py         # Database models
├── scrapers/
│   ├── base_scraper.py   # Base scraper class
│   ├── linkedin_scraper.py
│   ├── indeed_scraper.py
│   └── glassdoor_scraper.py
├── resume_parser/
│   └── parser.py        # Resume parsing logic
└── matcher/
    └── job_matcher.py   # Job matching algorithm
```

## Usage Workflow

```
1. Setup Profile (one-time)
   python3 setup_profile.py resume.pdf
   - Extracts skills/experience for matching
   - Optional: saves resume path as default
   
2. Search for Jobs (run daily/weekly)
   python3 main.py
   - Matches jobs to your profile automatically
   
3. Review Jobs (before applying)
   python3 review_ui.py
   - Press 'c' to generate cover letters
   - Press 't' to tailor resumes
   - Press 'a' to approve jobs
   
4. Apply to Approved Jobs
   python3 apply_jobs.py
   - Asks for resume ONCE (used for all jobs)
   - Automatically generates all cover letters and resumes
   - Shows complete summary for review
   - Final confirmation before applying
   - Records complete application details
   - Provides application links with ready materials
   
5. Track Applications
   python3 view_applications.py
   - View all applications and their status
   - Update application status
   - Track responses and interviews
```

## Tips

- **Run job search regularly**: New jobs appear daily
- **Review before applying**: Always check job details before auto-applying
- **Adjust match score**: Lower `MIN_MATCH_SCORE` for more results, higher for better matches
- **Use OpenAI API**: Better resume parsing if you have an API key
- **LinkedIn credentials**: Only needed for Easy Apply feature

## License

This project is for personal use. Be respectful of job site terms of service.

