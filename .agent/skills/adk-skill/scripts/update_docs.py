#!/usr/bin/env python3
"""
ADK Documentation Synchronizer
Fetches and updates llms-full.txt and llms.txt based on the canonical pointer at:
https://github.com/google/adk-python/blob/main/llms-full.txt

Ensures the skill references remain strictly up-to-date with the latest Google ADK documentation.
Uses only Python standard library modules (zero external dependencies).
All paths are relative to this skill's root directory.
"""

import argparse
import datetime
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Canonical pointer in the google/adk-python repository
GITHUB_POINTER_URL = "https://raw.githubusercontent.com/google/adk-python/main/llms-full.txt"
DEFAULT_LLMS_FULL_URL = "https://adk.dev/llms-full.txt"
DEFAULT_LLMS_INDEX_URL = "https://adk.dev/llms.txt"


def get_skill_root() -> Path:
    """Returns the root directory of the adk-skill folder (.agent/skills/adk-skill)."""
    return Path(__file__).resolve().parent.parent


def get_references_dir() -> Path:
    """Returns the references directory within the skill folder."""
    refs = get_skill_root() / "references"
    refs.mkdir(parents=True, exist_ok=True)
    return refs


def fetch_text(url: str, timeout: int = 30) -> tuple[str, dict]:
    """Fetches text content from a URL, returning content and response headers."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ADK-Agent-Skill-Updater/1.0 (+https://antigravity.google)",
            "Accept": "text/plain, text/markdown, text/*, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        content = resp.read().decode(charset, errors="replace")
        headers = dict(resp.headers)
        return content, headers


def resolve_documentation_urls(timeout: int = 30) -> tuple[str, str]:
    """
    Fetches the pointer from GitHub and extracts target URLs for llms-full.txt and llms.txt.
    Falls back to canonical adk.dev defaults if GitHub is unreachable or format changes.
    """
    print(f"[*] Checking canonical ADK documentation pointer: {GITHUB_POINTER_URL}")
    full_url = DEFAULT_LLMS_FULL_URL
    index_url = DEFAULT_LLMS_INDEX_URL

    try:
        content, _ = fetch_text(GITHUB_POINTER_URL, timeout=timeout)
        links = re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", content)
        for label, target in links:
            lower_label = label.lower()
            lower_target = target.lower()
            if "llms-full" in lower_label or "llms-full" in lower_target:
                full_url = target
            elif "llms.txt" in lower_label or lower_target.endswith("/llms.txt"):
                index_url = target
        print(f"[+] Resolved llms-full.txt URL: {full_url}")
        print(f"[+] Resolved llms.txt URL:      {index_url}")
    except Exception as e:
        print(f"[!] Warning: Could not resolve GitHub pointer ({e}). Using canonical defaults:")
        print(f"    - Full:  {full_url}")
        print(f"    - Index: {index_url}")

    return full_url, index_url


def update_file(url: str, destination: Path, timeout: int = 30, check_only: bool = False) -> bool:
    """Downloads content from url and saves to destination if changed."""
    print(f"[*] Fetching: {url} -> {destination.name}")
    try:
        content, headers = fetch_text(url, timeout=timeout)
        size_bytes = len(content.encode("utf-8"))

        if check_only:
            print(f"[i] Check-only: Remote is available ({size_bytes} bytes). Not written.")
            return True

        # Check if local file already exists and has identical content
        if destination.exists():
            existing_content = destination.read_text(encoding="utf-8", errors="replace")
            if existing_content == content:
                print(f"[=] Content unchanged for {destination.name} ({size_bytes} bytes).")
                return True

        destination.write_text(content, encoding="utf-8")
        print(f"[+] Successfully updated {destination.name} ({size_bytes:,} bytes).")
        return True
    except urllib.error.URLError as e:
        print(f"[!] Network error fetching {url}: {e}")
        if destination.exists():
            print(f"[i] Using existing cached version of {destination.name}.")
            return True
        return False
    except Exception as e:
        print(f"[!] Error updating {destination.name}: {e}")
        return False


def run_sync(force: bool = False, check_only: bool = False, timeout: int = 30) -> int:
    """Synchronizes both llms-full.txt and llms.txt into references/."""
    skill_root = get_skill_root()
    refs_dir = get_references_dir()
    meta_file = refs_dir / ".last_updated.json"

    print(f"=== Google ADK Documentation Synchronizer ===")
    print(f"Skill root: {skill_root}")
    print(f"Target dir: {refs_dir}")

    full_url, index_url = resolve_documentation_urls(timeout=timeout)

    target_full = refs_dir / "llms-full.txt"
    target_index = refs_dir / "llms.txt"

    success_full = update_file(full_url, target_full, timeout=timeout, check_only=check_only)
    success_index = update_file(index_url, target_index, timeout=timeout, check_only=check_only)

    if not check_only and (success_full or success_index):
        meta = {
            "last_updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "pointer_source": GITHUB_POINTER_URL,
            "llms_full_url": full_url,
            "llms_index_url": index_url,
            "full_file_size_bytes": target_full.stat().st_size if target_full.exists() else 0,
            "index_file_size_bytes": target_index.stat().st_size if target_index.exists() else 0,
        }
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"[+] Updated sync metadata in references/.last_updated.json")

    print("=== Synchronization Complete ===")
    return 0 if (success_full and success_index) else 1


def main():
    parser = argparse.ArgumentParser(
        description="Synchronize Google Agent Development Kit (ADK) llms-full.txt and llms.txt reference files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--force", action="store_true", help="Force refresh even if recent")
    parser.add_argument("--check-only", action="store_true", help="Check remote connectivity without writing")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    args = parser.parse_args()

    sys.exit(run_sync(force=args.force, check_only=args.check_only, timeout=args.timeout))


if __name__ == "__main__":
    main()
