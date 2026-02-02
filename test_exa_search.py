"""Test Exa.ai search integration"""

from search_agent import search_competition

# Test with known competitions
test_cases = [
    {
        "name": "Google Code Jam 2024",
        "organizer": "Google"
    },
    {
        "name": "NASA Space Apps Challenge",
        "organizer": "NASA"
    },
    {
        "name": "TechCrunch Disrupt Hackathon",
        "organizer": "TechCrunch"
    }
]

print("=" * 80)
print("TESTING EXA.AI INTEGRATION")
print("=" * 80)
print("\nNote: Set EXA_API_KEY environment variable for Exa.ai to work")
print("Sign up at: https://exa.ai\n")

for test in test_cases:
    print("=" * 80)
    print(f"Testing: {test['name']}")
    print(f"Organizer: {test['organizer']}")
    print("=" * 80)
    
    results = search_competition(
        test["name"],
        test["organizer"],
        max_results=10
    )
    
    print()
    print(f"✅ Found {len(results)} URLs")
    if results:
        for i, url in enumerate(results[:5], 1):
            print(f"  {i}. {url}")
    else:
        print("  ❌ No results found")
    print()
