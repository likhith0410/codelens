#!/usr/bin/env python3
"""run.py — Start CodeLens. Usage: python run.py"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("GEMINI_API_KEY"):
    print("=" * 60)
    print("  ERROR: GEMINI_API_KEY is not set!")
    print("  1. Copy .env.example to .env")
    print("  2. Get free key: https://aistudio.google.com/app/apikey")
    print("  3. Add to .env: GEMINI_API_KEY=your_key_here")
    print("=" * 60)
    sys.exit(1)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"\n🔍 CodeLens — Codebase Q&A with Proof")
    print(f"   Running at: http://localhost:{port}")
    print(f"   Status:     http://localhost:{port}/status")
    print(f"   Ctrl+C to stop\n")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)