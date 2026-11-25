"""Fill an employer's application form in a visible Chrome window, then stop.

The final Submit is always yours. This module never clicks a button, never
submits a form, never ticks consent/terms checkboxes, never answers voluntary
demographic questions, and never signs in or creates accounts. It opens the
official application page, uploads the reviewed tailored resume, types your
profile facts into empty fields, highlights what still needs you, and leaves
the window open on the form.
"""

from __future__ import annotations

import json
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


def _employers(profile: Dict[str, Any]) -> list[str]:
    resume = profile.get("resume") or {}
    names = []
    for section in ("experience", "leadership"):
        for entry in resume.get(section, []):
            company = str(entry.get("company") or "")
            names += [part.strip().lower() for part in re.split(r"[,/&]| at ", company) if len(part.strip()) > 2]
    return names


def field_values(profile: Dict[str, Any], answers: Dict[str, str] | None = None,
                 job: Dict[str, Any] | None = None) -> Dict[str, str]:
    """Canonical form answers drawn only from the saved profile and reviewed answer drafts."""
    answers = answers or {}
    job = job or {}
    name = (profile.get("name") or "").split()
    education = (profile.get("education") or [{}])[0]
    location = profile.get("location") or ""
    city = location.split(",")[0].strip()
    grad = str(profile.get("graduation") or education.get("expected_graduation") or "")
    grad_year = (re.search(r"20\d{2}", grad) or [""])[0]
    authorization = str(profile.get("work_authorization") or "").lower()
    authorized = "authorized to work" in authorization or "permanent resident" in authorization or "citizen" in authorization
    no_sponsorship = "no sponsorship" in authorization or "not require" in authorization
    relocation = str(profile.get("relocation") or "").lower()
    company = str(job.get("company") or "").strip().lower()
    # "No" only when the company is clearly not one the resume lists; otherwise you answer.
    worked_here = bool(company) and any(company in employer or employer in company for employer in _employers(profile))
    current = next((entry for entry in (profile.get("resume") or {}).get("experience", [])
                    if re.search(r"present|current", str(entry.get("dates", "")), re.I)), {})
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
        "relocate": "Yes" if relocation.startswith("open") or "willing" in relocation else "",
        "student": "Yes" if grad_year and education.get("institution") else "",
        "previously_employed": "No" if company and not worked_here else "",
        "current_company": current.get("company", ""),
        "current_title": current.get("title", ""),
        "how_heard": "Company website",
        "company": str(job.get("company") or "").strip(),
        "availability": answers.get("availability", ""),
        "cover_letter": answers.get("cover_letter", ""),
        "why_company": answers.get("why_company", ""),
        "why_role": answers.get("why_role", ""),
        "about_you": answers.get("tell_us_about_yourself", ""),
    }


# Runs in the page. Sets values on empty fields only, dispatches the events that
# React/Vue forms listen for, and returns a report. Only radio inputs and
# listbox options are ever clicked; buttons, links, and checkboxes never are.
# Voluntary self-identification questions get the "decline to answer" option
# when the form offers one, so they never reveal anything about you.
FILL_SCRIPT = r"""
const values = arguments[0];
const report = {filled: [], needs_you: [], skipped_sensitive: [], file_inputs: 0, combos: 0};
const VOLUNTARY = /(gender|pronoun|race|which categories describe you|ethnic|hispanic|latin[oax]|veteran|disabilit|sexual|orientation|transgender|indigenous|aboriginal|first nations|visible minority|racializ|lgbt)/i;
const SKIP = /(religio|date of birth|birth ?date|\bage\b|social insurance|\bsin\b|ssn|salary|compensation|pay expectation|password|captcha|signature|consent|agree|terms|privacy|acknowledg|certify|attest|criminal|convict)/i;
const DECLINE = /(decline|prefer not|don.?t wish|do not wish|choose not|not wish to|rather not|not to (answer|disclose|say|self|identify)|i don.?t want)/i;
const RULES = [
  ['sponsorship', /sponsor/i],
  ['work_authorized', /(authori[sz]ed|eligible|entitled|legally able|right|permit(ted)?)\s+to\s+work|work\s+(authori[sz]ation|permit|eligibility)/i],
  ['previously_employed', /(previously|ever|currently|formerly|before)\s+(been\s+)?(work(ed)?|employed|an? employee)|(former|past|current) (employee|intern) (of|at)|worked (for|at) (us|this company)/i],
  ['relocate', /relocat/i],
  ['student', /(currently|presently) (enrolled|a student|attending|pursuing)|are you (a )?(current )?student/i],
  ['how_heard', /how did you (hear|find|learn)|where did you (hear|find|see)|referral source|source of (application|referral)/i],
  ['availability', /when (can|could|would) you start|start date|earliest (start|availability)|availability|available to start/i],
  ['why_company', /why .{0,40}(join|work (for|at|with)|interest(ed)? in|apply(ing)? (to|at|for|with))|why (us|here)\b|what (interests|excites|attracts|draws) you/i],
  ['why_role', /why .{0,40}(this|the) (role|position|internship|co-?op)/i],
  ['about_you', /tell us (a bit |a little )?about yourself|introduce yourself/i],
  ['current_company', /current (company|employer|organi[sz]ation)|^(company|employer)\b/i],
  ['current_title', /current (job )?(title|role|position)/i],
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
const LONG_ONLY = new Set(['why_company', 'why_role', 'about_you', 'cover_letter']);
const YES_NO = new Set(['sponsorship', 'work_authorized', 'previously_employed', 'relocate', 'student']);
// React dropdowns keep a 1px, transparent "required" input next to the real one: never fill that.
const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.05 && el.getAttribute('aria-hidden') !== 'true'; };
const clean = t => (t || '').replace(/\s+/g, ' ').trim();
const esc = t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function labelText(el) {
  const parts = [];
  if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) parts.push(l.innerText); }
  const wrap = el.closest('label'); if (wrap) parts.push(wrap.innerText);
  const by = el.getAttribute('aria-labelledby');
  if (by) by.split(/\s+/).forEach(id => { const n = document.getElementById(id); if (n) parts.push(n.innerText); });
  parts.push(el.getAttribute('aria-label') || '');
  if (!clean(parts.join(''))) parts.push(el.getAttribute('placeholder') || '');
  const seen = new Set();
  const norm = p => p.toLowerCase().replace(/[^a-z0-9]+/g, '');
  let text = clean(parts.map(clean).filter(p => p && !seen.has(norm(p)) && seen.add(norm(p))).join(' '));
  if (text.length < 2 || /^(select|choose|start typing|search)\b/i.test(text)) {
    const box = el.closest('fieldset, [role=group], .field, .form-group, .application-question, [class*="field"], [class*="question"], li');
    if (box) text = clean((box.querySelector('legend, label, [class*="label"]') || box).innerText).slice(0, 200);
  }
  if (text.length < 2) text = clean(`${el.name || ''} ${el.id || ''}`.replace(/[_\-\[\]]+/g, ' '));
  return text;
}
function questionText(el) {
  if (el.type === 'radio' && el.name) {
    let group = el.parentElement;
    while (group && group !== document.body && group.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`).length < 2) group = group.parentElement;
    const legend = group && group.querySelector('legend');
    let first = legend ? clean(legend.innerText) : '';
    // The group's own text without the option labels is the question; some forms put it one level up.
    for (let up = 0, node = group; !first && node && node !== document.body && up < 4; up++, node = node.parentElement) {
      const copy = node.cloneNode(true);
      copy.querySelectorAll('label, input, [role=radio], select, textarea').forEach(n => n.remove());
      first = clean(copy.textContent);
    }
    if (first) return first.slice(0, 240);
  }
  const box = el.closest('fieldset, [role=radiogroup], [role=group], .application-question, [class*="question"], [class*="field"], li');
  if (!box) return labelText(el);
  const head = box.querySelector('legend, label, [class*="label"], [class*="question"]');
  return clean((head || box).innerText).slice(0, 240);
}
// Work-authorization answers in the profile are for Canada only; other countries need you.
const OTHER_COUNTRY = /united states|\bu\.?s\.?a?\b|america|united kingdom|\bu\.?k\.?\b|europe|\beu\b|australia|india|mexico/i;
const PLACE = new Set(['location', 'city', 'province', 'country']);
const QUESTION = /\b(can|could|will|would|are|do|did|have|is)\s+you\b|\bcommit\b/i;
function keyFor(text, long) {
  if (!text || SKIP.test(text) || VOLUNTARY.test(text)) return null;
  for (const [key, rule] of RULES) if (rule.test(text)) {
    if (PLACE.has(key) && (QUESTION.test(text) || (text.length > 90 && !/not in the u/i.test(text)))) continue;
    if ((key === 'work_authorized' || key === 'sponsorship') && OTHER_COUNTRY.test(text)) return null;
    if (LONG_ONLY.has(key) && !long) continue;
    return key;
  }
  return null;
}
// Matcher for an option label: Yes/No answers match the start, voluntary questions match "decline".
function matcher(key, want) {
  if (key === '__decline') return DECLINE;
  if (key === 'how_heard') return new RegExp('(company|career|corporate)\\s*(web)?\\s*(site|page)|^website|' + (values.company ? esc(values.company) + '.{0,3}s? (web)?site|' : '') + 'careers? (site|page)', 'i');
  if (key === 'province') return new RegExp('^\\s*' + esc(want) + '\\b|not in the (us|u\\.s|united states)|outside (the )?(us|u\\.s|united states)|non-u\\.?s', 'i');
  if (key === 'country') return new RegExp('^\\s*' + esc(want) + '\\b', 'i');
  if (YES_NO.has(key)) return new RegExp('^\\s*' + esc(want) + '\\b', 'i');
  if (key === 'graduation') return new RegExp(esc(values.graduation_year || want), 'i');
  return new RegExp('^\\s*' + esc(want) + '\\b|\\b' + esc(want) + '\\b', 'i');
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
const isCombo = el => el.getAttribute('role') === 'combobox' || /select__input|react-select/.test(el.className + ' ' + (el.id || ''));
const handledRadios = new Set();
const handledChecks = new Set();

for (const el of document.querySelectorAll('input, textarea, select')) {
  const type = (el.type || '').toLowerCase();
  if (type === 'file') { report.file_inputs++; continue; }
  if (type === 'checkbox') {
    if (!visible(el)) continue;
    const box = el.closest('fieldset, [role=group], .application-question, [class*="question"], [class*="field"]');
    const question = box ? clean((box.querySelector('legend, label, [class*="label"]') || box).innerText).slice(0, 200) : labelText(el);
    const group = box ? [...box.querySelectorAll('input[type=checkbox]')] : [el];
    if (handledChecks.has(question) || group.some(c => c.checked)) { handledChecks.add(question); continue; }
    handledChecks.add(question);
    // Only "how did you hear about us" is ever ticked; consent, terms and everything else stay yours.
    if (group.length > 1 && keyFor(question, false) === 'how_heard') {
      const rule = matcher('how_heard', values.how_heard);
      const pick = group.find(c => rule.test(clean(labelText(c))));
      if (pick) { pick.click(); mark(pick.closest('label') || pick, '#2e7d32'); report.filled.push(`${question.slice(0, 80)} → ${clean(labelText(pick))}`); continue; }
    }
    if (group.some(required)) { mark(box || el.closest('label') || el, '#ef6c00'); report.needs_you.push(`Tick yourself: ${(group.length > 1 ? question : labelText(el)).slice(0, 110)}`); }
    continue;
  }
  if (['hidden', 'submit', 'button', 'reset', 'image', 'checkbox', 'password', 'search'].includes(type) || el.disabled || el.readOnly) continue;
  if (!visible(el) && type !== 'radio') continue;
  if (type === 'radio') {
    if (!el.name || handledRadios.has(el.name)) continue;
    handledRadios.add(el.name);
    const group = [...document.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)];
    const question = questionText(el);
    if (group.some(r => r.checked)) continue;
    if (SKIP.test(question)) { report.skipped_sensitive.push(question.slice(0, 120)); continue; }
    const optionText = group.map(r => clean(labelText(r))).join(' | ');
    // Lever-style surveys: the options themselves show it is a self-identification question.
    const voluntary = VOLUNTARY.test(question) || (!keyFor(question, false) && group.some(r => DECLINE.test(clean(labelText(r))))
      && /\b(woman|man|non-binary|hispanic|latin|asian|black|white|indigenous|veteran|disab)/i.test(optionText));
    const key = voluntary ? '__decline' : keyFor(question, false);
    const want = key === '__decline' ? 'decline' : key ? values[key] : '';
    const choice = want && group.find(r => matcher(key, want).test(clean(labelText(r)) || r.value));
    if (choice) { choice.click(); mark(choice.closest('label') || choice, '#2e7d32'); report.filled.push(`${question.slice(0, 80)} → ${voluntary ? 'Decline to answer' : want}`); }
    else if (voluntary) report.skipped_sensitive.push(question.slice(0, 120));
    else if (group.some(required)) { mark(el.closest('fieldset, [role=radiogroup], .application-question, [class*="question"]') || el, '#ef6c00'); report.needs_you.push(question.slice(0, 120)); }
    continue;
  }
  const text = labelText(el);
  if (SKIP.test(text)) { if (required(el)) report.skipped_sensitive.push(text.slice(0, 120)); continue; }
  const voluntary = VOLUNTARY.test(text);
  let key = voluntary ? '__decline' : keyFor(text, el.tagName === 'TEXTAREA');
  if (!key && type === 'email') key = 'email';
  if (!key && type === 'tel') key = 'phone';
  const want = key === '__decline' ? 'decline' : key ? values[key] : '';
  if (el.tagName === 'SELECT') {
    if (el.selectedIndex > 0 && el.value) continue;
    const options = [...el.options].filter(o => o.value !== '' || o.index > 0);
    let pick = want && (options.find(o => clean(o.text).toLowerCase() === want.toLowerCase()) || options.find(o => matcher(key, want).test(clean(o.text))));
    if (!pick && PLACE.has(key) && values.country) pick = options.find(o => clean(o.text).toLowerCase() === values.country.toLowerCase());
    if (pick) { el.value = pick.value; el.dispatchEvent(new Event('change', {bubbles: true})); mark(el, '#2e7d32'); report.filled.push(`${text.slice(0, 80)} → ${clean(pick.text)}`); }
    else if (voluntary) report.skipped_sensitive.push(text.slice(0, 120));
    else if (required(el)) { mark(el, '#ef6c00'); report.needs_you.push(text.slice(0, 120)); }
    continue;
  }
  if (isCombo(el)) {
    // Searchable dropdowns (react-select and friends) are picked in a second, async step.
    const box = el.closest('[class*="select__control"], [class*="container"], [class*="field"]') || el.parentElement;
    const shown = box && box.querySelector('[class*="single-value"], [class*="singleValue"], [class*="multi-value"]');
    if ((shown && clean(shown.innerText)) || clean(el.value)) continue;
    if (want) {
      const search = key === 'location' || key === 'city' ? values.city : ['__decline', 'how_heard', 'province'].includes(key) || YES_NO.has(key) ? '' : want;
      el.setAttribute('data-jobapplier-combo', JSON.stringify({search,
        match: (key === 'location' ? new RegExp('^\\s*' + esc(values.city) + '\\b', 'i') : matcher(key, want)).source, label: text.slice(0, 80), shown: key === '__decline' ? 'Decline to answer' : want, required: required(el), voluntary}));
      report.combos++;
    } else if (required(el)) { mark(el, '#ef6c00'); report.needs_you.push(text.slice(0, 120)); }
    continue;
  }
  if (clean(el.value)) continue;
  if (want && key !== '__decline') {
    setNative(el, want); mark(el, '#2e7d32'); report.filled.push(`${text.slice(0, 80)} → ${want.length > 60 ? want.slice(0, 57) + '…' : want}`);
  } else if (voluntary) { report.skipped_sensitive.push(text.slice(0, 120)); }
  else if (required(el)) { mark(el, '#ef6c00'); report.needs_you.push(text.slice(0, 120)); }
}
report.needs_you = [...new Set(report.needs_you.filter(Boolean))];
return report;
"""

COMBO_OPTIONS_SCRIPT = r"""
// Options of one open dropdown, looked up inside its own container (other menus may be open too).
const el = arguments[0];
const box = el.closest('[class*="select__container"], [class*="select-shell"], [class*="container"], [class*="field"]') || el.parentElement;
const owned = el.getAttribute('aria-controls') && document.getElementById(el.getAttribute('aria-controls'));
const pool = owned ? owned.querySelectorAll('[role=option]') : box.querySelectorAll('[role=option], [class*="select__option"]');
return [...pool].filter(o => o.getBoundingClientRect().height > 0);
"""


def _js_regex(source: str) -> "re.Pattern[str]":
    """The page's matcher pattern in Python (only simple, compatible syntax is generated)."""
    return re.compile(source, re.I)


def fill_dropdowns(driver, wait: float = 3.0) -> Dict[str, list]:
    """Open each marked searchable dropdown with real input, type the search, and pick the option.

    Native clicks and keys are used because React dropdowns ignore synthetic events. Only list
    options are clicked; nothing else on the page is.
    """
    from selenium.webdriver.common.keys import Keys

    report: Dict[str, list] = {"filled": [], "needs_you": [], "skipped_sensitive": []}
    for el in driver.find_elements("css selector", "[data-jobapplier-combo]"):
        try:
            spec = json.loads(el.get_attribute("data-jobapplier-combo"))
            driver.execute_script("arguments[0].removeAttribute('data-jobapplier-combo'); arguments[0].scrollIntoView({block: 'center'});", el)
            rule = _js_regex(spec["match"])
            # Keyboard input opens React dropdowns and cannot be intercepted by an overlapping menu or label.
            driver.execute_script("document.activeElement && document.activeElement.blur(); arguments[0].focus()", el)
            el.send_keys(Keys.ARROW_DOWN)
            if spec.get("search"):
                el.send_keys(spec["search"])
            choice = None
            deadline = time.time() + wait
            while time.time() < deadline and choice is None:
                time.sleep(0.3)
                options = driver.execute_script(COMBO_OPTIONS_SCRIPT, el) or []
                if not options and not spec.get("search"):
                    try:
                        el.click()  # some dropdowns open only on a press, not from the keyboard
                    except Exception:  # noqa: BLE001
                        el.send_keys(Keys.ARROW_DOWN)
                    continue
                texts = [(option, " ".join((option.text or "").split())) for option in options]
                wanted = (spec.get("search") or spec.get("shown") or "").lower()
                choice = next((o for o, t in texts if t.lower() == wanted), None) or next((o for o, t in texts if rule.search(t)), None)
                if choice is not None:
                    picked = " ".join(choice.text.split())
                    driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'})", choice)
                    try:
                        choice.click()
                    except Exception:  # noqa: BLE001 - option hidden under something: pick it from the keyboard
                        index = options.index(choice)
                        for _ in range(index):
                            el.send_keys(Keys.ARROW_DOWN)
                        el.send_keys(Keys.ENTER)
            if choice is not None:
                report["filled"].append(f"{spec['label']} → {'Decline to answer' if spec.get('voluntary') else picked}")
            else:
                if spec.get("search"):
                    el.send_keys(Keys.CONTROL, "a")
                    el.send_keys(Keys.BACKSPACE)
                el.send_keys(Keys.ESCAPE)
                if spec.get("voluntary"):
                    report["skipped_sensitive"].append(spec["label"])
                elif spec.get("required"):
                    driver.execute_script("arguments[0].style.outline = '2px solid #ef6c00'", el)
                    report["needs_you"].append(spec["label"])
            time.sleep(0.15)
        except Exception as exc:  # noqa: BLE001 - one stubborn dropdown must not stop the rest
            logger.warning("Dropdown fill failed: %s", exc)
    return report


BANNER_SCRIPT = r"""
const [filled, needs, uploaded] = arguments;
let banner = document.getElementById('jobapplier-banner');
if (!banner) { banner = document.createElement('div'); banner.id = 'jobapplier-banner'; document.body.prepend(banner); }
banner.setAttribute('style', 'position:sticky;top:0;z-index:2147483647;background:#1b5e20;color:#fff;font:14px/1.4 -apple-system,system-ui,sans-serif;padding:10px 14px;box-shadow:0 2px 6px rgba(0,0,0,.25)');
banner.textContent = `JobApplier filled ${filled} field(s)` + (uploaded ? ' and attached your tailored resume' : '') +
  `. Green = filled, orange = needs you (${needs}). Check every answer, then press Submit yourself. JobApplier will not submit.`;
"""

RESUME_INPUT_SCRIPT = r"""
const inputs = [...document.querySelectorAll('input[type=file]')];
const text = el => ((el.closest('label, .field, [class*="field"], [class*="upload"], [class*="question"], div') || el).innerText + ' ' + (el.name || '') + ' ' + (el.id || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
let best = inputs.find(el => /resume|cv|curriculum/.test(text(el)) && !/cover/.test(text(el)));
if (!best) best = inputs.find(el => !/cover|transcript|portfolio/.test(text(el)));
return best || null;
"""

IFRAME_SCRIPT = r"""
// Follow an embedded ATS form only when this page has no form of its own, and match the
// iframe's host (a sign-in helper can carry "greenhouse.io" in its query string).
const own = [...document.querySelectorAll('input, textarea, select')].filter(el => !['hidden', 'submit', 'button'].includes(el.type)).length;
if (own >= 3) return null;
const ATS = /(^|\.)(greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com|smartrecruiters\.com|icims\.com)$/i;
for (const frame of document.querySelectorAll('iframe[src]')) {
  try { if (ATS.test(new URL(frame.src, location.href).hostname)) return frame.src; } catch (e) {}
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
    job: Dict[str, Any] | None = None,
    new_tab: bool = False,
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
        if new_tab and not refill_current_page and driver.current_url not in ("about:blank", "data:,"):
            driver.switch_to.new_window("tab")  # keep earlier filled forms open for review
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
        values = field_values(profile, answers, job)
        report = driver.execute_script(FILL_SCRIPT, values) or {}
        if report.get("combos"):
            extra = fill_dropdowns(driver)
            for name in ("filled", "needs_you", "skipped_sensitive"):
                report[name] = report.get(name, []) + extra.get(name, [])
        driver.execute_script(BANNER_SCRIPT, len(report.get("filled", [])), len(report.get("needs_you", [])), uploaded)
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
