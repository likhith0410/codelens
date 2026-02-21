"""
Run this to see exactly which models your API key can use.
Usage: python check_models.py
"""
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY", "").strip()
if not api_key:
    print("ERROR: GEMINI_API_KEY not found in .env")
    exit(1)

print(f"Using key: {api_key[:10]}...{api_key[-4:]}")
print()

import google.generativeai as genai
genai.configure(api_key=api_key)

print("All available models that support generateContent:")
print("-" * 60)
found = []
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(f"  {m.name}")
        found.append(m.name)

print()
if not found:
    print("NO models found! Your API key is invalid or has no permissions.")
    print("Go to: https://aistudio.google.com/app/apikey")
    print("Click: Create API key -> Create API key in NEW project")
else:
    print(f"Found {len(found)} usable models. Use any of the names above in qa_engine.py")