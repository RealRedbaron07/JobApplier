"""Natural, editable application and recruiter-message drafts."""

from __future__ import annotations

import re
from typing import Any, Dict

from .profile import load_profile


_NOT_ABOUT_COMPANY = re.compile(
    r"\b(you will|you'll|you have|you are|you're|your|we're looking|we are looking|looking for|requirements?|"
    r"qualifications?|responsibilit|must|should|nice to have|bonus|benefits?|salary|pay range|compensation|"
    r"equal opportunity|accommodat|disabilit|applicants?|candidates?|apply|visa|sponsor|background check|"
    r"years of experience|degree in|experience (?:with|in|using)|proficien|privacy|cookies?)\b", re.I)
_ABOUT_COMPANY = re.compile(r"\b(we|our|mission|founded|helps?|build(?:s|ing)?|platform|customers?|products?|team)\b", re.I)


def company_fact(job: Dict[str, Any]) -> str:
    """One sentence from the posting itself that says what the company or team does.

    Quoting the employer's own words keeps the answer specific without inventing
    anything. Returns "" when no suitable sentence exists.
    """
    from .tailoring import validate_draft

    company = (job.get("company") or "").strip()
    text = re.sub(r"\s+", " ", str(job.get("description") or ""))
    best, best_score = "", 0
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", text)[:40]:
        sentence = sentence.strip(" -•*•")
        if not 50 <= len(sentence) <= 260 or _NOT_ABOUT_COMPANY.search(sentence) or "http" in sentence:
            continue
        score = (3 if company and company.lower() in sentence.lower() else 0) + len(_ABOUT_COMPANY.findall(sentence))
        if score > best_score:
            best, best_score = sentence, score
    if best_score < 2 or not validate_draft(best)["passed"]:
        return ""
    return best.rstrip(".!") + "."


def generate_application_answers(job: Dict[str, Any], profile: Dict[str, Any] | None = None) -> Dict[str, str]:
    profile = profile or load_profile()
    answers = _base_answers(job, profile)
    fact = company_fact(job)
    if fact:
        company = job.get("company") or "your company"
        role = job.get("title") or "this role"
        quoted = f"One line in the posting stood out to me: “{fact}”"
        answers["cover_letter"] = answers["cover_letter"].replace(
            f"Before using this draft, I will add one verified sentence about {company}'s product, team, or mission from an official source.",
            f"{quoted} I would really like to help with that kind of work.")
        answers["why_company"] = (f"I'm interested in {company} because this {role} opportunity connects practical technology work "
                                  f"with a real team and product. {quoted} I would really like to help with that kind of work.")
    return answers


def _base_answers(job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, str]:
    company = job.get("company") or "your company"
    role = job.get("title") or "this role"
    project = job.get("suggested_project") or "MalpariBot"
    education = (profile.get("education") or [{}])[0]
    institution = education.get("institution") or "my university"
    degree = education.get("degree") or "Computer Science"
    minor = education.get("minor")
    study = f"{degree} student at {institution}" + (f" with {'an' if minor[:1].lower() in 'aeiou' else 'a'} {minor} minor" if minor else "")
    known_skills = profile.get("skills", [])
    highlighted = [skill for skill in ("Next.js", "TypeScript", "Express.js", "MySQL", "React Native", "Git") if skill in known_skills]
    tools = ", ".join(highlighted)
    name = profile.get("name") or "Mustafa Alp ARI"
    return {
        "cover_letter": f"Dear Hiring Team,\n\nI'm applying for the {role} opportunity at {company}. I'm a {study}, and my recent Riipen work has included web development, debugging, QA, and fintech application workflows. I have worked with tools including {tools}.\n\nThe role interests me because it would let me contribute practical technical work while continuing to learn from an experienced team. I would bring a careful approach to implementation, testing, and clear documentation. Before using this draft, I will add one verified sentence about {company}'s product, team, or mission from an official source.\n\nThank you for considering my application. I would welcome the opportunity to discuss how my experience and current studies could support the team.\n\nSincerely,\n{name}",
        "why_company": f"I'm interested in {company} because this {role} opportunity connects practical technology work with a real team and product. Before using this answer, I would add one specific fact from {company}'s official website or the posting.",
        "why_role": f"The {role} position fits the kind of work I want to deepen: building, testing, debugging, and improving software with a team. My recent Riipen projects gave me hands-on experience with development workflows and documenting issues clearly.",
        "tell_us_about_yourself": f"I'm a {study}. Through Riipen projects, I've worked on web, fintech, and mobile applications using tools including {tools}. I also enjoy building practical automation and accessibility projects, and I'm looking for an internship where I can contribute while continuing to learn.",
        "salary_expectation": "I'm open to the employer's established range for this internship/co-op and would consider the full scope, term, location, and learning opportunity. I would be happy to discuss the budgeted range.",
        "availability": profile.get("availability", "Please confirm availability before using this draft."),
        "work_authorization": str(profile.get("work_authorization") or "Please confirm work authorization before using this draft."),
        "relocation": profile.get("relocation", "Please confirm relocation preferences before using this draft."),
        "new_opportunities": "I'm looking for an opportunity to apply my coursework and recent project experience in a professional team, take on meaningful technical work, and grow through feedback and mentorship.",
        "star_example": "Situation: On the Riipen Advance Ontario fintech app, the marketplace, portfolio, and wallet screens still showed mock data, and the borrower and admin workflows needed validation. Task: I needed to connect real API responses and confirm the flows worked end to end. Action: I replaced the mock data with API responses, then tested the borrower and admin workflows over about 60 hours. Result: I documented the APIs, bugs, and smoke tests in a 348-line handoff for the team. Confirm the exact interview question and keep only details you personally completed before using this draft.",
        "project_bridge": f"For this application, emphasize {project} only using the factual bullets in the tailoring plan.",
    }


def recruiter_message(kind: str, contact: Dict[str, Any], job: Dict[str, Any] | None = None) -> str:
    first_name = (contact.get("name") or "there").split()[0]
    company = contact.get("company") or (job or {}).get("company") or "your company"
    role = (job or {}).get("title") or contact.get("role") or "the opportunity"
    templates = {
        "referral_request": f"Hi {first_name}, I noticed the {role} opening at {company}. My background is in CS, web development, QA, and fintech projects. If you think my experience could fit, would you be comfortable sharing how referrals work there? No pressure at all.",
        "coffee_chat": f"Hi {first_name}, I'm a York CS student learning more about technical work at {company}. Would you be open to a brief 15-minute chat about your experience and any advice for someone targeting internship roles?",
        "application_follow_up": f"Hi {first_name}, I recently applied for the {role} role at {company} and wanted to reaffirm my interest. My recent work includes web development, testing, and debugging on team projects. I'm happy to share any additional information that would be useful.",
        "thank_you": f"Hi {first_name}, thank you for taking the time to speak with me about the {role} opportunity. I appreciated learning more about the team and remain very interested. Please let me know if I can provide anything else.",
        "send_resume": f"Hi {first_name}, I'm interested in internship opportunities at {company} that align with software development, QA, data, or fintech. Would it be alright if I sent you a concise resume for context?",
        "rejection_networking": f"Hi {first_name}, thank you for letting me know about the decision on the {role} role. I appreciated the consideration and would be glad to stay in touch for future student opportunities at {company}.",
    }
    return templates.get(kind, templates["application_follow_up"])
