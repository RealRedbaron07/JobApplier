"""Fill an employer's application form in a visible Chrome window, then stop.

The final Submit is always yours. This module never clicks a button, never
submits a form, never ticks consent/terms checkboxes, never answers voluntary
demographic questions, and never signs in or creates accounts. It opens the
official application page, uploads the reviewed tailored resume, types your
profile facts into empty fields, highlights what still needs you, and leaves
the window open on the form.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from config import Config

logger = logging.getLogger("job_os.apply_assist")

ATS_HOSTS = {
    "greenhouse": ("greenhouse.io",),
    "lever": ("lever.co",),
    "ashby": ("ashbyhq.com",),
    "workday": ("myworkdayjobs.com", "myworkday.com"),
    "smartrecruiters": ("smartrecruiters.com",),
    "icims": ("icims.com",),
}


def detect_ats(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    for name, suffixes in ATS_HOSTS.items():
        if any(host == suffix or host.endswith("." + suffix) for suffix in suffixes):
            return name
    return "generic"


def application_url(url: str) -> str:
    """Go straight to the form page where the ATS has one, so no Apply button needs clicking."""
    ats = detect_ats(url)
    clean = (url or "").split("#", 1)[0].rstrip("/")
    path = urlparse(clean).path.rstrip("/")
    if ats == "lever" and re.search(r"/[0-9a-f-]{36}$", path):
        return clean + "/apply"
    if ats == "ashby" and re.search(r"/[0-9a-f-]{36}$", path):
        return clean + "/application"
    return clean


def field_values(profile: Dict[str, Any], answers: Dict[str, str] | None = None) -> Dict[str, str]:
    """Canonical form answers drawn only from the saved profile and reviewed answer drafts."""
    answers = answers or {}
    name = (profile.get("name") or "").split()
    education = (profile.get("education") or [{}])[0]
    location = profile.get("location") or ""
    city = location.split(",")[0].strip()
    grad = str(profile.get("graduation") or education.get("expected_graduation") or "")
    grad_year = (re.search(r"20\d{2}", grad) or [""])[0]
    authorization = str(profile.get("work_authorization") or "").lower()
    authorized = "authorized to work" in authorization or "permanent resident" in authorization or "citizen" in authorization
    no_sponsorship = "no sponsorship" in authorization or "not require" in authorization
    return {
        "first_name": name[0] if name else "",
        "last_name": name[-1] if len(name) > 1 else "",
        "full_name": profile.get("name") or "",
        "email": profile.get("email") or "",
        "phone": profile.get("phone") or "",
        "location": location,
        "city": city,
        "province": "Ontario" if re.search(r"\b(ON|Ontario)\b", location) else "",
        "country": "Canada" if "canada" in location.lower() else "",
        "linkedin": profile.get("linkedin") or "",
        "github": profile.get("github") or "",
        "website": profile.get("portfolio") or "",
        "school": education.get("institution") or "",
        "degree": "Bachelor",
        "discipline": "Computer Science" if "computer science" in str(education.get("degree", "")).lower() else str(education.get("degree") or ""),
        "graduation": grad,
        "graduation_year": grad_year,
        "work_authorized": "Yes" if authorized else "",
        "sponsorship": "No" if (authorized and no_sponsorship) else "",
        "cover_letter": answers.get("cover_letter", ""),
    }


# Runs in the page. Sets values on empty fields only, dispatches the events that
# React/Vue forms listen for, and returns a report. Only radio inputs and
# listbox options are ever clicked; buttons, links, and checkboxes never are.
FILL_SCRIPT = r"""
const values = arguments[0];
const report = {filled: [], needs_you: [], skipped_sensitive: [], file_inputs: 0};
const SKIP = /(gender|pronoun|race|ethnic|hispanic|latino|veteran|disabilit|sexual|orientation|transgender|indigenous|aboriginal|visible minority|religio|date of birth|birth ?date|\bage\b|social insurance|\bsin\b|ssn|salary|compensation|pay expectation|password|captcha|signature|consent|agree|terms|privacy|acknowledg|certify|attest)/i;
const RULES = [
  ['sponsorship', /sponsor/i],
  ['work_authorized', /(authori[sz]ed|eligible|entitled|legally able|right|permit(ted)?)\s+to\s+work|work\s+(authori[sz]ation|permit|eligibility)/i],
  ['first_name', /(first|given|preferred)\s*name|^first$/i],
  ['last_name', /(last|family|sur)\s*name|^last$/i],
  ['email', /e-?mail/i],
  ['phone', /phone|mobile|cell/i],
  ['linkedin', /linked\s*in/i],
  ['github', /git\s*hub/i],
  ['website', /website|portfolio|personal (site|url|page)|blog/i],
  ['school', /school|university|college|institution/i],
  ['degree', /degree/i],
  ['discipline', /discipline|major|field of study|program of study|area of study/i],
  ['graduation', /graduat|completion date|expected end|end date.*(school|education)/i],
  ['country', /^country\b|country of residence/i],
  ['province', /province|state\b|region/i],
  ['city', /^city\b|town/i],
  ['location', /location|where are you (based|located)|current address|address/i],
  ['cover_letter', /cover\s*letter/i],
  ['full_name', /^(full |legal |your )?name\b/i],
];
const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
const clean = t => (t || '').replace(/\s+/g, ' ').trim();
function labelText(el) {
  const parts = [];
  if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) parts.push(l.innerText); }
  const wrap = el.closest('label'); if (wrap) parts.push(wrap.innerText);
  const by = el.getAttribute('aria-labelledby');
  if (by) by.split(/\s+/).forEach(id => { const n = document.getElementById(id); if (n) parts.push(n.innerText); });
  parts.push(el.getAttribute('aria-label') || '', el.getAttribute('placeholder') || '');
  let text = clean(parts.join(' '));
  if (text.length < 2) {
    const box = el.closest('fieldset, [role=group], .field, .form-group, .application-question, [class*="field"], [class*="question"], li');
    if (box) text = clean((box.querySelector('legend, label, [class*="label"]') || box).innerText).slice(0, 200);
  }
  if (text.length < 2) text = clean(`${el.name || ''} ${el.id || ''}`.replace(/[_\-\[\]]+/g, ' '));
  return text;
}
function questionText(el) {
  const box = el.closest('fieldset, [role=radiogroup], [role=group], .application-question, [class*="question"], [class*="field"], li');
  if (!box) return labelText(el);
  const head = box.querySelector('legend, label, [class*="label"], [class*="question"]');
  return clean((head || box).innerText).slice(0, 240);
}
// Work-authorization answers in the profile are for Canada only; other countries need you.
const OTHER_COUNTRY = /united states|\bu\.?s\.?a?\b|america|united kingdom|\bu\.?k\.?\b|europe|\beu\b|australia|india|mexico/i;
function keyFor(text) {
  if (!text || SKIP.test(text)) return null;
  for (const [key, rule] of RULES) if (rule.test(text)) {
    if ((key === 'work_authorized' || key === 'sponsorship') && OTHER_COUNTRY.test(text)) return null;
    return key;
  }
  return null;
}
function setNative(el, value) {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  el.dispatchEvent(new Event('blur', {bubbles: true}));
}
function mark(el, color) { try { el.style.outline = `2px solid ${color}`; el.style.outlineOffset = '2px'; } catch (e) {} }
const required = el => el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(labelText(el));
const handledRadios = new Set();

for (const el of document.querySelectorAll('input, textarea, select')) {
  const type = (el.type || '').toLowerCase();
  if (type === 'file') { report.file_inputs++; continue; }
  if (type === 'checkbox') { if (required(el) && !el.checked && visible(el)) { mark(el.closest('label') || el, '#ef6c00'); report.needs_you.push(`Tick yourself: ${labelText(el).slice(0, 110)}`); } continue; }
  if (['hidden', 'submit', 'button', 'reset', 'image', 'checkbox', 'password', 'search'].includes(type) || el.disabled || el.readOnly) continue;
  if (!visible(el) && type !== 'radio') continue;
  if (type === 'radio') {
    if (!el.name || handledRadios.has(el.name)) continue;
    handledRadios.add(el.name);
    const group = [...document.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)];
    const question = questionText(el);
    if (SKIP.test(question)) { report.skipped_sensitive.push(question.slice(0, 120)); continue; }
    const key = keyFor(question);
    const want = key ? values[key] : '';
    if (group.some(r => r.checked)) continue;
    const choice = want && group.find(r => new RegExp('^\\s*' + want + '\\b', 'i').test(labelText(r) || r.value));
    if (choice) { choice.click(); mark(choice.closest('label') || choice, '#2e7d32'); report.filled.push(`${question.slice(0, 80)} → ${want}`); }
    else if (group.some(required)) { mark(el.closest('fieldset, [role=radiogroup], .application-question, [class*="question"]') || el, '#ef6c00'); report.needs_you.push(question.slice(0, 120)); }
    continue;
  }
  const text = labelText(el);
  if (SKIP.test(text)) { if (required(el)) report.skipped_sensitive.push(text.slice(0, 120)); continue; }
  let key = keyFor(text);
  if (!key && type === 'email') key = 'email';
  if (!key && type === 'tel') key = 'phone';
  const want = key ? values[key] : '';
  if (el.tagName === 'SELECT') {
    if (el.selectedIndex > 0 && el.value) continue;
    const options = [...el.options];
    const pick = want && (options.find(o => clean(o.text).toLowerCase() === want.toLowerCase())
      || options.find(o => new RegExp('^\\s*' + want.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'i').test(o.text))
      || (key === 'graduation' && values.graduation_year && options.find(o => o.text.includes(values.graduation_year))));
    if (pick) { el.value = pick.value; el.dispatchEvent(new Event('change', {bubbles: true})); mark(el, '#2e7d32'); report.filled.push(`${text.slice(0, 80)} → ${clean(pick.text)}`); }
    else if (required(el)) { mark(el, '#ef6c00'); report.needs_you.push(text.slice(0, 120)); }
    continue;
  }
  if (clean(el.value)) continue;
  if (want && !(el.getAttribute('role') === 'combobox' && ['work_authorized', 'sponsorship', 'degree', 'school', 'country', 'province'].includes(key))) {
    setNative(el, want); mark(el, '#2e7d32'); report.filled.push(`${text.slice(0, 80)} → ${want.length > 60 ? want.slice(0, 57) + '…' : want}`);
  } else if (required(el)) { mark(el, '#ef6c00'); report.needs_you.push(text.slice(0, 120)); }
}

let banner = document.getElementById('jobapplier-banner');
if (!banner) { banner = document.createElement('div'); banner.id = 'jobapplier-banner'; document.body.prepend(banner); }
banner.setAttribute('style', 'position:sticky;top:0;z-index:2147483647;background:#1b5e20;color:#fff;font:14px/1.4 -apple-system,system-ui,sans-serif;padding:10px 14px;box-shadow:0 2px 6px rgba(0,0,0,.25)');
banner.textContent = `JobApplier filled ${report.filled.length} field(s)` + (values.__resume_uploaded ? ' and attached your tailored resume' : '') +
  `. Green = filled, orange = needs you (${report.needs_you.length}). Check every answer, then press Submit yourself. JobApplier will not submit.`;
return report;
"""

RESUME_INPUT_SCRIPT = r"""
const inputs = [...document.querySelectorAll('input[type=file]')];
const text = el => ((el.closest('label, .field, [class*="field"], [class*="upload"], [class*="question"], div') || el).innerText + ' ' + (el.name || '') + ' ' + (el.id || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
let best = inputs.find(el => /resume|cv|curriculum/.test(text(el)) && !/cover/.test(text(el)));
if (!best) best = inputs.find(el => !/cover|transcript|portfolio/.test(text(el)));
return best || null;
"""

IFRAME_SCRIPT = r"""
for (const frame of document.querySelectorAll('iframe[src]')) {
  if (/greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com|smartrecruiters\.com|icims\.com/i.test(frame.src)) return frame.src;
}
return null;
"""


class ApplyBrowser:
    """One visible Chrome window with its own profile, kept open so you can review and submit."""

    def __init__(self, profile_dir: str | None = None):
        self.profile_dir = profile_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chrome_profile_apply")
        self.lock = threading.RLock()
        self._driver = None

    def driver(self):
        from selenium.common.exceptions import WebDriverException

        with self.lock:
            if self._driver is not None:
                try:
                    _ = self._driver.window_handles
                    return self._driver
                except WebDriverException:
                    self._driver = None
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            options = Options()
            os.makedirs(self.profile_dir, exist_ok=True)
            options.add_argument(f"--user-data-dir={self.profile_dir}")
            options.add_argument("--window-size=1280,1000")
            options.add_argument("--lang=en-CA")
            options.add_experimental_option("detach", True)  # the window outlives this request
            self._driver = webdriver.Chrome(options=options)
            self._driver.set_page_load_timeout(45)
            return self._driver


_browser = ApplyBrowser()


def _wait_for_form(driver, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ready = driver.execute_script("return document.readyState === 'complete' && document.querySelectorAll('input, textarea, select').length > 2")
            if ready:
                return
        except Exception:
            pass
        time.sleep(0.5)


def fill_application(
    job_url: str,
    resume_pdf: str,
    profile: Dict[str, Any],
    answers: Dict[str, str] | None = None,
    refill_current_page: bool = False,
    browser: ApplyBrowser | None = None,
) -> Dict[str, Any]:
    """Open the official application, attach the resume, fill known fields, and stop before Submit."""
    if not Config.STOP_BEFORE_SUBMIT:
        raise RuntimeError("STOP_BEFORE_SUBMIT must stay enabled.")
    browser = browser or _browser
    resume = Path(resume_pdf).resolve()
    if not resume.is_file():
        raise FileNotFoundError("Tailored resume PDF is missing; prepare the package again.")
    target = application_url(job_url)
    ats = detect_ats(target)
    with browser.lock:
        driver = browser.driver()
        if not refill_current_page:
            driver.get(target)
            _wait_for_form(driver)
            embedded = driver.execute_script(IFRAME_SCRIPT)
            if embedded:
                driver.get(embedded)
                ats = detect_ats(embedded)
                _wait_for_form(driver)
        page = driver.current_url
        if ats == "workday" and not refill_current_page:
            return {
                "ats": ats, "page": page, "filled": [], "needs_you": [], "skipped_sensitive": [], "resume_uploaded": False,
                "stopped_before_submit": True,
                "next_step": "Workday needs you to click Apply and sign in (or create your account) yourself. When the 'My Information' step is showing, press 'Fill this page' in JobApplier. Repeat on each step; submit yourself at the end.",
            }
        uploaded = False
        resume_input = driver.execute_script(RESUME_INPUT_SCRIPT)
        if resume_input is not None:
            try:
                resume_input.send_keys(str(resume))
                uploaded = True
                time.sleep(3)  # Lever/Greenhouse parse the upload and may prefill fields; fill after that
            except Exception as exc:  # noqa: BLE001 - report and continue with typed fields
                logger.warning("Resume upload failed: %s", exc)
        values = {**field_values(profile, answers), "__resume_uploaded": uploaded}
        report = driver.execute_script(FILL_SCRIPT, values) or {}
        driver.execute_script("window.scrollTo(0, 0)")
    return {
        "ats": ats,
        "page": page,
        "resume_uploaded": uploaded,
        "resume_file": resume.name,
        "filled": report.get("filled", []),
        "needs_you": report.get("needs_you", []),
        "skipped_sensitive": report.get("skipped_sensitive", []),
        "stopped_before_submit": True,
        "next_step": "Review the form in the JobApplier Chrome window, complete the orange fields, then press Submit yourself. Come back and mark the job applied.",
    }
