"""
qa_engine.py — Q&A using gemini-embedding-001 retrieval + Gemini 2.5 Flash generation.
"""

import os
import logging
from typing import Dict, Any
from pathlib import Path

import google.generativeai as genai

from .indexer import CodebaseIndexer

logger = logging.getLogger("codelens.qa")

GEMINI_MODEL = "gemini-2.5-flash"   # confirmed working on this API key


class QAEngine:
    def __init__(self, indexer: CodebaseIndexer):
        self.indexer = indexer

    def _configure(self):
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com/app/apikey"
            )
        genai.configure(api_key=api_key)

    def answer(self, session_id: str, question: str,
               generate_refactor: bool = False) -> Dict[str, Any]:
        self._configure()

        chunks = self.indexer.search(session_id, question, top_k=8)
        if not chunks:
            logger.warning('"event":"no_chunks","session":"%s"', session_id)
            return {
                "answer": (
                    "No relevant code found for your question. "
                    "Try rephrasing or upload a different codebase."
                ),
                "snippets": [],
                "refactor_suggestions": None,
            }

        context = "\n\n".join(
            f"[{i+1}] {c['file']} (lines {c['line_start']}-{c['line_end']}):\n"
            f"```\n{c['raw']}\n```"
            for i, c in enumerate(chunks)
        )

        prompt = (
            "You are an expert code analyst. Answer the developer's question "
            "using ONLY the provided code snippets below.\n\n"
            f"QUESTION: {question}\n\n"
            f"CODE SNIPPETS:\n{context}\n\n"
            "INSTRUCTIONS:\n"
            "- Give a clear, direct answer referencing specific file paths and line numbers.\n"
            "- Format file references like: `filename.py (lines X-Y)`\n"
            "- Quote short inline code using backticks when helpful.\n"
            "- If the answer spans multiple files, explain how they interact.\n"
            "- If the question cannot be answered from the snippets, say so clearly.\n"
            "- Do NOT invent file paths or code that is not in the snippets.\n\n"
            "Respond in markdown format."
        )

        model    = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.2, max_output_tokens=1500),
        )
        answer_text = response.text.strip()
        logger.info('"event":"answer_generated","session":"%s","chunks":%d',
                    session_id, len(chunks))

        refactor = None
        if generate_refactor and chunks:
            top = chunks[0]
            r   = model.generate_content(
                "You are a senior software engineer. "
                "Review this code and give 3-5 concrete refactor suggestions.\n\n"
                f"File: {top['file']} (lines {top['line_start']}-{top['line_end']})\n"
                f"```\n{top['raw']}\n```\n\n"
                "Format each suggestion as:\n"
                "**Issue**: [problem]\n"
                "**Suggestion**: [fix]\n"
                "**Why**: [reason]",
                generation_config=genai.GenerationConfig(
                    temperature=0.3, max_output_tokens=800),
            )
            refactor = r.text.strip()

        return {
            "answer":               answer_text,
            "snippets":             [{**c, "language": _lang(c["file"])} for c in chunks],
            "refactor_suggestions": refactor,
        }


def _lang(filename: str) -> str:
    ext_map = {
        ".py": "python",   ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx",     ".tsx": "tsx",        ".java": "java",
        ".go": "go",       ".rb": "ruby",        ".rs": "rust",
        ".cpp": "cpp",     ".c": "c",            ".h": "c",
        ".hpp": "cpp",     ".cs": "csharp",      ".php": "php",
        ".swift": "swift", ".kt": "kotlin",      ".sh": "bash",
        ".bash": "bash",   ".yml": "yaml",       ".yaml": "yaml",
        ".toml": "toml",   ".json": "json",      ".sql": "sql",
        ".html": "html",   ".css": "css",        ".md": "markdown",
    }
    return ext_map.get(Path(filename).suffix.lower(), "text")