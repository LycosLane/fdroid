#!/usr/bin/env python3
"""Sync latest GitHub Release APKs and Fastlane metadata into the F-Droid repo."""

from __future__ import annotations

import html as html_lib
import io
import json
import os
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

APPS = [
    (
        "LycosLane/purepodcast",
        "com.lycoslane.purepodcast",
        "PurePodcast",
        "Multimedia",
        "Why PurePodcast: Most podcast apps either lock storage-saving compression behind paid subscriptions, clutter the UI with ads, or lack channel-level audio repair. PurePodcast is 100% free, ad-free, and built purely on native AndroidX/Media3.",
    ),
    (
        "LycosLane/pureaudiobooks",
        "com.lycoslane.pureaudiobooks",
        "PureAudiobooks",
        "Multimedia",
        "Why PureAudiobooks: Generic players ignore broken stereo rips, mixed album tags, and speed-adjusted remaining time. PureAudiobooks gives you a calm SAF-folder library with live channel repair, tag splitting, and local sidecar metadata.",
    ),
    (
        "LycosLane/freedatadiet-mobile",
        "com.lycoslane.freedatadiet_mobile",
        "FreeDataDiet Mobile",
        "System",
        "Why FreeDataDiet: Storage cleaners on Play Store are full of ads, trackers, and fake RAM boosters. FreeDataDiet requests zero internet permission, flattens entire folder trees for instant sorting, and verifies duplicates with 2-pass SHA-256.",
    ),
]

ROOT_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = ROOT_DIR / "repo"
METADATA_DIR = ROOT_DIR / "metadata"
PUBLIC_DIR = ROOT_DIR / "public"
FINGERPRINT = "E104F7455B72D8FF7A9F9501B399214AC5AE1FE2707AD3673B638542A66A8397"


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


def read_app_store_copy(app_id: str) -> tuple[str, list[str], str]:
    """Read short description, bullet highlights, and icon path from synced Fastlane metadata."""
    en_dir = METADATA_DIR / app_id / "en-US"
    short_file = en_dir / "short_description.txt"
    full_file = en_dir / "full_description.txt"
    icon_file = en_dir / "images" / "icon.png"

    short_desc = short_file.read_text(encoding="utf-8").strip() if short_file.exists() else ""
    bullets: list[str] = []
    if full_file.exists():
        for line in full_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                bullets.append(stripped[2:].strip())
            if len(bullets) >= 4:
                break

    icon_rel = ""
    if icon_file.exists():
        icons_out = PUBLIC_DIR / "icons"
        icons_out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(icon_file, icons_out / f"{app_id}.png")
        icon_rel = f"icons/{app_id}.png"

    return short_desc, bullets, icon_rel


def write_landing_page(synced_apps: list[dict[str, object]]) -> None:
    """Write the Obsidian-themed static landing page for the GitHub Pages F-Droid repo."""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    for asset_name in ("repo-qr.png", "repo-icon.png", "logo-android-fedora.svg"):
        src = ROOT_DIR / "assets" / asset_name
        if src.exists():
            shutil.copyfile(src, PUBLIC_DIR / asset_name)

    repo_url = "https://lycoslane.github.io/fdroid/repo"
    verified_url = f"{repo_url}?fingerprint={FINGERPRINT}"
    fdroid_intent_url = f"fdroidrepos://lycoslane.github.io/fdroid/repo?fingerprint={FINGERPRINT}"

    cards_html = []
    for app in synced_apps:
        name = html_lib.escape(str(app["display_name"]))
        tag = html_lib.escape(str(app["tag"]))
        category = html_lib.escape(str(app["category"]))
        repo_link = html_lib.escape(str(app["repo_url"]))
        apk_link = html_lib.escape(str(app["apk_url"]))
        short_desc = html_lib.escape(str(app["short_desc"]))
        why_copy = html_lib.escape(str(app["why_copy"]))
        icon_rel = str(app["icon_rel"])
        bullets = app["bullets"]

        icon_tag = (
            f'<img class="app-icon" src="{html_lib.escape(icon_rel)}" alt="{name} icon" />'
            if icon_rel else ""
        )
        bullets_html = "".join(
            f"<li>{html_lib.escape(str(b))}</li>" for b in bullets
        )
        cards_html.append(f"""      <article class="app-card">
        <div class="app-head">
          {icon_tag}
          <div>
            <div class="app-title-row">
              <h3>{name}</h3>
              <span class="badge badge-version">{tag}</span>
              <span class="badge badge-cat">{category}</span>
            </div>
            <p class="app-short">{short_desc}</p>
          </div>
        </div>
        <p class="app-why">{why_copy}</p>
        <ul class="app-bullets">{bullets_html}</ul>
        <div class="app-actions">
          <a class="btn btn-secondary" href="{repo_link}">GitHub Source</a>
          <a class="btn btn-outline" href="{apk_link}">Direct APK</a>
        </div>
      </article>""")

    apps_block = "\n".join(cards_html)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LycosLane Apps - F-Droid Repository</title>
  <link rel="icon" type="image/png" href="repo-icon.png">
  <style>
    :root {{
      --bg: #101216;
      --surface: #171A21;
      --card: #1E222B;
      --border: #2B313E;
      --text: #ECEFF4;
      --muted: #94A3B8;
      --cyan: #00B4FF;
      --amber: #FFB020;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      line-height: 1.6;
    }}
    .wrap {{
      max-width: 960px;
      margin: 0 auto;
      padding: 36px 20px 64px;
    }}
    .hero {{
      display: flex;
      align-items: center;
      gap: 20px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 24px;
    }}
    .hero-logo {{
      width: 84px;
      height: 84px;
      border-radius: 20px;
      flex-shrink: 0;
    }}
    .hero h1 {{
      margin: 0 0 6px;
      font-size: 1.75rem;
      line-height: 1.2;
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
    }}
    .accent-bar {{
      display: inline-flex;
      gap: 6px;
      margin-top: 10px;
    }}
    .pill-cyan {{
      background: rgba(0, 180, 255, 0.14);
      color: var(--cyan);
      border: 1px solid rgba(0, 180, 255, 0.35);
      font-size: 0.78rem;
      font-weight: 600;
      padding: 2px 10px;
      border-radius: 999px;
    }}
    .pill-amber {{
      background: rgba(255, 176, 32, 0.14);
      color: var(--amber);
      border: 1px solid rgba(255, 176, 32, 0.35);
      font-size: 0.78rem;
      font-weight: 600;
      padding: 2px 10px;
      border-radius: 999px;
    }}
    .setup-grid {{
      display: grid;
      grid-template-columns: 280px 1fr;
      gap: 20px;
      margin-bottom: 32px;
    }}
    @media (max-width: 740px) {{
      .hero {{ flex-direction: column; text-align: center; }}
      .accent-bar {{ justify-content: center; }}
      .setup-grid {{ grid-template-columns: 1fr; }}
    }}
    .panel {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 20px;
    }}
    .qr-panel {{
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      justify-content: center;
    }}
    .qr-box {{
      background: #FFFFFF;
      padding: 10px;
      border-radius: 12px;
      margin-bottom: 14px;
    }}
    .qr-box img {{
      display: block;
      width: 196px;
      height: 196px;
    }}
    .btn {{
      display: inline-block;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.92rem;
      padding: 10px 16px;
      border-radius: 8px;
      transition: opacity 0.15s ease;
    }}
    .btn:hover {{ opacity: 0.9; }}
    .btn-primary {{
      background: var(--cyan);
      color: #081218;
      width: 100%;
      text-align: center;
    }}
    .btn-secondary {{
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
    }}
    .btn-outline {{
      background: rgba(255, 176, 32, 0.12);
      color: var(--amber);
      border: 1px solid rgba(255, 176, 32, 0.35);
    }}
    h2 {{
      font-size: 1.25rem;
      margin: 0 0 14px;
    }}
    code {{
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--cyan);
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 0.84rem;
      word-break: break-all;
      display: inline-block;
    }}
    .field-label {{
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      margin: 12px 0 4px;
    }}
    .field-label:first-child {{ margin-top: 0; }}
    .hint {{
      margin: 12px 0 0;
      font-size: 0.85rem;
      color: var(--muted);
    }}
    .apps-list {{
      display: flex;
      flex-direction: column;
      gap: 18px;
    }}
    .app-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 22px;
    }}
    .app-head {{
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 12px;
    }}
    .app-icon {{
      width: 64px;
      height: 64px;
      border-radius: 14px;
      flex-shrink: 0;
    }}
    .app-title-row {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 4px;
    }}
    .app-title-row h3 {{
      margin: 0;
      font-size: 1.2rem;
    }}
    .badge {{
      font-size: 0.76rem;
      font-weight: 600;
      padding: 2px 9px;
      border-radius: 999px;
    }}
    .badge-version {{
      background: rgba(0, 180, 255, 0.14);
      color: var(--cyan);
      border: 1px solid rgba(0, 180, 255, 0.35);
    }}
    .badge-cat {{
      background: var(--surface);
      color: var(--muted);
      border: 1px solid var(--border);
    }}
    .app-id code {{
      color: var(--muted);
      font-size: 0.78rem;
      padding: 2px 6px;
    }}
    .app-short {{
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.94rem;
    }}
    .app-why {{
      margin: 0 0 12px;
      padding: 10px 14px;
      background: var(--surface);
      border-left: 3px solid var(--cyan);
      border-radius: 0 8px 8px 0;
      color: var(--text);
      font-size: 0.92rem;
    }}
    .app-bullets {{
      margin: 0 0 16px;
      padding-left: 20px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .app-bullets li {{
      margin-bottom: 6px;
    }}
    .app-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    footer {{
      margin-top: 40px;
      text-align: center;
      color: var(--muted);
      font-size: 0.85rem;
    }}
    footer a {{
      color: var(--cyan);
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <img class="hero-logo" src="repo-icon.png" alt="LycosLane Android Fedora Logo" />
      <div>
        <h1>LycosLane Apps - F-Droid Repository</h1>
        <p>Privacy-first, 100% open-source Android apps. Built without ads, accounts, or telemetry.</p>
        <div class="accent-bar">
          <span class="pill-cyan">MIT Licensed FOSS</span>
          <span class="pill-amber">Signed F-Droid Repo</span>
        </div>
      </div>
    </header>

    <section class="setup-grid">
      <div class="panel qr-panel">
        <div class="qr-box">
          <img src="repo-qr.png" alt="LycosLane F-Droid QR Code" />
        </div>
        <a class="btn btn-primary" href="{fdroid_intent_url}">Add to Neo Store / F-Droid</a>
      </div>

      <div class="panel">
        <h2>Manual Repository Setup</h2>
        <div class="field-label">Repository URL</div>
        <code>{repo_url}</code>
        <div class="field-label">SHA-256 Fingerprint</div>
        <code>{FINGERPRINT}</code>
        <div class="field-label">Full Verified URL</div>
        <code>{verified_url}</code>
        <p class="hint">In <strong>F-Droid</strong>, <strong>Droid-ify</strong>, or <strong>Neo Store</strong>: leave username and password empty, and keep mirror rotation disabled.</p>
      </div>
    </section>

    <section>
      <h2>Available Apps</h2>
      <div class="apps-list">
{apps_block}
      </div>
    </section>

    <footer>
      MIT License &copy; 2026 <a href="https://github.com/LycosLane">LycosLane</a> &middot;
      <a href="https://github.com/LycosLane/fdroid">Repository Source</a><br>
      <span style="font-size:0.78rem;opacity:0.8;">The Android robot is reproduced or modified from work created and shared by Google and used according to terms described in the Creative Commons 3.0 Attribution License.</span>
    </footer>
  </div>
</body>
</html>
"""
    with open(PUBLIC_DIR / "index.html", "w", encoding="utf-8", newline="\n") as f:
        f.write(html)


def main() -> None:
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    synced_apps: list[dict[str, object]] = []

    for repo_slug, app_id, display_name, category, why_copy in APPS:
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
        short_desc, bullets, icon_rel = read_app_store_copy(app_id)
        synced_apps.append({
            "display_name": display_name,
            "app_id": app_id,
            "category": category,
            "tag": tag,
            "repo_url": f"https://github.com/{repo_slug}",
            "apk_url": download_url,
            "short_desc": short_desc,
            "why_copy": why_copy,
            "bullets": bullets,
            "icon_rel": icon_rel,
        })

    if not synced_apps:
        raise RuntimeError("No APKs were synced from any configured GitHub repository.")

    write_landing_page(synced_apps)
    print(f"[DONE] Synced {len(synced_apps)} app(s) into {REPO_DIR}")


if __name__ == "__main__":
    main()
