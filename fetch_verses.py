#!/usr/bin/env python3
"""
Build verses-nasb.txt (NASB 1995) for the Daily Verse app from the references in refs.txt,
using the YouVersion Platform API (free App Key: https://platform.youversion.com).

  YVP_APP_KEY=xxx python3 fetch_verses.py --list          # find the NASB1995 Bible id
  YVP_APP_KEY=xxx python3 fetch_verses.py --bible <id>    # write verses-nasb.txt

Standard library only. The key never reaches the website; only verses-nasb.txt is served.
"""
import argparse, html, json, os, re, shutil, sys, time, urllib.error, urllib.parse, urllib.request

API = "https://api.youversion.com/v1"
MAX_VERSES = 500  # Lockman: no more than 500 NASB verses stored electronically

USFM = {
    "Genesis":"GEN","Exodus":"EXO","Leviticus":"LEV","Numbers":"NUM","Deuteronomy":"DEU","Joshua":"JOS",
    "Judges":"JDG","Ruth":"RUT","1 Samuel":"1SA","2 Samuel":"2SA","1 Kings":"1KI","2 Kings":"2KI",
    "1 Chronicles":"1CH","2 Chronicles":"2CH","Ezra":"EZR","Nehemiah":"NEH","Esther":"EST","Job":"JOB",
    "Psalm":"PSA","Psalms":"PSA","Proverbs":"PRO","Ecclesiastes":"ECC","Song of Solomon":"SNG","Isaiah":"ISA",
    "Jeremiah":"JER","Lamentations":"LAM","Ezekiel":"EZK","Daniel":"DAN","Hosea":"HOS","Joel":"JOL",
    "Amos":"AMO","Obadiah":"OBA","Jonah":"JON","Micah":"MIC","Nahum":"NAM","Habakkuk":"HAB",
    "Zephaniah":"ZEP","Haggai":"HAG","Zechariah":"ZEC","Malachi":"MAL","Matthew":"MAT","Mark":"MRK",
    "Luke":"LUK","John":"JHN","Acts":"ACT","Romans":"ROM","1 Corinthians":"1CO","2 Corinthians":"2CO",
    "Galatians":"GAL","Ephesians":"EPH","Philippians":"PHP","Colossians":"COL","1 Thessalonians":"1TH",
    "2 Thessalonians":"2TH","1 Timothy":"1TI","2 Timothy":"2TI","Titus":"TIT","Philemon":"PHM",
    "Hebrews":"HEB","James":"JAS","1 Peter":"1PE","2 Peter":"2PE","1 John":"1JN","2 John":"2JN",
    "3 John":"3JN","Jude":"JUD","Revelation":"REV",
}

def get(path, key, params=None):
    url = f"{API}{path}" + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"X-YVP-App-Key": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {e.code} for {path}: {body}") from None

def list_bibles(key):
    """Try a few documented parameter shapes; return (params_used, bibles)."""
    attempts = [
        {"language_ranges[]": "en", "all_available": "true"},
        {"language_ranges[]": "eng", "all_available": "true"},
        {"language_ranges[]": "en"},
    ]
    last = None
    for params in attempts:
        try:
            bibles, page = [], dict(params)
            for _ in range(50):                      # follow pagination if present
                data = get("/bibles", key, page)
                bibles += data.get("data", [])
                token = data.get("next_page_token")
                if not token: break
                page = dict(params, page_token=token)
            return params, bibles
        except RuntimeError as e:
            last = e; print(f"  tried {params}: {e}")
    raise SystemExit(f"Couldn't list Bibles. Last error: {last}")

def to_usfm(ref):
    m = re.match(r"^(.*) (\d+):(\d+)(?:-(\d+))?$", ref)
    if not m or m[1] not in USFM:
        raise ValueError(f"can't parse {ref!r}")
    b, c, a, z = USFM[m[1]], m[2], m[3], m[4]
    return f"{b}.{c}.{a}" + (f"-{b}.{c}.{z}" if z else "")

def verse_count(ref):
    m = re.search(r":(\d+)(?:-(\d+))?$", ref)
    return int(m[2]) - int(m[1]) + 1 if m and m[2] else 1

def clean(content):
    t = re.sub(r"<[^>]+>", " ", content)          # in case the API returns HTML
    t = html.unescape(t)
    t = re.sub(r"(^|\s)\d{1,3}(?=\s)", " ", t)     # verse numbers
    return re.sub(r"\s+", " ", t).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list English Bibles your key can use")
    ap.add_argument("--bible", help="YouVersion Bible id for NASB1995")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--refs", default=os.path.join(here, "refs.txt"))
    args = ap.parse_args()
    key = os.environ.get("YVP_APP_KEY") or sys.exit("Set YVP_APP_KEY")

    if args.list:
        params, bibles = list_bibles(key)
        print(f"Listed with {params}: {len(bibles)} Bibles")
        for b in bibles:
            print(b.get("id"), "|", b.get("abbreviation") or "", "|", b.get("localized_title") or b.get("title"))
        return
    if not args.bible:
        sys.exit("Pass --bible <id> (find it with --list)")
    dest = os.path.join(here, "verses-nasb.txt")

    refs = [l.strip() for l in open(args.refs, encoding="utf-8").read().splitlines()
            if l.strip() and not l.startswith("#")]

    out, total, failed = [], 0, []
    for ref in refs:
        total += verse_count(ref)
        if total > MAX_VERSES:
            print(f"Stopping at {ref}: would pass {MAX_VERSES} verses"); break
        try:
            p = get(f"/bibles/{args.bible}/passages/{to_usfm(ref)}", key, {"format": "text"})
            text = clean(p.get("content") or p.get("data", {}).get("content", ""))
            if not text: raise ValueError("empty")
            out.append(f"{ref} | {text}")
            print("ok  ", ref)
        except Exception as e:
            failed.append(ref); print("FAIL", ref, e)
        time.sleep(0.2)  # be polite to the rate limit

    if not out:
        sys.exit("Nothing fetched; leaving verses-nasb.txt unchanged.")
    if os.path.exists(dest):
        shutil.copy(dest, dest + ".bak")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("# NASB 1995 verse list, generated by fetch_verses.py\n\n" + "\n".join(out) + "\n")
    print(f"\nWrote {len(out)} passages to {dest}" + (f", {len(failed)} failed" if failed else ""))

if __name__ == "__main__":
    main()