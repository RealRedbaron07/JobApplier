# Workday Support & How It Works

## Current Status: ⚠️ **Partial Support**

The system **does NOT have a direct Workday scraper**, but it can still help you with Workday applications in several ways.

## What Works with Workday

### ✅ 1. Job Discovery
**How it works:**
- Many companies post jobs on LinkedIn/Indeed/Glassdoor that redirect to Workday
- The system finds these jobs and extracts the Workday URL
- You get the job listing with the Workday application link

**Example:**
```
Job found on LinkedIn → "Apply on Company Website" → Links to Workday
System saves: job_url = "https://company.wd1.myworkdayjobs.com/..."
```

### ✅ 2. Material Generation
**What you get:**
- Personalized cover letter for the Workday job
- Tailored resume highlighting relevant skills
- All materials ready before you apply

**Usage:**
```bash
python3 apply_jobs.py
# System generates cover letter and tailored resume
# Provides Workday URL with ready materials
```

### ✅ 3. Application Tracking
**Complete tracking:**
- Records which resume/cover letter was used
- Tracks application status
- Records responses and interviews
- Exports to CSV for analysis

### ✅ 4. Manual Application Support
**Workflow:**
1. System finds job (even if it redirects to Workday)
2. Generates cover letter and tailored resume
3. Provides Workday URL
4. You apply manually on Workday
5. System tracks everything

## What Doesn't Work

### ❌ Direct Auto-Apply on Workday
**Why:**
- Workday has complex forms with multiple steps
- Requires account creation/login
- Has CAPTCHA and security measures
- Each company's Workday portal is different

**Current limitation:**
- No automated form filling
- No automated file upload
- No automated submission

## How to Use with Workday Jobs

### Method 1: Find Jobs via Other Platforms

```bash
# 1. Search for jobs (finds jobs that link to Workday)
python3 main.py

# 2. Review jobs
python3 review_ui.py
# Jobs with Workday URLs will show as "external_site"

# 3. Apply (generates materials, provides Workday link)
python3 apply_jobs.py
# Output: "Manual application required"
#         "→ Visit: https://company.wd1.myworkdayjobs.com/..."
#         "→ Cover letter: cover_letters/..."
#         "→ Tailored resume: tailored_resumes/..."
```

### Method 2: Manual Job Entry (Future Feature)

You could manually add Workday jobs to the database, but this feature isn't built yet.

## Workday Application Process

### Typical Workday Flow:

1. **Click Apply** → Redirects to Workday
2. **Create Account / Login** → Workday account required
3. **Fill Application Form** → Multiple pages
4. **Upload Resume** → Use tailored resume from system
5. **Upload Cover Letter** → Use generated cover letter
6. **Answer Questions** → Company-specific questions
7. **Submit** → Application complete

### How System Helps:

✅ **Before applying:**
- Cover letter ready (copy/paste or upload)
- Tailored resume ready (upload)
- Job details saved

✅ **After applying:**
- Application tracked in database
- Status can be updated
- Responses tracked
- Exported to CSV

## Example Workflow

```bash
# Step 1: Find jobs (some will be Workday)
python3 main.py
# Output: "Found 15 jobs"
#         "• Software Engineer at TechCorp - Score: 75"
#         "  URL: https://techcorp.wd1.myworkdayjobs.com/..."

# Step 2: Review
python3 review_ui.py
# See job with Workday URL

# Step 3: Apply
python3 apply_jobs.py
# Output:
# "Processing: Software Engineer at TechCorp"
# "✓ Cover letter: cover_letters/20241215_TechCorp_Software_Engineer.txt"
# "✓ Tailored resume: tailored_resumes/20241215_TechCorp_Software_Engineer_Resume.docx"
# "ℹ️  Manual application required"
# "→ Visit: https://techcorp.wd1.myworkdayjobs.com/..."

# Step 4: Apply on Workday
# - Open the URL
# - Upload tailored resume
# - Copy/paste cover letter
# - Fill form
# - Submit

# Step 5: Track
python3 view_applications.py
# Application recorded as "pending" (manual)
```

## Future: Workday Scraper (Possible but Complex)

### Why It's Difficult:

1. **Account Required:**
   - Each company has different Workday portal
   - Need to create account per company
   - Login credentials needed

2. **Complex Forms:**
   - Multi-step application process
   - Dynamic form fields
   - Company-specific questions

3. **Security:**
   - CAPTCHA protection
   - Bot detection
   - Rate limiting

4. **Variability:**
   - Each company's Workday is customized
   - Different form structures
   - Different required fields

### What Would Be Needed:

- Workday scraper class
- Account management per company
- Form field detection
- Dynamic form filling
- File upload automation
- CAPTCHA handling (if possible)

## Current Best Practice

### Recommended Workflow:

1. **Use system for discovery:**
   - Find jobs on LinkedIn/Indeed/Glassdoor
   - Even if they redirect to Workday

2. **Use system for materials:**
   - Generate cover letters
   - Tailor resumes
   - Get everything ready

3. **Apply manually on Workday:**
   - Use provided materials
   - Fill form manually
   - Submit application

4. **Track in system:**
   - Update status when you apply
   - Track responses
   - Export for analysis

## Summary

**✅ What Works:**
- Finding Workday jobs via other platforms
- Generating cover letters and tailored resumes
- Providing Workday URLs
- Tracking applications
- Exporting to CSV

**❌ What Doesn't Work:**
- Direct auto-apply on Workday
- Automated form filling
- Automated file upload

**💡 Best Approach:**
Use the system to find jobs and prepare materials, then apply manually on Workday. The system still tracks everything and provides all the materials you need!

