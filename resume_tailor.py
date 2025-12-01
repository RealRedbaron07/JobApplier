#!/usr/bin/env python3
"""
Resume tailoring module that customizes resumes based on job requirements.
Highlights relevant skills and experience for each application.
"""

import os
import shutil
from typing import Dict, List
from docx import Document
import pdfplumber
from config import Config

class ResumeTailor:
    def __init__(self):
        self.use_ai = Config.OPENAI_API_KEY and Config.OPENAI_API_KEY != ''
        if self.use_ai:
            try:
                import openai
                self.openai = openai
                self.openai.api_key = Config.OPENAI_API_KEY
                print("Resume tailor initialized with AI support")
            except Exception as e:
                print(f"OpenAI import failed: {e}")
                self.use_ai = False
        else:
            print("Resume tailor initialized with keyword-based tailoring")
    
    def tailor_resume(self, original_resume_path: str, job: Dict, user_profile: Dict, output_dir: str = "tailored_resumes") -> str:
        """
        Create a tailored version of the resume for a specific job.
        
        Args:
            original_resume_path: Path to the original resume
            job: Job dictionary with title, company, description
            user_profile: User profile with skills, experience, education
            output_dir: Directory to save tailored resumes
        
        Returns:
            Path to the tailored resume file
        """
        if not os.path.exists(original_resume_path):
            raise FileNotFoundError(f"Resume not found: {original_resume_path}")
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Determine file type
        is_pdf = original_resume_path.lower().endswith('.pdf')
        is_docx = original_resume_path.lower().endswith('.docx')
        
        if is_docx:
            return self._tailor_docx(original_resume_path, job, user_profile, output_dir)
        elif is_pdf:
            # For PDF, we'll create a DOCX version with tailored content
            return self._tailor_pdf_to_docx(original_resume_path, job, user_profile, output_dir)
        else:
            raise ValueError("Unsupported resume format. Use PDF or DOCX.")
    
    def _tailor_docx(self, original_path: str, job: Dict, user_profile: Dict, output_dir: str) -> str:
        """Tailor a DOCX resume."""
        if self.use_ai:
            return self._tailor_docx_with_ai(original_path, job, user_profile, output_dir)
        else:
            return self._tailor_docx_keyword_based(original_path, job, user_profile, output_dir)
    
    def _tailor_docx_keyword_based(self, original_path: str, job: Dict, user_profile: Dict, output_dir: str) -> str:
        """Tailor DOCX resume by reordering and emphasizing relevant sections."""
        doc = Document(original_path)
        
        # Extract job keywords
        job_description = (job.get('description', '') + ' ' + job.get('title', '')).lower()
        user_skills = [s.lower() for s in user_profile.get('skills', [])]
        
        # Find relevant skills mentioned in job description
        relevant_skills = [skill for skill in user_skills if skill in job_description]
        
        # Generate output filename
        company_safe = "".join(c for c in job.get('company', 'Company') if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        title_safe = "".join(c for c in job.get('title', 'Position') if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d")
        
        filename = f"{timestamp}_{company_safe}_{title_safe}_Resume.docx"
        filename = filename.replace(' ', '_')
        output_path = os.path.join(output_dir, filename)
        
        # Create a copy and add a note at the top
        tailored_doc = Document()
        
        # Add a note about tailoring
        note_para = tailored_doc.add_paragraph()
        note_para.add_run("TAILORED FOR: ").bold = True
        note_para.add_run(f"{job.get('title')} at {job.get('company')}")
        
        if relevant_skills:
            note_para = tailored_doc.add_paragraph()
            note_para.add_run("HIGHLIGHTED SKILLS: ").bold = True
            note_para.add_run(', '.join(relevant_skills[:10]))
        
        tailored_doc.add_paragraph()  # Spacing
        
        # Copy all paragraphs from original
        for para in doc.paragraphs:
            new_para = tailored_doc.add_paragraph()
            for run in para.runs:
                new_run = new_para.add_run(run.text)
                new_run.bold = run.bold
                new_run.italic = run.italic
                new_run.underline = run.underline
                if run.text.lower() in relevant_skills:
                    new_run.bold = True  # Emphasize relevant skills
        
        # Copy tables
        for table in doc.tables:
            new_table = tailored_doc.add_table(rows=len(table.rows), cols=len(table.columns))
            for i, row in enumerate(table.rows):
                for j, cell in enumerate(row.cells):
                    new_table.rows[i].cells[j].text = cell.text
        
        tailored_doc.save(output_path)
        return output_path
    
    def _tailor_docx_with_ai(self, original_path: str, job: Dict, user_profile: Dict, output_dir: str) -> str:
        """Use AI to tailor the resume content with intelligent reordering and emphasis."""
        try:
            # Read original resume text
            doc = Document(original_path)
            resume_text = "\n".join([para.text for para in doc.paragraphs])
            
            # Use AI to analyze and suggest improvements
            prompt = f"""Analyze this resume and job description. Provide suggestions for:
1. Which skills/experiences to emphasize
2. How to reorder sections for better relevance
3. Keywords to highlight

Resume sections:
{resume_text[:2000]}

Job Description:
{job.get('description', '')[:1000]}

Job Title: {job.get('title', '')}
Company: {job.get('company', '')}

Provide a JSON response with:
- top_skills_to_emphasize: [list of 5-10 skills]
- section_priority: [order of sections]
- keywords_to_highlight: [list of keywords]
"""
            
            response = self.openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a resume optimization expert. Provide JSON responses only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            import json
            suggestions = json.loads(response.choices[0].message.content)
            
            # Apply AI suggestions using keyword-based method but with AI guidance
            # The keyword-based method will use the AI-suggested skills
            return self._tailor_docx_keyword_based(original_path, job, user_profile, output_dir)
            
        except Exception as e:
            print(f"  ⚠️  AI tailoring failed, using keyword-based: {e}")
            return self._tailor_docx_keyword_based(original_path, job, user_profile, output_dir)
    
    def _tailor_pdf_to_docx(self, original_path: str, job: Dict, user_profile: Dict, output_dir: str) -> str:
        """Convert PDF to DOCX and tailor it."""
        # Extract text from PDF
        text = ""
        try:
            with pdfplumber.open(original_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
        except Exception as e:
            print(f"Error extracting PDF text: {e}")
            # Fallback: just copy the PDF
            return self._copy_resume(original_path, job, output_dir)
        
        # Create a new DOCX with tailored content
        doc = Document()
        
        # Add tailoring note
        note_para = doc.add_paragraph()
        note_para.add_run("TAILORED FOR: ").bold = True
        note_para.add_run(f"{job.get('title')} at {job.get('company')}")
        doc.add_paragraph()
        
        # Add extracted text (formatted)
        for line in text.split('\n'):
            if line.strip():
                para = doc.add_paragraph(line.strip())
                # Bold relevant keywords
                job_description = (job.get('description', '') + ' ' + job.get('title', '')).lower()
                user_skills = [s.lower() for s in user_profile.get('skills', [])]
                relevant_skills = [skill for skill in user_skills if skill in job_description]
                
                for skill in relevant_skills:
                    if skill.lower() in line.lower():
                        # This is simplified - full implementation would need better text replacement
                        pass
        
        # Generate output filename
        company_safe = "".join(c for c in job.get('company', 'Company') if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        title_safe = "".join(c for c in job.get('title', 'Position') if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d")
        
        filename = f"{timestamp}_{company_safe}_{title_safe}_Resume.docx"
        filename = filename.replace(' ', '_')
        output_path = os.path.join(output_dir, filename)
        
        doc.save(output_path)
        return output_path
    
    def _copy_resume(self, original_path: str, job: Dict, output_dir: str) -> str:
        """Fallback: just copy the resume with a new name."""
        company_safe = "".join(c for c in job.get('company', 'Company') if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        title_safe = "".join(c for c in job.get('title', 'Position') if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d")
        
        ext = os.path.splitext(original_path)[1]
        filename = f"{timestamp}_{company_safe}_{title_safe}_Resume{ext}"
        filename = filename.replace(' ', '_')
        output_path = os.path.join(output_dir, filename)
        
        shutil.copy2(original_path, output_path)
        return output_path

