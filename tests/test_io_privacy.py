from pathlib import Path

from job_os.io import export_csv, parse_csv


class Row:
    id = 1
    company = "=DANGEROUS()"
    title = "Intern"
    location = "Toronto"
    application_status = "discovered"


def test_csv_import_and_formula_safe_export():
    rows = parse_csv("title,company,location,description\nDeveloper Intern,Example,Toronto,Python and Git internship")
    assert len(rows) == 1
    assert rows[0]["title"] == "Developer Intern"
    exported = export_csv([Row()])
    assert "'=DANGEROUS()" in exported


def test_private_files_are_gitignored():
    ignore = Path(".gitignore").read_text()
    assert "data/*.json" in ignore
    assert ".env" in ignore
    assert "*.db" in ignore
    assert "data/drafts/" in ignore
