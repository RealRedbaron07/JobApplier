#!/usr/bin/env python3
"""
Cover letter generator that creates personalized cover letters for each job application.
Uses OpenAI if available, otherwise uses template-based generation.
"""

import os
from typing import Dict, Optional, Tuple
from config import Config
from datetime import datetime

class CoverLetterGenerator:
    def __init__(self):
        self.use_ai = Config.OPENAI_API_KEY and Config.OPENAI_API_KEY != ''
        if self.use_ai:
            try:
                import openai
                self.openai = openai
                self.openai.api_key = Config.OPENAI_API_KEY
                print("Cover letter generator initialized with AI support")
            except Exception as e:
                print(f"OpenAI import failed: {e}")
                self.use_ai = False
        else:
            print("Cover letter generator initialized with template-based generation")
    
    def generate_cover_letter(self, job: Dict, user_profile: Dict, output_dir: str = "cover_letters") -> Tuple[str, str]:
        """
        Generate a cover letter for a job application.
        
        Args:
            job: Job dictionary with title, company, description, etc.
            user_profile: User profile with skills, experience, education
            output_dir: Directory to save cover letter files
        
        Returns:
            tuple: (cover_letter_text, file_path)
        """
        if self.use_ai:
            return self._generate_with_ai(job, user_profile, output_dir)
        else:
            return self._generate_with_template(job, user_profile, output_dir)
    
    def _generate_with_ai(self, job: Dict, user_profile: Dict, output_dir: str) -> Tuple[str, str]:
        """Generate cover letter using OpenAI."""
        try:
            # Prepare user information
            skills = user_profile.get('skills', [])
            experience = user_profile.get('experience', [])
            education = user_profile.get('education', [])
            
            # Build experience summary
            exp_summary = ""
            for exp in experience[:3]:  # Top 3 experiences
                title = exp.get('title', '')
                company = exp.get('company', '')
                if title and company:
                    exp_summary += f"- {title} at {company}\n"
            
            # Build education summary
            edu_summary = ""
            for edu in education:
                degree = edu.get('degree', '')
                field = edu.get('field', '')
                institution = edu.get('institution', '')
                if degree and field:
                    edu_summary += f"- {degree} in {field}"
                    if institution:
                        edu_summary += f" from {institution}"
                    edu_summary += "\n"
            
            prompt = f"""Write a professional, concise cover letter for a job application. 

Job Details:
- Position: {job.get('title', 'N/A')}
- Company: {job.get('company', 'N/A')}
- Location: {job.get('location', 'N/A')}

Job Description (key points):
{job.get('description', '')[:1000]}

Applicant Background:
Skills: {', '.join(skills[:15])}

Relevant Experience:
{exp_summary}

Education:
{edu_summary}

Requirements:
- Keep it to 3-4 paragraphs
- Be specific about why you're interested in this role
- Highlight 2-3 most relevant skills/experiences
- Show enthusiasm for the company/role
- Professional but personable tone
- End with a call to action

Write the cover letter:"""

            response = self.openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional career coach writing cover letters. Write compelling, personalized cover letters that highlight the candidate's relevant experience and enthusiasm for the role."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=800
            )
            
            cover_letter = response.choices[0].message.content.strip()
            
            # Save to file
            file_path = self._save_cover_letter(cover_letter, job, output_dir)
            
            return cover_letter, file_path
            
        except Exception as e:
            print(f"Error generating cover letter with AI: {e}")
            print("Falling back to template-based generation...")
            return self._generate_with_template(job, user_profile, output_dir)
    
    def _generate_with_template(self, job: Dict, user_profile: Dict, output_dir: str) -> Tuple[str, str]:
        """Generate cover letter using template."""
        job_title = job.get('title', 'Position')
        company = job.get('company', 'Company')
        location = job.get('location', '')
        
        # Extract key requirements from job description
        description = job.get('description', '').lower()
        key_requirements = []
        
        # Match user skills to job requirements
        user_skills = [s.lower() for s in user_profile.get('skills', [])]
        common_skills = [skill for skill in user_skills if skill in description]
        
        # Get most relevant experience
        experience = user_profile.get('experience', [])
        relevant_exp = experience[0] if experience else {}
        
        # Get education
        education = user_profile.get('education', [])
        edu = education[0] if education else {}
        
        # Build cover letter
        cover_letter = f"""Dear Hiring Manager,

I am writing to express my strong interest in the {job_title} position at {company}. With my background in {', '.join(common_skills[:3]) if common_skills else 'technology'}, I am excited about the opportunity to contribute to your team."""
        
        # Add experience paragraph
        if relevant_exp:
            title = relevant_exp.get('title', '')
            company_exp = relevant_exp.get('company', '')
            if title and company_exp:
                cover_letter += f"\n\nIn my role as {title} at {company_exp}, I developed expertise in {', '.join(common_skills[:2]) if common_skills else 'software development'}. This experience has prepared me to excel in the {job_title} role, particularly in areas such as {', '.join(common_skills[:2]) if common_skills else 'problem-solving and technical implementation'}."
        
        # Add why interested
        cover_letter += f"\n\nI am particularly drawn to this opportunity at {company} because of [your interest in the company/role - please customize this section]. I am eager to bring my passion for {common_skills[0] if common_skills else 'technology'} and my commitment to excellence to your team."
        
        # Closing
        cover_letter += f"\n\nThank you for considering my application. I look forward to the opportunity to discuss how my skills and experience align with the {job_title} position. I am available for an interview at your convenience.\n\nSincerely,\n[Your Name]"
        
        # Save to file
        file_path = self._save_cover_letter(cover_letter, job, output_dir)
        
        return cover_letter, file_path
    
    def _save_cover_letter(self, cover_letter: str, job: Dict, output_dir: str) -> str:
        """Save cover letter to a file."""
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename
        company_safe = "".join(c for c in job.get('company', 'Company') if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        title_safe = "".join(c for c in job.get('title', 'Position') if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
        timestamp = datetime.now().strftime("%Y%m%d")
        
        filename = f"{timestamp}_{company_safe}_{title_safe}.txt"
        filename = filename.replace(' ', '_')
        
        file_path = os.path.join(output_dir, filename)
        
        # Write to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cover_letter)
        
        return file_path

