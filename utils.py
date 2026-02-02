import re
from typing import Dict, List, Tuple
from urllib.parse import urlparse


def _extract_year(text: str) -> int | None:
    """Extract a 4-digit year from text."""
    if not text:
        return None
    
    # Look for 4-digit years (1900-2099)
    matches = re.findall(r'\b(19\d{2}|20\d{2})\b', str(text))
    return int(matches[0]) if matches else None


def _check_certificate_legitimacy_patterns(raw_text: str) -> Tuple[float, List[str]]:
    """
    Check if OCR text contains patterns typical of legitimate certificates.
    Returns (score 0-1, list of found patterns)
    """
    patterns_found = []
    score = 0.0
    
    text_lower = raw_text.lower()
    
    # Pattern 1: Contains certificate keywords
    cert_keywords = ['certificate', 'completion', 'participation', 'recognition', 'award', 'presented', 'honor', 'achievement']
    cert_matches = sum(1 for kw in cert_keywords if kw in text_lower)
    if cert_matches >= 2:
        score += 0.15
        patterns_found.append(f"✓ Found {cert_matches} certificate-related keywords")
    
    # Pattern 2: Contains date patterns
    date_pattern = r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|january|february|march|april|may|june|july|august|september|october|november|december)\b'
    if re.search(date_pattern, text_lower):
        score += 0.10
        patterns_found.append("✓ Found date information")
    
    # Pattern 3: Contains name (longer words separated by spaces)
    words = re.findall(r'\b[A-Z][a-z]+\b', raw_text)
    if len(words) >= 3:
        score += 0.10
        patterns_found.append(f"✓ Found {len(words)} proper nouns (likely names/organizations)")
    
    # Pattern 4: Contains organization keywords
    org_keywords = ['university', 'college', 'institute', 'organization', 'company', 'board', 'division', 'council', 'committee', 'foundation']
    org_matches = sum(1 for kw in org_keywords if kw in text_lower)
    if org_matches >= 1:
        score += 0.15
        patterns_found.append(f"✓ Found {org_matches} organization-related keyword(s)")
    
    # Pattern 5: Contains event keywords
    event_keywords = ['summit', 'conference', 'competition', 'hackathon', 'symposium', 'workshop', 'seminar', 'event']
    event_matches = sum(1 for kw in event_keywords if kw in text_lower)
    if event_matches >= 1:
        score += 0.15
        patterns_found.append(f"✓ Found {event_matches} event-related keyword(s)")
    
    # Pattern 6: Has reasonable length (real certificates have content)
    if len(raw_text.strip()) >= 150:
        score += 0.15
        patterns_found.append(f"✓ Substantial text content ({len(raw_text)} chars)")
    elif len(raw_text.strip()) >= 100:
        score += 0.08
    
    # Pattern 7: Has location information
    location_keywords = ['dhaka', 'bangladesh', 'city', 'country', 'venue', 'location', 'held at', 'organized at']
    if any(kw in text_lower for kw in location_keywords):
        score += 0.10
        patterns_found.append("✓ Contains location information")
    
    # Pattern 8: Avoid obvious fake patterns
    fake_keywords = ['scam', 'fake', 'invalid', 'forged', 'counterfeit']
    if any(kw in text_lower for kw in fake_keywords):
        score = max(0, score - 0.5)
        patterns_found.append("⚠ Warning: Contains suspicious words")
    
    return min(score, 1.0), patterns_found


def _is_official_domain(url: str) -> bool:
    """Check if URL is from official domain (.gov, .edu, .org)."""
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.endswith('.gov') or netloc.endswith('.edu') or netloc.endswith('.org')
    except Exception:
        return False


def _is_social_media_event(url: str) -> bool:
    """Check if URL is from Facebook events or LinkedIn events."""
    try:
        url_lower = url.lower()
        return (
            'facebook.com/events' in url_lower or
            'fb.com/events' in url_lower or
            'linkedin.com/events' in url_lower
        )
    except Exception:
        return False


def _is_social_media_link(url: str) -> bool:
    """Check if URL is from any social media platform."""
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return (
            'facebook.com' in netloc or
            'fb.com' in netloc or
            'linkedin.com' in netloc or
            'twitter.com' in netloc or
            'instagram.com' in netloc
        )
    except Exception:
        return False


def _check_text_clarity(raw_text: str) -> float:
    """
    Check OCR text clarity and quality.
    Returns a score 0-1 based on text quality indicators.
    """
    if not raw_text:
        return 0.0
    
    text_len = len(raw_text.strip())
    if text_len < 50:
        return 0.2
    elif text_len < 100:
        return 0.4
    elif text_len < 300:
        return 0.6
    elif text_len < 500:
        return 0.8
    else:
        return 1.0


def _check_text_consistency(raw_text: str, search_urls: List[str]) -> bool:
    """Check if raw text has content and URLs exist (basic consistency check)."""
    if not raw_text or len(raw_text.strip()) < 20:
        return False
    
    if not search_urls or len(search_urls) == 0:
        return False
    
    # Basic check: text has meaningful content and we have search results
    # More sophisticated: check if any words from text appear in URLs
    text_words = set(re.findall(r'\w+', raw_text.lower()))
    meaningful_words = {w for w in text_words if len(w) > 3}
    
    if len(meaningful_words) < 3:
        return False
    
    # Check if any meaningful words appear in URLs
    urls_text = ' '.join(search_urls).lower()
    matches = sum(1 for word in meaningful_words if word in urls_text)
    
    # If at least 1 word match, consider consistent
    return matches > 0


def _is_future_or_recent_event(text: str) -> bool:
    """
    Check if event is in future (2025+) or recent (current year/past year).
    These events may not be well indexed yet.
    """
    from datetime import datetime
    
    year_matches = re.findall(r'\b(202[5-9]|203\d)\b', text)
    if year_matches:
        event_year = int(year_matches[0])
        current_year = datetime.now().year
        # Consider future or recent (within last 2 years)
        return event_year >= current_year or (current_year - event_year <= 1)
    
    return False


def calculate_accuracy(raw_text: str, search_urls: List[str]) -> Tuple[float, str]:
    """
    Calculate accuracy score and status based ONLY on search URLs found.
    
    Args:
        raw_text (str): Raw OCR extracted text from certificate
        search_urls (List[str]): List of URLs from web search
    
    Returns:
        Tuple[float, str]: (score 0-100, status "Authentic"/"Suspicious"/"Fake")
    
    Scoring (based ONLY on search results):
        - Official domains (.gov, .edu, .org): +40 points
        - Social media links (Facebook, LinkedIn): +30 points
        - Text consistency with search results: +20 points
        - No search results: 0 points (cannot verify)
    
    Status:
        - Authentic: score >= 70
        - Suspicious: score 40-69
        - Fake: score < 40 (including no search results)
    """
    score = 0
    reasons = []
    
    # Only proceed if we have search results
    if len(search_urls) == 0:
        reasons.append("❌ No online verification found - cannot confirm authenticity")
        reasons.append("⚠️ Certificate may be fake or too local/new to be indexed")
        return 0, "Fake"
    
    # 1. Check for official domains (+40 points)
    has_official = any(_is_official_domain(url) for url in search_urls)
    if has_official:
        score += 40
        reasons.append("✓ Found official domain (.gov/.edu/.org)")
    
    # 2. Check for social media links (+30 points)
    has_social = any(_is_social_media_link(url) for url in search_urls)
    if has_social:
        score += 30
        reasons.append("✓ Found official social media event")
    
    # 3. Check text consistency (+20 points)
    is_consistent = _check_text_consistency(raw_text, search_urls)
    if is_consistent:
        score += 20
        reasons.append("✓ Certificate details match search results")
    
    # Cap at 100
    score = min(score, 100)
    
    # Determine status based ONLY on search verification
    if score >= 70:
        status = "Authentic"
        reasons.insert(0, "✅ Certificate verified through multiple sources")
    elif score >= 40:
        status = "Suspicious"
        reasons.insert(0, "⚠️ Certificate found online but with limited verification")
    else:
        status = "Fake"
        reasons.insert(0, "❌ Certificate not properly verified online")
    
    return score, status


# Keep the original function for backward compatibility with dict-based inputs
def calculate_accuracy_dict(ocr_data: Dict[str, str], search_results: List[str]) -> Dict[str, any]:
    score = 0
    
    # Check for official domains
    has_official = any(_is_official_domain(url) for url in search_results)
    if has_official:
        score += 50
    
    # Check for social media event pages
    has_social_event = any(_is_social_media_event(url) for url in search_results)
    if has_social_event:
        score += 30
    
    # Check year matching
    ocr_year = _extract_year(ocr_data.get('event_date', ''))
    if ocr_year:
        # Check if year appears in any search result URL or could be verified
        search_text = ' '.join(search_results)
        search_year = _extract_year(search_text)
        if search_year and search_year == ocr_year:
            score += 20
    
    # Cap at 100
    score = min(score, 100)
    
    # Determine status
    if score >= 70:
        status = "Verified"
    elif score >= 40:
        status = "Suspicious"
    else:
        status = "Fake"
    
    return {
        "score": score,
        "status": status,
        "details": {
            "has_official_domain": has_official,
            "has_social_media_event": has_social_event,
            "year_match": ocr_year is not None and score >= 20
        }
    }


def format_verification_report(ocr_data: Dict, search_results: List[str], accuracy_result: Dict) -> str:
    """
    Format a human-readable verification report.
    
    Args:
        ocr_data: Extracted OCR data
        search_results: List of search result URLs
        accuracy_result: Result from calculate_accuracy()
    
    Returns:
        Formatted string report
    """
    report = []
    report.append("=" * 60)
    report.append("CERTIFICATE VERIFICATION REPORT")
    report.append("=" * 60)
    report.append(f"\nCompetition: {ocr_data.get('competition_name', 'N/A')}")
    report.append(f"Organizer: {ocr_data.get('organizer_name', 'N/A')}")
    report.append(f"Event Date: {ocr_data.get('event_date', 'N/A')}")
    report.append(f"\nAccuracy Score: {accuracy_result['score']}/100")
    report.append(f"Status: {accuracy_result['status']}")
    report.append(f"\nVerification Details:")
    report.append(f"  - Official Domain Found: {accuracy_result['details']['has_official_domain']}")
    report.append(f"  - Social Media Event Found: {accuracy_result['details']['has_social_media_event']}")
    report.append(f"  - Year Match: {accuracy_result['details']['year_match']}")
    report.append(f"\nSearch Results Found: {len(search_results)}")
    
    if search_results:
        report.append("\nRelevant URLs:")
        for i, url in enumerate(search_results[:5], 1):
            report.append(f"  {i}. {url}")
    
    report.append("=" * 60)
    
    return "\n".join(report)


if __name__ == "__main__":
    # Example usage for calculate_accuracy (raw_text, search_urls)
    raw_text_sample = "AI Hackathon 2025 organized by Tech University on March 15, 2025"
    sample_urls = [
        "https://techuniversity.edu/events/ai-hackathon",
        "https://facebook.com/events/ai-hackathon-2025"
    ]
    
    score, status = calculate_accuracy(raw_text_sample, sample_urls)
    print(f"Score: {score}/100")
    print(f"Status: {status}")
    
    # Example usage for dict-based function
    sample_ocr = {
        "competition_name": "AI Hackathon 2025",
        "organizer_name": "Tech University",
        "event_date": "2025-03-15"
    }
    
    result = calculate_accuracy_dict(sample_ocr, sample_urls)
    print(f"\nDict-based result: {result}")
