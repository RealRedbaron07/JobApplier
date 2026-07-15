from pathlib import Path
import subprocess

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


def test_formula_safety_handles_leading_whitespace():
    class WhitespaceRow(Row):
        company = " \t=ALSO_DANGEROUS()"

    assert "' \t=ALSO_DANGEROUS()" in export_csv([WhitespaceRow()])


def test_private_files_are_gitignored():
    ignore = Path(".gitignore").read_text()
    assert "data/*.json" in ignore
    assert ".env" in ignore
    assert "*.db" in ignore
    assert "data/drafts/" in ignore
    assert ".env.*" in ignore


def test_git_actually_ignores_private_artifacts(tmp_path):
    del tmp_path
    for path in (".env.production", "data/candidate_profile.json", "private.sqlite", "exports/jobs.csv"):
        result = subprocess.run(["git", "check-ignore", "-q", path], check=False)
        assert result.returncode == 0, path
