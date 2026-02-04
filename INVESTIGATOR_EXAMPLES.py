"""
Example Usage of the Expert Investigator Module
Demonstrates how to use certificate_investigator.py
"""

from certificate_investigator import investigate_certificate, run_investigation_summary
import json

# ============================================================================
# EXAMPLE 1: Legitimate Certificate (Should return "Verified")
# ============================================================================

print("=" * 80)
print("EXAMPLE 1: LEGITIMATE CERTIFICATE")
print("=" * 80)

# Sample data for a legitimate BEAR Summit certificate
legitimate_data = {
    "candidate_name": "Ahmed Hassan",
    "competition_name": "BEAR Summit 2025",
    "organizer": "ICT Division Bangladesh",
    "extracted_text": """
BEAR SUMMIT 2025 AND NATIONAL 
TECHNOLOGY COMPETITION

Certificate of Participation

This is to certify that Ahmed Hassan has successfully 
participated in the BEAR Summit 2025, a national level 
technology competition organized by the ICT Division 
of Bangladesh, held on 16-17 July 2025 in Dhaka.

Organized by: ICT Division Bangladesh
Location: Dhaka
Date: 16-17 July 2025

Signature: _______________
    """,
    "web_info": [
        {
            "url": "https://ictnewsbangladesh.com/bear-summit-2025",
            "content": """
BEAR Summit 2025: Bangladesh's Biggest Tech Event

Dhaka, June 2025 - The ICT Division is proud to announce 
the BEAR Summit 2025, a national technology competition 
bringing together the brightest minds from across Bangladesh.

Event Details:
- Dates: 16-17 July 2025
- Location: Dhaka Convention Center, Dhaka
- Organizer: ICT Division Bangladesh
- Expected Participants: 500+
- Categories: AI, Web Development, Cybersecurity

Certificates will be awarded to all participants and winners 
in each category. This is a legitimate government-sponsored event.
            """
        },
        {
            "url": "https://facebook.com/events/bear-summit-2025",
            "content": """
BEAR Summit 2025 - Official Facebook Event

500+ people interested in this event
100+ going

Event Description:
Join Bangladesh's premier technology summit! Network with industry 
professionals, learn cutting-edge technologies, and compete for prizes.

Date: July 16-17, 2025
Location: Dhaka, Bangladesh
Organizer: ICT Division Bangladesh

#BearSummit2025 #BangladeshTech #ICTDIV
            """
        }
    ],
    "event_date": "16-17 July 2025",
    "location": "Dhaka, Bangladesh"
}

# Run investigation
result_1 = investigate_certificate(**legitimate_data)

print("\n📊 INVESTIGATION RESULT:")
print(json.dumps(result_1, indent=2))

print("\n📝 SUMMARY:")
print(run_investigation_summary(result_1))


# ============================================================================
# EXAMPLE 2: Suspicious Certificate (Should return "Suspicious")
# ============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 2: SUSPICIOUS CERTIFICATE")
print("=" * 80)

suspicious_data = {
    "candidate_name": "John Doe",
    "competition_name": "Tech Masterclass 2025",
    "organizer": "Innovation Hub",
    "extracted_text": """
TECH MASTERCLASS 2025
Certificate of Completion

This certifies that John Doe has completed the 
Tech Masterclass 2025 organized by Innovation Hub.
Completion Date: March 15, 2025

Signature: _______________
    """,
    "web_info": [
        {
            "url": "https://www.linkedin.com/posts/user-review",
            "content": """
Just completed Tech Masterclass 2025! Great learning experience 
with Innovation Hub. #TechMasterclass #Learning
            """
        }
    ],
    "event_date": "March 15, 2025",
    "location": "Bangladesh"
}

result_2 = investigate_certificate(**suspicious_data)

print("\n📊 INVESTIGATION RESULT:")
print(json.dumps(result_2, indent=2))

print("\n📝 SUMMARY:")
print(run_investigation_summary(result_2))


# ============================================================================
# EXAMPLE 3: Fake Certificate (Should return "Fake")
# ============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 3: FAKE CERTIFICATE")
print("=" * 80)

fake_data = {
    "candidate_name": "Fake Name",
    "competition_name": "World Super Elite Competition 2025",
    "organizer": "Global Elite Institute",
    "extracted_text": """
WORLD SUPER ELITE COMPETITION 2025
Certificate of Achievement

This is to certify that Fake Name has won first prize 
in the World Super Elite Competition 2025.

Organized by: Global Elite Institute
Location: International City
Date: 1-2 August 2025

We congratulate the winner!

Signature: _______________
    """,
    "web_info": [],  # No web data found
    "event_date": "1-2 August 2025",
    "location": "International City, Bangladesh"
}

result_3 = investigate_certificate(**fake_data)

print("\n📊 INVESTIGATION RESULT:")
print(json.dumps(result_3, indent=2))

print("\n📝 SUMMARY:")
print(run_investigation_summary(result_3))


# ============================================================================
# EXAMPLE 4: Integration with Streamlit (as used in app.py)
# ============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 4: STREAMLIT INTEGRATION PATTERN")
print("=" * 80)

print("""
# In app.py (Step 6 of verification flow):

import streamlit as st
from certificate_investigator import investigate_certificate

# After getting OCR data and web scraping results...
try:
    investigation_result = investigate_certificate(
        candidate_name=candidate_name,
        competition_name=competition_name,
        organizer=organizer_name,
        extracted_text=raw_text,
        web_info=scraped_data,
        event_date=event_date,
        location=location
    )
    
    # Display results
    investigator_status = investigation_result.get('status')
    investigator_score = investigation_result.get('accuracy_score')
    investigator_reasoning = investigation_result.get('reasoning')
    investigator_evidence = investigation_result.get('evidence_found')
    
    # Show metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Investigation Score", f"{investigator_score}/100")
    with col2:
        st.metric("Status", investigator_status)
    with col3:
        st.metric("Event Found Online", 
                  "✅ Yes" if investigation_result.get('event_found_online') else "❌ No")
    
    # Show verdict
    if investigator_status == "Verified":
        st.success("✅ Certificate Verified")
    elif investigator_status == "Suspicious":
        st.warning("⚠️ Certificate Suspicious - Manual Review Needed")
    else:
        st.error("❌ Certificate Likely Fake")
    
    # Show reasoning
    st.info(investigator_reasoning)
    
except Exception as e:
    st.warning(f"Investigation unavailable: {str(e)}")
""")


# ============================================================================
# EXAMPLE 5: Batch Investigation (Multiple Certificates)
# ============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 5: BATCH INVESTIGATION PATTERN")
print("=" * 80)

certificates = [legitimate_data, suspicious_data, fake_data]
results = []

for cert in certificates:
    result = investigate_certificate(**cert)
    results.append(result)

print("\n📊 BATCH RESULTS SUMMARY:")
for i, result in enumerate(results, 1):
    print(f"\nCertificate {i}:")
    print(f"  Status: {result['status']}")
    print(f"  Score: {result['accuracy_score']}/100")
    print(f"  Event Found: {result['event_found_online']}")

# Save results to file
with open("investigation_results.json", "w") as f:
    json.dump(results, f, indent=2)
print("\n✅ Results saved to investigation_results.json")


# ============================================================================
# EXAMPLE 6: Response Handling Best Practices
# ============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 6: RESPONSE HANDLING BEST PRACTICES")
print("=" * 80)

print("""
# Best practices for handling investigator responses:

def handle_investigation_result(result):
    '''Process investigation result safely'''
    
    # 1. Check if result is valid
    if not result or 'status' not in result:
        return "ERROR: Invalid result format"
    
    # 2. Extract values safely with defaults
    status = result.get('status', 'Unknown')
    score = result.get('accuracy_score', 0)
    reasoning = result.get('reasoning', 'No reasoning provided')
    
    # 3. Handle different statuses
    if status == "Verified":
        action = "ACCEPT CERTIFICATE"
        confidence = "HIGH"
    elif status == "Suspicious":
        action = "MANUAL REVIEW REQUIRED"
        confidence = "MEDIUM"
    else:  # Fake
        action = "REJECT CERTIFICATE"
        confidence = "HIGH"
    
    # 4. Build response object
    response = {
        "action": action,
        "confidence": confidence,
        "score": score,
        "reasoning": reasoning,
        "evidence": result.get('evidence_found', 'None'),
        "verification_flags": {
            "candidate": result.get('candidate_verified', False),
            "organizer": result.get('organizer_verified', False),
            "event": result.get('event_found_online', False)
        }
    }
    
    return response

# Usage
investigation = investigate_certificate(...)
action_response = handle_investigation_result(investigation)
print(f"Action: {action_response['action']}")
print(f"Confidence: {action_response['confidence']}")
print(f"Reasoning: {action_response['reasoning']}")
""")


# ============================================================================
# EXAMPLE 7: Error Handling
# ============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 7: ERROR HANDLING")
print("=" * 80)

print("""
# Handling errors gracefully:

from certificate_investigator import investigate_certificate
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def safe_investigate(certificate_data):
    '''Safely run investigation with error handling'''
    
    try:
        # Validate input
        required_fields = ['candidate_name', 'competition_name', 'organizer', 
                          'extracted_text', 'web_info']
        
        for field in required_fields:
            if field not in certificate_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Run investigation
        result = investigate_certificate(**certificate_data)
        
        logger.info(f"Investigation complete: {result['status']}")
        return result
        
    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        return {
            "status": "Suspicious",
            "accuracy_score": 0,
            "reasoning": f"Input validation failed: {str(e)}",
            "evidence_found": "None"
        }
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            "status": "Suspicious",
            "accuracy_score": 0,
            "reasoning": "Investigation error - please try again",
            "evidence_found": "None"
        }

# Usage
result = safe_investigate(legitimate_data)
""")

print("\n" + "=" * 80)
print("END OF EXAMPLES")
print("=" * 80)
