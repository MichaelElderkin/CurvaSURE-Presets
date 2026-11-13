#!/usr/bin/env python3
"""
make_preset_index.py — build the names-only index that the public Preset Index page reads.

Reads the full CurvaSURE preset manifest (which contains every point of every preset)
and writes preset_index.json with the SAME category / maker / preset structure but
with every preset reduced to {"index": true}. No points, parameters or notes leave
this script. Optionally commits the result to the presets repository on GitHub.

Usage
  python make_preset_index.py                       # read the live manifest URL, write ./preset_index.json
  python make_preset_index.py path/to/manifest.json # read a local manifest instead
  python make_preset_index.py --push                # also commit preset_index.json to the repo
                                                    # (needs a GitHub token in the env var GITHUB_TOKEN)

Settings are the constants just below. The token is never written anywhere; it is read
from the environment only when --push is given. Use a fine-grained personal access token
with "Contents: read and write" on the presets repository and nothing else.
"""
import json, os, sys, base64, urllib.request, urllib.error

MANIFEST_URL = "https://michaelelderkin.github.io/CurvaSURE-Presets/all_curvasure_presets_v5_0_0.json"
REPO = "michaelelderkin/CurvaSURE-Presets"   # owner/name
BRANCH = "main"
INDEX_PATH = "preset_index.json"              # path inside the repo (served by GitHub Pages at the same path)
OUTPUT_FILE = "preset_index.json"             # local copy written next to this script
META_KEYS = {"category_defaults", "category_options"}
EXCLUDE_CATEGORIES = {"Defaults"}             # templates are not listed on the public page


def is_preset(v):
    return isinstance(v, dict) and not isinstance(v, list) and any(k in v for k in ("points", "params", "version"))


def build_index(manifest):
    """Same nesting as the manifest; each preset becomes {"index": true}."""
    out = {}
    presets = 0
    for cat, contents in manifest.items():
        if cat in EXCLUDE_CATEGORIES or not isinstance(contents, dict):
            continue
        cat_out = {}
        for key, val in contents.items():
            if key in META_KEYS:
                continue
            if is_preset(val):
                cat_out[key] = {"index": True}
                presets += 1
            elif isinstance(val, dict):
                group = {pk: {"index": True} for pk, pv in val.items() if is_preset(pv)}
                if group:
                    cat_out[key] = group
                    presets += len(group)
        if cat_out:
            out[cat] = cat_out
    return out, presets


def load_manifest(source):
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(urllib.request.Request(source, headers={"Cache-Control": "no-cache"}), timeout=30) as r:
            return json.load(r)
    with open(source, encoding="utf-8") as f:
        return json.load(f)


def github_api(method, url, token, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "curvasure-preset-index",
        **({"Content-Type": "application/json"} if data else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace") or "{}")


def push_index(text):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("--push needs a GitHub token in the environment variable GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{REPO}/contents/{INDEX_PATH}"
    status, current = github_api("GET", f"{url}?ref={BRANCH}", token)
    sha = current.get("sha") if status == 200 else None
    if status == 200 and base64.b64decode(current.get("content", "")).decode("utf-8", "replace") == text:
        print("Repository index already up to date; nothing pushed.")
        return
    body = {"message": "Update preset index (names only)", "content": base64.b64encode(text.encode("utf-8")).decode("ascii"), "branch": BRANCH}
    if sha:
        body["sha"] = sha
    status, resp = github_api("PUT", url, token, body)
    if status in (200, 201):
        print(f"Pushed {INDEX_PATH} to {REPO}@{BRANCH} (commit {resp.get('commit', {}).get('sha', '?')[:7]}).")
    else:
        sys.exit(f"GitHub refused the push ({status}): {resp.get('message', resp)}")


def main(argv):
    push = "--push" in argv
    args = [a for a in argv if a != "--push"]
    source = args[0] if args else MANIFEST_URL
    manifest = load_manifest(source)
    index, n = build_index(manifest)
    text = json.dumps(index, indent=1, ensure_ascii=False) + "\n"
    # Belt and braces: the output must never contain measurement keys
    for forbidden in ("points", "tip_width", "butt_width", "Left Profile", "Right Profile", "notes", "params"):
        if forbidden in text:
            sys.exit(f"Refusing to write: output contains '{forbidden}'")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILE)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {out_path}: {len(index)} categories, {n} presets, {len(text):,} bytes (names only).")
    if push:
        push_index(text)


if __name__ == "__main__":
    main(sys.argv[1:])
