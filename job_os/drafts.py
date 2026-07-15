"""Natural, editable application and recruiter-message drafts."""

from __future__ import annotations

from typing import Any, Dict

from .profile import load_profile


def generate_application_answers(job: Dict[str, Any], profile: Dict[str, Any] | None = None) -> Dict[str, str]:
    profile = profile or load_profile()
    company = job.get("company") or "your company"
    role = job.get("title") or "this role"
    project = job.get("suggested_project") or "JobApplier"
    education = (profile.get("education") or [{}])[0]
    institution = education.get("institution") or "my university"
    degree = education.get("degree") or "Computer Science"
    minor = education.get("minor")
    study = f"{degree} student at {institution}" + (f" with a {minor} minor" if minor else "")
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
        "star_example": "Situation: On the Allymon fintech project, user, loan, and investor-qualification workflows needed QA validation. Task: I needed to compare the intended behavior with what the local application actually did. Action: I set up and debugged the application, exercised the relevant database, authentication, and admin flows, and documented expected versus actual behavior. Result: I produced concrete QA findings for team review. Confirm the exact interview question and keep only details you personally completed before using this draft.",
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
