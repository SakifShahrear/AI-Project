from googlesearch import search

print("Testing googlesearch-python library...")
print("=" * 50)

# Test 1: Simple query
print("\n1. Simple query: 'Bangladesh'")
try:
    results = list(search('Bangladesh', num_results=3, sleep_interval=1))
    print(f"   Results: {len(results)}")
    if results:
        for i, url in enumerate(results, 1):
            print(f"   {i}. {url}")
    else:
        print("   ❌ BLOCKED/NO RESULTS")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 2: With site restriction
print("\n2. Site-restricted: 'Bangladesh site:.bd'")
try:
    results = list(search('Bangladesh site:.bd', num_results=3, sleep_interval=1))
    print(f"   Results: {len(results)}")
    if results:
        for i, url in enumerate(results, 1):
            print(f"   {i}. {url}")
    else:
        print("   ❌ BLOCKED/NO RESULTS")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

print("\n" + "=" * 50)
print("CONCLUSION:")
if len(list(search('test', num_results=1))) == 0:
    print("❌ googlesearch-python is BLOCKED or RATE-LIMITED")
else:
    print("✅ googlesearch-python is WORKING")
