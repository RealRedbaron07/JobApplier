#!/usr/bin/env python3
"""LinkedIn Easy Apply automation - stops before final submit."""
import sys, os, json, time, random
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Load from .env - no hardcoded creds
EMAIL = os.getenv('LINKEDIN_EMAIL', '')
PASSWORD = os.getenv('LINKEDIN_PASSWORD', '')
LOG_FILE = os.path.join(os.path.dirname(__file__), 'jobs_log.json')

if not EMAIL or not PASSWORD:
    print("Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env")
    sys.exit(1)

print("Starting LinkedIn automation...", flush=True)

os.environ['SSL_CERT_FILE'] = __import__('certifi').where()
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# Internship-focused searches
SEARCHES = [
    ("Software Engineering Intern 2026", "Remote"),
    ("Software Engineering Intern", "Toronto"),  
    ("Software Developer Intern", "Canada"),
    ("Data Science Intern 2026", "Remote"),
]

# Filter keywords - only apply to relevant jobs
MUST_HAVE = ['intern', 'internship', 'co-op', 'student', 'summer 2026', 'summer 2025']
AVOID = ['senior', 'lead', 'manager', 'director', '5+ years', '7+ years', '10+', 'principal', 'staff engineer']

def is_relevant(title):
    """Check if job title is relevant for internship search."""
    t = title.lower()
    # Must contain internship keyword
    if not any(k in t for k in MUST_HAVE):
        return False
    # Avoid senior roles
    if any(k in t for k in AVOID):
        return False
    return True

def log_job(job):
    jobs = json.load(open(LOG_FILE)) if os.path.exists(LOG_FILE) else []
    jobs.append({**job, "timestamp": datetime.now().isoformat()})
    json.dump(jobs, open(LOG_FILE, 'w'), indent=2)

def p(m): print(m, flush=True)

def main():
    p("Launching Chrome...")
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--start-maximized')
    driver = uc.Chrome(options=options, version_main=144, use_subprocess=True)
    time.sleep(2)
    
    p("Logging into LinkedIn...")
    driver.get("https://www.linkedin.com/login")
    time.sleep(4)
    
    if "feed" not in driver.current_url:
        driver.find_element(By.ID, "username").send_keys(EMAIL)
        driver.find_element(By.ID, "password").send_keys(PASSWORD + Keys.RETURN)
        time.sleep(8)
        if "checkpoint" in driver.current_url or "challenge" in driver.current_url:
            p("2FA required - complete in browser, waiting 45s...")
            time.sleep(45)
    
    p("Logged in!\n")
    
    total_processed = 0
    
    for search_title, loc in SEARCHES:
        p(f"\n=== Searching: {search_title} | {loc} ===")
        # f_AL=true = Easy Apply only, f_E=1 = Entry level/Intern
        url = f"https://www.linkedin.com/jobs/search/?keywords={search_title.replace(' ', '%20')}&location={loc.replace(' ', '%20')}&f_TPR=r604800&f_AL=true&f_E=1&sortBy=DD"
        driver.get(url)
        time.sleep(4)
        driver.execute_script("window.scrollTo(0, 800);")
        time.sleep(2)
        
        links = driver.find_elements(By.XPATH, "//a[contains(@href, '/jobs/view/')]")
        seen = set()
        count = 0
        
        for link in links:
            if count >= 10: break
            try:
                href = link.get_attribute("href")
                if not href or href in seen: continue
                seen.add(href)
                
                link.click()
                time.sleep(2)
                
                try:
                    job_title = driver.find_element(By.CSS_SELECTOR, "h1.t-24, h2.t-24, .jobs-unified-top-card__job-title").text[:60]
                except:
                    continue
                
                # FILTER: Skip irrelevant jobs
                if not is_relevant(job_title):
                    p(f"  [SKIP] {job_title[:40]} - not internship")
                    continue
                
                try:
                    company = driver.find_element(By.CSS_SELECTOR, ".jobs-unified-top-card__company-name").text[:30]
                except:
                    company = "?"
                
                easy_btn = driver.find_elements(By.XPATH, "//button[contains(@class, 'jobs-apply-button') and contains(., 'Easy Apply')]")
                
                if easy_btn:
                    p(f"  [APPLY] {job_title[:40]} @ {company}")
                    easy_btn[0].click()
                    time.sleep(2)
                    
                    # Navigate form - STOP at final submit
                    for step in range(8):
                        submit_btn = driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Submit application')]")
                        if submit_btn:
                            p(f"      >> READY - click Submit manually!")
                            log_job({"title": job_title, "company": company, "url": href, "status": "ready"})
                            count += 1
                            total_processed += 1
                            time.sleep(2)
                            # Close modal to continue
                            dismiss = driver.find_elements(By.CSS_SELECTOR, "button[aria-label='Dismiss']")
                            if dismiss: dismiss[0].click()
                            break
                        
                        next_btn = driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Continue') or contains(@aria-label, 'Next') or contains(@aria-label, 'Review')]")
                        if next_btn:
                            next_btn[0].click()
                            time.sleep(1.5)
                            continue
                        
                        # Missing required fields
                        if driver.find_elements(By.CSS_SELECTOR, "[data-test-form-element-error]"):
                            p(f"      [!] Missing fields - skipping")
                            dismiss = driver.find_elements(By.CSS_SELECTOR, "button[aria-label='Dismiss']")
                            if dismiss: dismiss[0].click()
                            break
                        
                        time.sleep(1)
                else:
                    p(f"  [EXT] {job_title[:40]} - opening tab")
                    driver.execute_script(f"window.open('{href}', '_blank');")
                    log_job({"title": job_title, "company": company, "url": href, "status": "external"})
                    count += 1
                    total_processed += 1
                    
            except Exception as e:
                continue
    
    p(f"\n{'='*50}")
    p(f"Done! Processed {total_processed} internship jobs.")
    p("Check browser - click Submit on ready applications.")
    p("="*50)
    
    while True:
        try:
            driver.current_url
            time.sleep(10)
        except:
            break

if __name__ == "__main__":
    main()
