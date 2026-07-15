from job_os.parser import parse_job_description


def test_parser_extracts_structured_fields():
    text = """Software Developer Co-op - Toronto. Starting Fall 2026 for 8 months.
    Required qualifications: TypeScript, React, Git and SQL.
    Next.js is preferred. Hybrid schedule. Pay $24-$30 per hour. No sponsorship available.
    Please submit a resume and transcript."""
    parsed = parse_job_description(text, {"title": "Software Developer Co-op", "company": "Example", "location": "Toronto, ON"})
    assert parsed["work_mode"] == "hybrid"
    assert parsed["term_length"] == "8 months"
    assert parsed["start_date"] == "Fall 2026"
    assert {"TypeScript", "React", "Git", "SQL"}.issubset(parsed["required_skills"])
    assert "Next.js" in parsed["preferred_skills"]
    assert parsed["salary_min"] == 24
    assert parsed["coop_eligible"] is True
    assert "transcript" in parsed["required_documents"]


def test_multiline_sections_boolean_and_single_salary():
    parsed = parse_job_description(
        """Fall 2026 co-op.
Required:
Python
SQL
AWS
Preferred:
Power BI
Pay $17.75 per hour.""",
        {"coop_eligible": "false"},
    )
    assert parsed["start_date"] == "Fall 2026"
    assert parsed["required_skills"] == ["AWS", "Python", "SQL"]
    assert parsed["preferred_skills"] == ["Power BI"]
    assert parsed["coop_eligible"] is False
    assert parsed["salary_min"] == parsed["salary_max"] == 17.75
