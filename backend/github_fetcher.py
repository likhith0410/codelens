"""github_fetcher.py — Downloads a public GitHub repo as ZIP and extracts it."""

import os
import re
import zipfile
from pathlib import Path
from typing import Dict

import httpx


class GitHubFetcher:
    REPO_API = "https://api.github.com/repos/{owner}/{repo}"
    ZIP_URL  = "https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"

    def _parse(self, url: str):
        url = url.strip().rstrip("/")
        m   = re.search(r"github\.com[/:]([^/]+)/([^/\s]+?)(?:\.git)?$", url)
        if not m:
            raise ValueError(
                f"Cannot parse GitHub URL: '{url}'. "
                "Expected: https://github.com/owner/repo"
            )
        return m.group(1), m.group(2)

    async def fetch_and_extract(self, repo_url: str, dest_dir: str) -> Dict:
        owner, repo = self._parse(repo_url)
        dest        = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)

        headers = {"Accept": "application/vnd.github+json"}
        token   = os.getenv("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                self.REPO_API.format(owner=owner, repo=repo),
                headers=headers
            )
            if r.status_code == 404:
                raise ValueError(
                    f"Repo not found: {owner}/{repo}. Make sure it's public."
                )
            if r.status_code != 200:
                raise ValueError(f"GitHub API error: {r.status_code}")

            info    = r.json()
            branch  = info.get("default_branch", "main")
            size_kb = info.get("size", 0)
            if size_kb > 50_000:
                raise ValueError(
                    f"Repo is too large ({size_kb // 1024} MB). Limit is 50 MB."
                )

            zr = await client.get(
                self.ZIP_URL.format(owner=owner, repo=repo, branch=branch),
                headers=headers,
                follow_redirects=True
            )
            if zr.status_code != 200:
                raise ValueError(f"Failed to download ZIP: {zr.status_code}")

            zip_path = dest / "repo.zip"
            zip_path.write_bytes(zr.content)

        with zipfile.ZipFile(str(zip_path), "r") as zf:
            zf.extractall(str(dest))
        zip_path.unlink()

        return {
            "repo_owner":     owner,
            "repo_name":      repo,
            "default_branch": branch,
            "repo_url":       repo_url,
        }