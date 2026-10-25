# Full Automation Setup Guide

This guide explains how to set up the JobApplier for fully automated, unattended operation.

## Quick Setup (3 Steps)

### 1. Update Your Resume Path

The system needs to know where your resume is located. You have two options:

**Option A: Update via Script (Recommended)**
```bash
python3 update_resume.py "/Users/malpari/Downloads/Mustafa_Alp_ARI_Resume_4.pdf"
```

**Option B: Set via Environment Variable**
```bash
# Add to your .env file:
RESUME_PATH=/Users/malpari/Downloads/Mustafa_Alp_ARI_Resume_4.pdf
```

**Option C: Re-run Profile Setup**
```bash
python3 setup_profile.py "/Users/malpari/Downloads/Mustafa_Alp_ARI_Resume_4.pdf"
```

### 2. Enable Full Automation

Edit your `.env` file and set:
```env
AUTO_APPLY_ENABLED=true
```

This removes all manual confirmation prompts and allows the system to run unattended.

### 3. Configure Your Preferences (Optional)

**Set Preferred Locations:**
```env
# Add to .env:
PREFERRED_LOCATIONS=Toronto,Canada,Remote,Istanbul,Ankara
```

**Adjust Match Score Threshold:**
```env
# Default is 60, lower for more jobs, higher for better matches
MIN_MATCH_SCORE=55
```

## What Changed?

### 🎯 Improved Job Matching

**Before:** Jobs were heavily biased toward:
- Toronto, Canada, Istanbul, Turkey locations (hardcoded)
- Computer Science + Economics profiles
- Aggressive penalties (-20 for non-internship jobs)

**After:** 
- ✅ Location preferences are configurable via `PREFERRED_LOCATIONS`
- ✅ Matching works for any profile/location
- ✅ Reduced penalties (only -5 for non-internship, -10 for red flags)
- ✅ More entry-level keywords recognized
- ✅ Better scoring for skill matches

### 🤖 Full Automation

**Before:**
- Required typing "yes" to proceed with applications
- Could not run unattended (e.g., scheduled cron jobs)

**After:**
- ✅ Set `AUTO_APPLY_ENABLED=true` for zero prompts
- ✅ Can run in Docker, CI/CD, scheduled tasks
- ✅ Auto-uses resume from profile (no manual selection)

### 📄 Resume Management

**New Features:**
- ✅ `update_resume.py` script to easily change resume
- ✅ `RESUME_PATH` environment variable to override
- ✅ Auto-validation of resume file existence

## Full Workflow

### Automated Daily Run (Example)

```bash
# 1. One-time setup (first time only)
python3 setup_profile.py "/Users/malpari/Downloads/Mustafa_Alp_ARI_Resume_4.pdf"

# 2. Configure .env for automation
cat >> .env << EOF
AUTO_APPLY_ENABLED=true
PREFERRED_LOCATIONS=Toronto,Canada,Remote
MIN_MATCH_SCORE=60
OPENAI_API_KEY=your-key-here
LINKEDIN_EMAIL=your-email@example.com
LINKEDIN_PASSWORD=your-password
EOF

# 3. Run the bot (can be scheduled via cron)
python3 main.py          # Find jobs
python3 review_ui.py -a  # Auto-approve jobs above threshold
python3 apply_jobs.py    # Apply automatically (no prompts!)
```

### Scheduled Automation (Cron Example)

```bash
# Add to crontab (run daily at 9 AM)
0 9 * * * cd /path/to/JobApplier && python3 main.py && python3 apply_jobs.py

# Or use a wrapper script:
# run_automation.sh
#!/bin/bash
cd /path/to/JobApplier
python3 main.py
python3 review_ui.py --auto-approve
python3 apply_jobs.py
```

## Environment Variables Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `AUTO_APPLY_ENABLED` | Enable unattended operation | `true` or `false` |
| `PREFERRED_LOCATIONS` | Comma-separated locations | `Toronto,Canada,Remote` |
| `RESUME_PATH` | Override resume path | `/Users/me/resume.pdf` |
| `MIN_MATCH_SCORE` | Minimum score to apply | `60` (0-100) |
| `OPENAI_API_KEY` | Better cover letters | `sk-...` |
| `LINKEDIN_EMAIL` | LinkedIn automation | `you@email.com` |
| `LINKEDIN_PASSWORD` | LinkedIn automation | `yourpassword` |

## Testing Your Setup

### Test 1: Verify Resume Path
```bash
python3 -c "from database.models import Session, UserProfile; session = Session(); profile = session.query(UserProfile).first(); print(f'Resume: {profile.resume_path if profile else \"No profile found\"}')"
```

### Test 2: Test Job Matching
```bash
python3 -c "
from matcher.job_matcher import JobMatcher
matcher = JobMatcher({'skills': ['python', 'java'], 'preferred_locations': ['Toronto']})
test_job = {'title': 'Software Engineering Intern', 'description': 'Python developer intern', 'location': 'Toronto, Canada'}
print(f'Score: {matcher.calculate_match_score(test_job)}/100')
"
```

### Test 3: Verify Automation Config
```bash
python3 -c "from config import Config; print(f'AUTO_APPLY_ENABLED: {Config.AUTO_APPLY_ENABLED}')"
```

## Troubleshooting

### Issue: "No valid resume found in profile database"

**Solution:**
```bash
python3 update_resume.py "/Users/malpari/Downloads/Mustafa_Alp_ARI_Resume_4.pdf"
```

### Issue: "AUTO_APPLY_ENABLED is set to False"

**Solution:** Edit `.env`:
```env
AUTO_APPLY_ENABLED=true
```

### Issue: Jobs still get low scores

**Solution:** 
1. Lower the threshold: `MIN_MATCH_SCORE=50`
2. Configure locations: `PREFERRED_LOCATIONS=Toronto,Remote`
3. Check your profile has skills: `python3 setup_profile.py`

### Issue: Resume file not found

**Solution:** Use absolute path:
```bash
# Find absolute path
realpath ~/Downloads/Mustafa_Alp_ARI_Resume_4.pdf
# Or
readlink -f ~/Downloads/Mustafa_Alp_ARI_Resume_4.pdf

# Then update
python3 update_resume.py "/full/absolute/path/to/resume.pdf"
```

## Advanced: Docker/CI Deployment

```dockerfile
# Dockerfile
FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

# Set environment variables
ENV AUTO_APPLY_ENABLED=true
ENV RESUME_PATH=/app/resume.pdf
ENV PREFERRED_LOCATIONS=Toronto,Canada,Remote

CMD ["python3", "main.py"]
```

## Summary of Fixes

✅ **Automation Fixed:**
- No more manual prompts when `AUTO_APPLY_ENABLED=true`
- Can run unattended in background

✅ **Matching Improved:**
- Location preferences are configurable
- Less aggressive penalties
- Works for any profile (not just CS+Econ)

✅ **Resume Management:**
- Easy update with `update_resume.py`
- Can override via environment variable
- Auto-validates file exists

✅ **Fully Generalizable:**
- No hardcoded locations
- No profile-specific bonuses
- Works for anyone, anywhere

## Need Help?

1. Check logs: `tail -f logs/*.log`
2. Test configuration: Run the tests above
3. Verify .env: `cat .env | grep -v PASSWORD`
4. Check database: `python3 view_applications.py`

---

**For the Original User:**

To update to your new resume, run:
```bash
python3 update_resume.py "/Users/malpari/Downloads/Mustafa_Alp_ARI_Resume_4.pdf"
```

Note: If the file is on your local machine and not in the repository, use the full absolute path. The system will store this path and use it for all future applications.
