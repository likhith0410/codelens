"""
diagnose_and_fix.py
Run this to find which model actually works for YOUR key: python diagnose_and_fix.py
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY", "").strip()
print(f"Key: {api_key[:12]}...{api_key[-4:]}\n")

import google.generativeai as genai
genai.configure(api_key=api_key)

# Test each model with a real tiny request
candidates = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-001",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash",
]

print("Testing models with a real request...")
print("-" * 50)
working = None
for name in candidates:
    try:
        m = genai.GenerativeModel(name)
        r = m.generate_content(
            "Say the word: ok",
            generation_config=genai.GenerationConfig(max_output_tokens=5)
        )
        print(f"  WORKS: {name}  -> response: {r.text.strip()}")
        if not working:
            working = name
    except Exception as e:
        short = str(e)[:120].replace('\n', ' ')
        print(f"  FAIL:  {name}  -> {short}")

print()
if working:
    print(f"*** WORKING MODEL: {working} ***")
    print(f"\nNow run this to patch your qa_engine.py:")
    print(f'  python -c "')
    print(f"  import re")
    print(f"  f = open('backend/qa_engine.py').read()")
    print(f"  f = re.sub(r'GEMINI_MODEL = .*', 'GEMINI_MODEL = \\\"{working}\\\"', f)")
    print(f"  open('backend/qa_engine.py','w').write(f)")
    print(f'  print(\\\"Patched!\\\")')
    print(f'  "')
else:
    print("NO model works. Your API key has quota 0 on all models.")
    print("You MUST create a brand new key from a different Google account.")
    print("Go to: https://aistudio.google.com/app/apikey")