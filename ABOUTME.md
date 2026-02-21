# About Me

## Contact

- **Name**: [Likhith Gowda T R]
- **Email**: [likhithgowda88923@gmail.com]
- **GitHub**: [https://github.com/likhith0410]
- **LinkedIn**: [https://www.linkedin.com/in/likhith-gowda-t-r]

---

## Resume

> Please find my resume attached / linked below.
>
> [https://drive.google.com/file/d/1OlxvfvgGb-k_tqgxVcZCMt20tSJMPXW4/view?usp=drivesdk]

---

## Why This Project

I built **CodeLens** to demonstrate my ability to ship a complete, production-quality full-stack application from scratch under time constraints.

The core challenge I found interesting: how do you make a *large, unfamiliar codebase* immediately navigable for a developer? My answer was semantic search + LLM synthesis + explicit citations — so every answer comes with a receipt (file path, line numbers, actual code).

**Technical decisions I'm proud of:**
- Chose Google's embedding API over local ML libraries to avoid Python 3.13/Windows compatibility issues with PyTorch — a pragmatic call that kept setup simple for any environment
- Implemented cosine similarity search in pure numpy rather than adding a FAISS dependency — fewer moving parts, easier to deploy
- Designed the chunking strategy with overlapping 60-line windows so context is preserved at function boundaries
- Built the UI to feel like a real tool, not a demo — with session persistence, Q&A history, tags, and markdown export

**What I'd do with more time:**
- Add hybrid search (keyword + semantic) for better recall on exact identifier names
- Support private GitHub repos via OAuth
- Stream Gemini responses token-by-token for faster perceived response time
- Add a side-by-side diff view to compare answers across commits

---

