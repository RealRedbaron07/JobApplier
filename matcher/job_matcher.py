from typing import Dict
import re

class JobMatcher:
    def __init__(self, user_profile: Dict):
        self.user_profile = user_profile
        
        # Define keywords for tech/fintech internships
        self.tech_keywords = [
            'python', 'java', 'javascript', 'react', 'node', 'sql', 'git',
            'aws', 'docker', 'api', 'software', 'developer', 'engineer',
            'data', 'machine learning', 'ai', 'web development', 'backend',
            'frontend', 'full stack', 'mobile', 'android', 'ios'
        ]
        
        self.fintech_keywords = [
            'fintech', 'finance', 'trading', 'banking', 'payment', 'blockchain',
            'cryptocurrency', 'financial', 'investment', 'portfolio', 'risk',
            'quantitative', 'analytics', 'economics', 'market', 'capital'
        ]
        
        self.internship_keywords = [
            'intern', 'internship', 'co-op', 'summer', 'undergraduate',
            'student', 'entry level', 'junior', 'trainee', 'associate'
        ]
        
        self.red_flags = [
            'senior', '5+ years', '10+ years', 'phd required', 'graduate degree required',
            'extensive experience', 'lead', 'principal', 'staff engineer', 'architect'
        ]
    
    def calculate_match_score(self, job: Dict) -> int:
        """Calculate match score between user profile and job (0-100)."""
        job_title = job.get('title', '').lower()
        job_description = job.get('description', '').lower()
        job_location = job.get('location', '').lower()
        
        if not job_description:
            print(f"Warning: No description for job {job.get('title')}")
            # Still try to score based on title
            if not job_title:
                return 0
            job_description = job_title
        
        combined_text = f"{job_title} {job_description}"
        
        score = 0
        
        # 1. Check if it's an internship (30 points)
        internship_matches = sum(1 for keyword in self.internship_keywords if keyword in combined_text)
        if internship_matches > 0:
            score += min(30, internship_matches * 10)
        else:
            # If no internship keywords, heavily penalize
            score -= 20
        
        # 2. Check for tech keywords (25 points)
        tech_matches = sum(1 for keyword in self.tech_keywords if keyword in combined_text)
        score += min(25, tech_matches * 3)
        
        # 3. Check for fintech keywords (20 points)
        fintech_matches = sum(1 for keyword in self.fintech_keywords if keyword in combined_text)
        score += min(20, fintech_matches * 4)
        
        # 4. User skills match (15 points)
        user_skills = [skill.lower() for skill in self.user_profile.get('skills', [])]
        if user_skills:
            skill_matches = sum(1 for skill in user_skills if skill in combined_text)
            score += min(15, skill_matches * 5)
        else:
            # Default skills for CS student if profile is empty
            default_skills = ['python', 'java', 'sql', 'javascript']
            skill_matches = sum(1 for skill in default_skills if skill in combined_text)
            score += min(15, skill_matches * 4)
        
        # 5. Location bonus (10 points)
        if 'remote' in job_location or 'hybrid' in job_location:
            score += 10
        elif any(city in job_location for city in ['san francisco', 'new york', 'boston', 'seattle']):
            score += 5
        
        # 6. Red flags (deductions)
        red_flag_count = sum(1 for flag in self.red_flags if flag in combined_text)
        score -= red_flag_count * 15
        
        # 7. Education level check (bonus for undergrad-friendly)
        if any(word in combined_text for word in ['undergraduate', 'sophomore', 'junior', 'bachelor']):
            score += 10
        
        # Ensure score is between 0 and 100
        score = max(0, min(100, score))
        
        return score
    
    def should_apply(self, job: Dict, min_score: int = 60) -> bool:
        """Determine if user should apply to this job."""
        score = self.calculate_match_score(job)
        return score >= min_score
    
    def get_match_reasoning(self, job: Dict) -> str:
        """Get a brief explanation of the match score."""
        score = self.calculate_match_score(job)
        job_title = job.get('title', '').lower()
        job_description = job.get('description', '').lower()
        combined_text = f"{job_title} {job_description}"
        
        reasons = []
        
        # Check what contributed to the score
        if any(keyword in combined_text for keyword in self.internship_keywords):
            reasons.append("✓ Internship position")
        
        tech_matches = sum(1 for keyword in self.tech_keywords if keyword in combined_text)
        if tech_matches > 0:
            reasons.append(f"✓ {tech_matches} tech skill matches")
        
        fintech_matches = sum(1 for keyword in self.fintech_keywords if keyword in combined_text)
        if fintech_matches > 0:
            reasons.append(f"✓ {fintech_matches} fintech keyword matches")
        
        red_flag_count = sum(1 for flag in self.red_flags if flag in combined_text)
        if red_flag_count > 0:
            reasons.append(f"✗ {red_flag_count} red flags (senior/experienced)")
        
        return f"Score: {score}/100 - " + ", ".join(reasons) if reasons else f"Score: {score}/100"
