import PyPDF2
import pdfplumber
from docx import Document
import re
from typing import Dict, List
from config import Config

class ResumeParser:
    def __init__(self):
        self.use_ai = Config.OPENAI_API_KEY and Config.OPENAI_API_KEY != ''
        if self.use_ai:
            import openai
            openai.api_key = Config.OPENAI_API_KEY
            print("Resume parser initialized with AI support")
        else:
            print("Resume parser initialized with rule-based extraction (no API key)")
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF using pdfplumber for better accuracy."""
        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
        except Exception as e:
            print(f"Error extracting PDF text: {e}")
        return text
    
    def extract_text_from_docx(self, docx_path: str) -> str:
        """Extract text from Word document."""
        try:
            doc = Document(docx_path)
            return "\n".join([paragraph.text for paragraph in doc.paragraphs])
        except Exception as e:
            print(f"Error extracting DOCX text: {e}")
            return ""
    
    def parse_resume(self, file_path: str) -> Dict:
        """Parse resume and extract structured information."""
        if file_path.endswith('.pdf'):
            text = self.extract_text_from_pdf(file_path)
        elif file_path.endswith('.docx'):
            text = self.extract_text_from_docx(file_path)
        else:
            raise ValueError("Unsupported file format. Use PDF or DOCX.")
        
        if self.use_ai:
            parsed_data = self._extract_with_ai(text)
        else:
            parsed_data = self._extract_with_rules(text)
        
        return parsed_data
    
    def _extract_with_ai(self, resume_text: str) -> Dict:
        """Use OpenAI to extract structured data from resume."""
        import openai
        import json
        
        prompt = f"""
        Extract the following information from this resume and return as JSON:
        - skills (list of technical and soft skills)
        - experience (list of job experiences with company, title, duration, responsibilities)
        - education (list of degrees with institution, degree, field, year)
        - certifications (list)
        - contact_info (email, phone, linkedin)
        
        Resume:
        {resume_text}
        """
        
        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a resume parsing assistant. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Error parsing with AI: {e}")
            return self._extract_with_rules(resume_text)
    
    def _extract_with_rules(self, text: str) -> Dict:
        """Rule-based extraction without AI."""
        return {
            'skills': self.extract_skills(text),
            'experience': self.extract_experience(text),
            'education': self.extract_education(text),
            'certifications': self.extract_certifications(text),
            'contact_info': self.extract_contact_info(text)
        }
    
    def extract_skills(self, text: str) -> List[str]:
        """Extract technical and soft skills."""
        # Comprehensive skill list
        skill_keywords = [
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'sql',
            'react', 'angular', 'vue', 'node.js', 'express', 'django', 'flask',
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'git', 'github',
            'html', 'css', 'mongodb', 'postgresql', 'mysql', 'redis',
            'machine learning', 'deep learning', 'tensorflow', 'pytorch',
            'pandas', 'numpy', 'scikit-learn', 'data analysis', 'statistics',
            'excel', 'powerpoint', 'tableau', 'power bi',
            'agile', 'scrum', 'jira', 'rest api', 'graphql',
            'finance', 'economics', 'accounting', 'financial modeling',
            'bloomberg terminal', 'trading', 'risk management'
        ]
        
        found_skills = []
        text_lower = text.lower()
        
        for skill in skill_keywords:
            if skill in text_lower:
                found_skills.append(skill)
        
        return list(set(found_skills))
    
    def extract_experience(self, text: str) -> List[Dict]:
        """Extract work experience."""
        # Simple pattern matching for experience
        experience = []
        lines = text.split('\n')
        
        # Look for common job title patterns
        job_pattern = re.compile(r'(intern|developer|engineer|analyst|assistant|associate)', re.IGNORECASE)
        
        for i, line in enumerate(lines):
            if job_pattern.search(line):
                experience.append({
                    'title': line.strip(),
                    'company': lines[i+1].strip() if i+1 < len(lines) else '',
                    'duration': '',
                    'responsibilities': []
                })
        
        return experience[:5]  # Return max 5 experiences
    
    def extract_education(self, text: str) -> List[Dict]:
        """Extract education information."""
        education = []
        text_lower = text.lower()
        
        # Check for degree keywords
        if 'bachelor' in text_lower or 'b.s.' in text_lower or 'b.a.' in text_lower:
            degree_type = 'Bachelor'
        elif 'master' in text_lower or 'm.s.' in text_lower or 'm.a.' in text_lower:
            degree_type = 'Master'
        else:
            degree_type = 'Undergraduate'
        
        # Check for majors
        major = ''
        if 'computer science' in text_lower or 'cs' in text_lower:
            major = 'Computer Science'
        if 'economics' in text_lower or 'econ' in text_lower:
            if major:
                major += ' / Economics'
            else:
                major = 'Economics'
        
        if major:
            education.append({
                'degree': degree_type,
                'field': major,
                'institution': '',
                'year': ''
            })
        
        return education
    
    def extract_certifications(self, text: str) -> List[str]:
        """Extract certifications."""
        cert_keywords = ['certified', 'certification', 'certificate', 'aws', 'azure', 'comptia']
        certifications = []
        
        text_lower = text.lower()
        for keyword in cert_keywords:
            if keyword in text_lower:
                certifications.append(keyword.title())
        
        return list(set(certifications))
    
    def extract_contact_info(self, text: str) -> Dict:
        """Extract contact information."""
        contact = {}
        
        # Extract email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_match = re.search(email_pattern, text)
        if email_match:
            contact['email'] = email_match.group(0)
        
        # Extract phone
        phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        phone_match = re.search(phone_pattern, text)
        if phone_match:
            contact['phone'] = phone_match.group(0)
        
        # Extract LinkedIn
        linkedin_pattern = r'linkedin\.com/in/[\w-]+'
        linkedin_match = re.search(linkedin_pattern, text, re.IGNORECASE)
        if linkedin_match:
            contact['linkedin'] = linkedin_match.group(0)
        
        return contact
    
    def extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords for job matching."""
        return self.extract_skills(text)
