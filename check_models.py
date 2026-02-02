import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("❌ GEMINI_API_KEY not found in .env file")
    exit(1)

genai.configure(api_key=api_key)

print("🔍 Checking available Gemini models...\n")

try:
    models = genai.list_models()
    print("✅ Available models that support generateContent:\n")
    
    for model in models:
        if 'generateContent' in model.supported_generation_methods:
            print(f"  ✓ {model.name}")
    
except Exception as e:
    print(f"❌ Error: {e}")
