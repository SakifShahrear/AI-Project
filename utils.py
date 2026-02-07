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


def _normalize_tokens(text: str) -> List[str]:
    if not text:
        return []
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    tokens = [t for t in text.split() if len(t) > 3]
    return tokens


def _domain_matches_identity(search_urls: List[str], organizer_name: str | None,
                             competition_name: str | None, event_date: str | None) -> bool:
    if not search_urls:
        return False

    tokens = set(_normalize_tokens(organizer_name) + _normalize_tokens(competition_name))
    year = _extract_year(event_date or "")
    if year:
        tokens.add(str(year))

    if not tokens:
        return False

    for url in search_urls:
        url_lower = url.lower()
        for token in tokens:
            if token in url_lower:
                return True
    return False


def _content_has_competition_and_date(scraped_data: List[Dict], competition_name: str | None,
                                      event_date: str | None) -> bool:
    if not scraped_data or not competition_name or not event_date:
        return False

    comp = competition_name.lower().strip()
    year = _extract_year(event_date)
    if not comp or not year:
        return False

    for item in scraped_data:
        content = (item.get("content") or "").lower()
        if comp in content and str(year) in content:
            return True
    return False


def rank_search_urls(
    search_urls: List[str],
    competition_name: str | None,
    organizer_name: str | None,
    event_date: str | None
) -> List[str]:
    if not search_urls:
        return []

    tokens = set(_normalize_tokens(competition_name) + _normalize_tokens(organizer_name))
    year = _extract_year(event_date or "")

    def relevance_score(url: str) -> int:
        score = 0
        if _is_official_domain(url):
            score += 3
        if _is_social_media_link(url):
            score += 2

        url_lower = url.lower()
        if year and str(year) in url_lower:
            score += 2

        for token in tokens:
            if token in url_lower:
                score += 1
        return score

    return sorted(search_urls, key=relevance_score, reverse=True)


def calculate_rule_based_score(
    raw_text: str,
    competition_name: str | None,
    organizer_name: str | None,
    event_date: str | None,
    search_urls: List[str],
    scraped_data: List[Dict] | None
) -> Tuple[int, str]:
    score = 10

    if raw_text and raw_text.strip():
        score = max(score, 20)

    has_fields = any([
        competition_name not in (None, "Unknown"),
        organizer_name not in (None, "Unknown"),
        event_date not in (None, "Unknown")
    ])
    if has_fields:
        score = max(score, 40)

    if search_urls and len(search_urls) > 0:
        score = max(score, 60)

    if _domain_matches_identity(search_urls, organizer_name, competition_name, event_date):
        score = max(score, 80)

    if _content_has_competition_and_date(scraped_data or [], competition_name, event_date):
        score = max(score, 95)

    if score >= 80:
        status = "Authentic"
    elif score >= 40:
        status = "Suspicious"
    else:
        status = "Fake"

    return score, status


def _tokenize_text(text: str) -> set:
    if not text:
        return set()
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return {t for t in text.split() if len(t) > 3}


def text_similarity_score(raw_text: str, scraped_data: List[Dict] | None) -> int:
    if not raw_text or not scraped_data:
        return 0

    corpus = " ".join((item.get("content") or "") for item in scraped_data[:5])
    ocr_tokens = _tokenize_text(raw_text)
    web_tokens = _tokenize_text(corpus)

    if not ocr_tokens or not web_tokens:
        return 0

    intersection = len(ocr_tokens.intersection(web_tokens))
    union = len(ocr_tokens.union(web_tokens))
    if union == 0:
        return 0

    jaccard = intersection / union
    return min(100, int(jaccard * 200))


def field_confidence_score(
    competition_name: str | None,
    organizer_name: str | None,
    event_date: str | None,
    search_urls: List[str],
    scraped_data: List[Dict] | None
) -> int:
    score = 0
    if competition_name and competition_name != "Unknown":
        score += 35
    if organizer_name and organizer_name != "Unknown":
        score += 35
    if event_date and event_date != "Unknown":
        score += 20

    corpus = " ".join((item.get("content") or "") for item in (scraped_data or [])[:5]).lower()
    urls_text = " ".join(search_urls or []).lower()

    if competition_name and competition_name.lower() in corpus:
        score += 5
    if organizer_name and organizer_name.lower() in corpus:
        score += 5
    if event_date and event_date.lower() in corpus:
        score += 5
    if competition_name and competition_name.lower() in urls_text:
        score += 5
    if organizer_name and organizer_name.lower() in urls_text:
        score += 5

    return min(score, 100)


def anomaly_score(raw_text: str) -> int:
    if not raw_text:
        return 0

    text = raw_text.strip()
    score = 100

    if len(text) < 50:
        score -= 50
    elif len(text) < 100:
        score -= 30

    lower = text.lower()
    suspicious = ["scam", "fake", "invalid", "forged", "counterfeit"]
    if any(word in lower for word in suspicious):
        score -= 40

    digits = sum(1 for c in text if c.isdigit())
    letters = sum(1 for c in text if c.isalpha())
    total = len(text)

    if total > 0 and digits / total > 0.25:
        score -= 20
    if total > 0 and letters / total < 0.3:
        score -= 20

    return max(0, min(100, score))


def calculate_combined_score(
    raw_text: str,
    competition_name: str | None,
    organizer_name: str | None,
    event_date: str | None,
    search_urls: List[str],
    scraped_data: List[Dict] | None
) -> Tuple[int, str, Dict[str, int]]:
    similarity = text_similarity_score(raw_text, scraped_data)
    field_score = field_confidence_score(
        competition_name,
        organizer_name,
        event_date,
        search_urls,
        scraped_data
    )
    anomaly = anomaly_score(raw_text)

    combined = int((0.4 * similarity) + (0.4 * field_score) + (0.2 * anomaly))

    if combined >= 80:
        status = "Authentic"
    elif combined >= 40:
        status = "Suspicious"
    else:
        status = "Fake"

    details = {
        "similarity": similarity,
        "field_confidence": field_score,
        "anomaly": anomaly
    }

    return combined, status, details


def check_step4_evidence(
    raw_text: str,
    search_urls: List[str],
    competition_name: str | None,
    organizer_name: str | None,
    event_date: str | None,
    scraped_data: List[Dict] | None
) -> bool:
    if _domain_matches_identity(search_urls, organizer_name, competition_name, event_date):
        return True
    if _content_has_competition_and_date(scraped_data or [], competition_name, event_date):
        return True
    return _check_text_consistency(raw_text, search_urls)


def calculate_step_score(
    step1_found: bool,
    step2_found: bool,
    step3_found: bool,
    step4_found: bool,
    step5_found: bool
) -> Tuple[int, str]:
    score = 10
    any_step = any([step1_found, step2_found, step3_found, step4_found, step5_found])

    if not any_step:
        score = 70
    elif step5_found:
        score = 90
    elif step4_found:
        score = 70
    elif step3_found:
        score = 60
    elif step2_found:
        score = 40
    elif step1_found:
        score = 20

    if score >= 80:
        status = "Authentic"
    elif score >= 40:
        status = "Suspicious"
    else:
        status = "Fake"

    return score, status


def calculate_accuracy(
    raw_text: str,
    search_urls: List[str],
    competition_name: str | None = None,
    organizer_name: str | None = None,
    event_date: str | None = None,
    scraped_data: List[Dict] | None = None
) -> Tuple[float, str]:
    """
    Calculate accuracy score and status with fixed rules.

    Rules:
        - Text extracted -> score 20
        - Possible to search -> score 40
        - Search results found -> score 60
        - Domain matches organizer/competition/date -> score 80
        - Competition name + date found on website -> score 95
        - Otherwise -> score 10
    """
    score = 10

    if raw_text and len(raw_text.strip()) > 0:
        score = max(score, 20)

    can_search = (
        competition_name
        and organizer_name
        and competition_name != "Unknown"
        and organizer_name != "Unknown"
    )
    if can_search:
        score = max(score, 40)

    if search_urls and len(search_urls) > 0:
        score = max(score, 60)

    if _domain_matches_identity(search_urls, organizer_name, competition_name, event_date):
        score = max(score, 80)

    if _content_has_competition_and_date(scraped_data or [], competition_name, event_date):
        score = max(score, 95)

    if score >= 80:
        status = "Authentic"
    elif score >= 40:
        status = "Suspicious"
    else:
        status = "Fake"

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
