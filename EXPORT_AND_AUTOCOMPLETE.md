# Export & Auto-Complete Features

## 📊 Export Applications to Table

Export all your applications to a CSV file for easy viewing and analysis.

### Usage

```bash
# Full export with all details
python3 export_applications.py

# Summary table (key info only)
python3 export_applications.py --summary

# Custom filename
python3 export_applications.py my_applications.csv
```

### What's Exported

**Full Export Includes:**
- Application Date
- Job Title, Company, Location
- Platform (LinkedIn, Indeed, etc.)
- Job URL
- Match Score
- Application Status
- Application Method
- Resume Used (path)
- Cover Letter (path)
- Tailored Resume (path)
- Response Received (Yes/No)
- Response Date
- Interview Date
- Follow-up Date
- Offer Details
- Notes

**Summary Export Includes:**
- Date Applied
- Days Since Application
- Job Title, Company, Location
- Status
- Response (Yes/No)
- Interview (Yes/No)
- Match Score
- URL

### Example Output

The CSV file can be opened in:
- Excel
- Google Sheets
- Numbers (Mac)
- Any spreadsheet application

**File Location:**
- Saved in project root directory
- Filename: `applications_export_YYYYMMDD_HHMMSS.csv`
- Or custom filename if specified

---

## ⏱️ Auto-Complete Applications

Automatically mark applications as "completed" if there's no response within 2 hours.

### How It Works

1. **When you apply:**
   - Each application gets a follow-up date set to 2 hours from application time
   - Status is tracked as 'submitted' or 'pending'

2. **After 2 hours:**
   - Run auto-complete to mark applications with no response as 'completed'
   - Keeps your application list clean and organized

### Usage

```bash
# Check pending applications
python3 auto_complete_applications.py

# Or explicitly check
python3 auto_complete_applications.py --check

# Auto-complete applications pending 2+ hours
python3 auto_complete_applications.py --auto-complete

# Auto-complete with custom threshold (e.g., 3 hours)
python3 auto_complete_applications.py --auto-complete 3
```

### What Happens

**When checking:**
- Shows all pending applications
- Shows how long each has been pending
- Highlights applications over 2 hours

**When auto-completing:**
- Finds applications pending 2+ hours with no response
- Shows what will be updated
- Asks for confirmation
- Marks them as 'completed' status
- Adds note: "Auto-completed - No response within X hours"

### Status Flow

```
submitted/pending → (2 hours, no response) → completed
```

**Note:** If you get a response, you can manually update the status to:
- `interview` - If you get an interview
- `rejected` - If rejected
- `offer` - If you get an offer
- etc.

---

## 🔄 Complete Workflow

### Daily/Weekly Routine

```bash
# 1. Apply to jobs
python3 apply_jobs.py

# 2. Check pending applications (optional)
python3 auto_complete_applications.py --check

# 3. Auto-complete old applications (optional)
python3 auto_complete_applications.py --auto-complete

# 4. Export to table for review
python3 export_applications.py --summary

# 5. View in spreadsheet application
# Open the CSV file in Excel/Sheets
```

### Benefits

✅ **Clean Tracking:**
- Applications automatically marked after 2 hours
- No manual cleanup needed
- Clear status at a glance

✅ **Easy Analysis:**
- Export to CSV for spreadsheet analysis
- Filter, sort, and analyze in Excel/Sheets
- Track success rates, response times, etc.

✅ **Complete Records:**
- All application details exported
- Resume paths, cover letters, tailored resumes
- Full history of each application

---

## 📈 Use Cases

### Track Application Success

1. Export applications monthly
2. Analyze in spreadsheet:
   - Response rate
   - Average response time
   - Best performing job titles/companies
   - Match score vs. response rate

### Follow-Up Reminders

1. Export applications
2. Filter by status = 'pending'
3. Sort by application date
4. Follow up on old applications

### Resume Optimization

1. Export applications
2. Compare which resumes got responses
3. Identify best-performing resume versions
4. Use insights for future applications

---

## Tips

1. **Regular Exports:**
   - Export weekly or monthly
   - Keep historical records
   - Track trends over time

2. **Auto-Complete:**
   - Run daily or weekly
   - Keeps list manageable
   - Focus on active applications

3. **Status Updates:**
   - Update status when you get responses
   - Use `view_applications.py --update`
   - Keep records accurate

4. **Backup:**
   - Export regularly
   - Keep CSV files as backup
   - Never lose application history

