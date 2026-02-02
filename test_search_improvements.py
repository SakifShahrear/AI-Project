"""Test search improvements with progressive keyword strategy"""

from search_agent import search_competition

# Test certificate data
test_certificate = {
    "competition_name": "BEAR SUMMIT AND NATIONAL SEMICONDUCTOR SYMPOSIUM 2025",
    "organizer": "ICT DIVISION"
}

print("=" * 80)
print("TESTING IMPROVED SEARCH")
print("=" * 80)
print(f"\nCertificate: {test_certificate['competition_name']}")
print(f"Organizer: {test_certificate['organizer']}")
print()

# Run search
results = search_competition(
    test_certificate["competition_name"],
    test_certificate["organizer"],
    max_results=10
)

print()
print("=" * 80)
print(f"FINAL RESULTS: {len(results)} URLs found")
print("=" * 80)

if results:
    for i, url in enumerate(results, 1):
        print(f"{i}. {url}")
else:
    print("❌ No results found")
