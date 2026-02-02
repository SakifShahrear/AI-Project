"""Test with a known real certificate"""

from search_agent import search_competition

# Test with a well-known hackathon/competition
test_cases = [
    {
        "name": "BEAR SUMMIT AND NATIONAL SEMICONDUCTOR SYMPOSIUM 2025",
        "organizer": "ICT DIVISION"
    },
    {
        "name": "Google Code Jam 2024",
        "organizer": "Google"
    },
    {
        "name": "NASA Space Apps Challenge",
        "organizer": "NASA"
    }
]

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
        for i, url in enumerate(results[:5], 1):  # Show first 5
            print(f"  {i}. {url}")
    else:
        print("  ❌ No relevant results")
    print()
