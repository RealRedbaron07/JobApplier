from typing import Dict
import re
import os

class JobMatcher:
    def __init__(self, user_profile: Dict):
        self.user_profile = user_profile
        
        # Define keywords for tech/fintech internships
        self.tech_keywords = [
            'python', 'java', 'javascript', 'react', 'node', 'sql', 'git',
            'aws', 'docker', 'api', 'software', 'developer', 'engineer',
            'data', 'machine learning', 'ai', 'web development', 'backend',
            'frontend', 'full stack', 'mobile', 'android', 'ios', 'c++', 'c#',
            'typescript', 'cloud', 'devops', 'cybersecurity', 'kubernetes',
            'django', 'flask', 'spring', 'angular', 'vue', 'mongodb', 'postgresql'
        ]
        
        self.fintech_keywords = [
            'fintech', 'finance', 'trading', 'banking', 'payment', 'blockchain',
            'cryptocurrency', 'financial', 'investment', 'portfolio', 'risk',
            'quantitative', 'analytics', 'economics', 'market', 'capital',
            'econometrics', 'derivative', 'equity', 'asset management', 'macro'
        ]
        
        self.internship_keywords = [
            'intern', 'internship', 'co-op', 'co op', 'coop', 'summer', 'undergraduate',
            'student', 'entry level', 'entry-level', 'junior', 'trainee', 'associate', 'graduate'
        ]
        
        self.red_flags = [
            'senior', '5+ years', '10+ years', 'phd required', 'graduate degree required',
            'extensive experience', 'lead', 'principal', 'staff engineer', 'architect',
            '7+ years', '8+ years', 'masters required'
        ]
        
        # Get preferred locations from environment or config (for flexible scoring)
        self.preferred_locations = self._get_preferred_locations()
    
    def _get_preferred_locations(self) -> list:
        """Get preferred locations from environment variable or config."""
        # Check if user profile has location preferences
        if self.user_profile.get('preferred_locations'):
            return [loc.lower() for loc in self.user_profile['preferred_locations']]
        
        # Fallback to environment variable
        env_locations = os.getenv('PREFERRED_LOCATIONS', '')
        if env_locations:
            return [loc.strip().lower() for loc in env_locations.split(',')]
        
        # Default: remote and hybrid are universally preferred
        return ['remote', 'hybrid']
    
    def calculate_match_score(self, job: Dict) -> int:
        """Calculate match score between user profile and job (0-100).
        
        Improved algorithm that is more generalizable and less aggressive with penalties.
        """
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
        
        # 1. Entry-level/Internship position check (40 points max)
        # Less aggressive - give partial credit for entry-level keywords
        internship_matches = sum(1 for keyword in self.internship_keywords if keyword in combined_text)
        if internship_matches > 0:
            score += min(40, internship_matches * 10)
        elif 'entry' in combined_text or 'junior' in combined_text or 'new grad' in combined_text:
            # Partial credit for entry-level roles without explicit "intern" keyword
            score += 20
        else:
            # Only minor penalty for missing internship keywords (not -20)
            score -= 5
        
        # 2. Check for tech keywords (25 points)
        tech_matches = sum(1 for keyword in self.tech_keywords if keyword in combined_text)
        score += min(25, tech_matches * 2)
        
        # 3. Check for fintech keywords (15 points) - optional bonus
        fintech_matches = sum(1 for keyword in self.fintech_keywords if keyword in combined_text)
        score += min(15, fintech_matches * 3)
        
        # 4. User skills match (25 points) - most important
        user_skills = [skill.lower() for skill in self.user_profile.get('skills', [])]
        if user_skills:
            skill_matches = sum(1 for skill in user_skills if skill in combined_text)
            # More generous scoring for skill matches
            score += min(25, skill_matches * 3)
        else:
            # Default skills if profile is empty - use tech keywords as proxy
            skill_matches = sum(1 for keyword in self.tech_keywords[:8] if keyword in combined_text)
            score += min(20, skill_matches * 3)
        
        # 5. Location scoring (10 points) - flexible based on preferences
        location_score = 0
        for preferred_loc in self.preferred_locations:
            if preferred_loc in job_location:
                location_score = 10
                break
        # Always give partial credit for remote/hybrid
        if location_score == 0 and ('remote' in job_location or 'hybrid' in job_location):
            location_score = 5
        score += location_score
        
        # 6. Red flags (deductions) - less aggressive
        red_flag_count = sum(1 for flag in self.red_flags if flag in combined_text)
        # Reduced penalty from -15 to -10 per flag
        score -= red_flag_count * 10
        
        # 7. Education level check (bonus for undergrad-friendly)
        if any(word in combined_text for word in ['undergraduate', 'sophomore', 'junior year', 'bachelor', 'pursuing degree']):
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
