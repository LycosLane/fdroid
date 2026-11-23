#!/usr/bin/env python3
"""Sync latest GitHub Release APKs and Fastlane metadata into the F-Droid repo."""

from __future__ import annotations

import io
import json
import os
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

APPS = [
    ("LycosLane/purepodcast", "com.lycoslane.purepodcast"),
    ("LycosLane/pureaudiobooks", "com.lycoslane.pureaudiobooks"),
    ("LycosLane/freedatadiet-mobile", "com.lycoslane.freedatadiet_mobile"),
]

ROOT_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = ROOT_DIR / "repo"
METADATA_DIR = ROOT_DIR / "metadata"
PUBLIC_DIR = ROOT_DIR / "public"


def github_request(url: str, accept: str = "application/vnd.github+json") -> bytes:
    """Perform an authenticated GitHub API or asset request when GITHUB_TOKEN is set."""
    headers = {
        "Accept": accept,
        "User-Agent": "lycoslane-fdroid-sync/1.0",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def pick_apk_asset(release: dict) -> dict | None:
    """Select the primary release APK asset, ignoring debug APKs when a release APK exists."""
    assets = [
        a for a in release.get("assets", [])
        if str(a.get("name", "")).lower().endswith(".apk")
    ]
    if not assets:
        return None
    non_debug = [a for a in assets if "debug" not in str(a.get("name", "")).lower()]
    return non_debug[0] if non_debug else assets[0]


def sync_fastlane_metadata(repo_slug: str, app_id: str) -> None:
    """Download default branch zipball and copy fastlane/metadata/android/* into metadata/<app_id>/."""
    zip_url = f"https://api.github.com/repos/{repo_slug}/zipball"
    try:
        raw_zip = github_request(zip_url, accept="application/vnd.github+json")
    except urllib.error.URLError as exc:
        print(f"[WARN] Could not fetch zipball for {repo_slug}: {exc}")
        return

    target_dir = METADATA_DIR / app_id
    marker = "/fastlane/metadata/android/"
    copied = 0

    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            normalized = info.filename.replace("\\", "/")
            idx = normalized.find(marker)
            if idx < 0:
                continue
            rel = normalized[idx + len(marker):].lstrip("/")
            if not rel or ".." in rel.split("/"):
                continue

            if copied == 0 and target_dir.exists():
                shutil.rmtree(target_dir)

            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            copied += 1

    if copied > 0:
        print(f"[OK] Synced {copied} Fastlane files for {app_id}")
    else:
        print(f"[INFO] No Fastlane metadata found in {repo_slug}, using {app_id}.yml")


def write_landing_page(synced_apps: list[dict[str, str]]) -> None:
    """Write a minimal static landing page for the GitHub Pages F-Droid repository."""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"      <li><strong>{app['name']}</strong> (<code>{app['app_id']}</code>) - "
        f"<a href=\"{app['url']}\">{app['tag']}</a></li>"
        for app in synced_apps
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LycosLane Apps - F-Droid Repository</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #161a1c; }}
    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }}
    .box {{ background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 14px 18px; margin: 16px 0; }}
  </style>
</head>
<body>
  <h1>LycosLane Apps - F-Droid Repository</h1>
  <p>Add this repository URL in <strong>F-Droid</strong>, <strong>Droid-ify</strong>, or <strong>Neo Store</strong> to install and automatically update all Pure Suite Android apps:</p>
  <div class="box">
    <code>https://lycoslane.github.io/fdroid/repo</code>
  </div>
  <h2>Available Apps</h2>
  <ul>
{rows}
  </ul>
</body>
</html>
"""
    with open(PUBLIC_DIR / "index.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(html)


def main() -> None:
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    synced_apps: list[dict[str, str]] = []

    for repo_slug, app_id in APPS:
        release_url = f"https://api.github.com/repos/{repo_slug}/releases/latest"
        try:
            release = json.loads(github_request(release_url).decode("utf-8"))
        except urllib.error.URLError as exc:
            print(f"[WARN] Failed to fetch latest release for {repo_slug}: {exc}")
            continue

        asset = pick_apk_asset(release)
        if asset is None:
            print(f"[WARN] No APK asset found in latest release for {repo_slug}")
            continue

        tag = str(release.get("tag_name", "latest"))
        apk_name = Path(str(asset["name"])).name
        apk_dest = REPO_DIR / apk_name
        download_url = str(asset["browser_download_url"])

        print(f"[DL] {repo_slug} ({tag}) -> {apk_name}")
        apk_bytes = github_request(download_url, accept="application/octet-stream")
        with open(apk_dest, "wb") as f:
            f.write(apk_bytes)

        sync_fastlane_metadata(repo_slug, app_id)
        synced_apps.append({
            "name": repo_slug.split("/")[-1],
            "app_id": app_id,
            "tag": tag,
            "url": str(release.get("html_url", f"https://github.com/{repo_slug}/releases")),
        })

    if not synced_apps:
        raise RuntimeError("No APKs were synced from any configured GitHub repository.")

    write_landing_page(synced_apps)
    print(f"[DONE] Synced {len(synced_apps)} app(s) into {REPO_DIR}")


if __name__ == "__main__":
    main()
