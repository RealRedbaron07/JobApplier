# 📤 Push to GitHub - Step by Step

## Step 1: Create Repository on GitHub

1. Go to https://github.com/new
2. Repository name: `JobApplier` (or whatever you want)
3. Description: "Automated job application bot with AI-powered cover letters and resume tailoring"
4. Choose: **Private** (recommended - contains your resume and job data)
5. **DO NOT** check "Initialize with README" (we already have files)
6. Click "Create repository"

---

## Step 2: Connect and Push

After creating the repo, GitHub will show you commands. Use these:

```bash
# Make sure you're in the project directory
cd /Users/malpari/Desktop/JobApplier

# Add all files (respects .gitignore)
git add .

# Create initial commit
git commit -m "Initial commit: Automated job application bot"

# Add your GitHub repo (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/JobApplier.git

# Push to GitHub
git branch -M main
git push -u origin main
```

---

## What Gets Pushed

✅ **Included:**
- All Python code
- README and documentation
- Configuration files
- Scraper modules
- Database models

❌ **Excluded (via .gitignore):**
- `.env` file (your API keys, passwords)
- `job_applications.db` (your database)
- Generated cover letters
- Generated resumes
- Python cache files

**Your sensitive data stays local!**

---

## After Pushing

Your repo will be on GitHub with:
- ✅ All code
- ✅ Documentation
- ✅ Setup instructions
- ❌ No sensitive data (protected by .gitignore)

---

## Quick Copy-Paste

```bash
cd /Users/malpari/Desktop/JobApplier
git add .
git commit -m "Initial commit: Automated job application bot"
git remote add origin https://github.com/YOUR_USERNAME/JobApplier.git
git branch -M main
git push -u origin main
```

**Replace `YOUR_USERNAME` with your actual GitHub username!**

---

## If You Need to Update Later

```bash
git add .
git commit -m "Your commit message"
git push
```

---

## Security Note

The `.gitignore` file ensures:
- ✅ Your `.env` file (with API keys) is NOT uploaded
- ✅ Your database (with job data) is NOT uploaded
- ✅ Generated files are NOT uploaded
- ✅ Only code and documentation are uploaded

**Always check `.gitignore` before pushing!**

