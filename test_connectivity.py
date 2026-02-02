#!/usr/bin/env python
"""
Simple test to check if googlesearch library can reach Google
"""

def test_basic_import():
    print("✓ Testing google-generativeai import... ", end="")
    try:
        import google.generativeai as genai
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
    
    print("✓ Testing googlesearch import... ", end="")
    try:
        from googlesearch import search
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
    
    print("\n✓ Quick connectivity test:")
    try:
        import urllib.request
        response = urllib.request.urlopen("https://www.google.com", timeout=5)
        print(f"  ✅ Can reach google.com (status: {response.status})")
    except Exception as e:
        print(f"  ❌ Cannot reach google.com: {e}")
        print("     Note: This might be blocked by firewall/VPN")

if __name__ == "__main__":
    print("=" * 60)
    print("📋 Dependency Check")
    print("=" * 60)
    test_basic_import()
    print("\n" + "=" * 60)
    print("If googlesearch works but returns 0 results, it's likely")
    print("Google is rate-limiting. Try again after a few minutes.")
    print("=" * 60)
