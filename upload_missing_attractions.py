"""
For every attractions / patrimoine_vestimentaire row whose image_path is NULL,
search Wikimedia Commons for a candidate image, upload it to Cloudinary, and
write the new image_path to the DB.

Dry-run by default — prints proposed slug, Cloudinary public_id, and the
Wikimedia file that would be uploaded. Pass --apply to actually upload + write.

    python upload_missing_attractions.py            # dry-run
    python upload_missing_attractions.py --apply    # upload + DB write
"""

import argparse
import os
import sys
import unicodedata
import urllib.parse
from pathlib import Path

import cloudinary
import cloudinary.exceptions
import cloudinary.uploader
import pymysql
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(Path(__file__).parent / "backend" / ".env")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

UA = "MoroccoSecretsBot/1.0 (mekam979@gmail.com)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

ACCENT_MAP = {
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "â": "a", "à": "a", "ä": "a",
    "ô": "o", "ö": "o",
    "û": "u", "ù": "u", "ü": "u",
    "î": "i", "ï": "i",
    "ç": "c",
}


def slugify(name: str) -> str:
    s = name.strip().lower()
    for k, v in ACCENT_MAP.items():
        s = s.replace(k, v)
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    s = s.replace(" ", "_")
    s = "".join(c for c in s if c.isalnum() or c == "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def search_commons(query: str, limit: int = 5) -> list[str]:
    """Top File: hits matching <query>. Returns filenames without 'File:' prefix."""
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srnamespace": 6,
        "srlimit": limit,
        "srsearch": query,
    }
    r = requests.get(
        COMMONS_API, params=params, headers={"User-Agent": UA}, timeout=20
    )
    r.raise_for_status()
    titles = []
    for hit in r.json().get("query", {}).get("search", []):
        title = hit["title"]
        if title.startswith("File:"):
            title = title[len("File:"):]
        if os.path.splitext(title)[1].lower() in IMAGE_EXTS:
            titles.append(title)
    return titles


def file_path_url(filename: str, width: int = 1280) -> str:
    encoded = urllib.parse.quote(filename)
    return (
        f"https://commons.wikimedia.org/wiki/Special:FilePath/"
        f"{encoded}?width={width}"
    )


def process_table(conn, table: str, folder: str, dry_run: bool) -> dict:
    summary = {"candidates": [], "uploaded": [], "no_candidate": [], "errors": []}
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id, nom_ville, nom FROM {table} WHERE image_path IS NULL"
        )
        rows = cur.fetchall()

    print(f"\n[{table}] {len(rows)} NULL rows to process")

    for row in rows:
        slug = slugify(row["nom"])
        query = f"{row['nom']} {row['nom_ville']}"
        nom_short = row["nom"][:36] + ("…" if len(row["nom"]) > 36 else "")
        try:
            results = search_commons(query)
        except Exception as e:
            print(f"  ERR     {row['nom_ville']:18s} {nom_short:40s}  search failed: {e}")
            summary["errors"].append({**row, "slug": slug, "error": str(e)})
            continue

        if not results:
            print(f"  no-cand {row['nom_ville']:18s} {nom_short:40s}  query={query!r}")
            summary["no_candidate"].append({**row, "slug": slug, "query": query})
            continue

        top = results[0]
        wm_url = file_path_url(top)
        candidate = {
            **row,
            "slug": slug,
            "query": query,
            "wm_filename": top,
            "wm_url": wm_url,
            "public_id": f"{folder}/{slug}",
            "image_path": f"{slug}.jpg",
        }
        summary["candidates"].append(candidate)

        print(f"  cand    {row['nom_ville']:18s} {nom_short:40s}")
        print(f"          slug      = {slug}")
        print(f"          public_id = {folder}/{slug}")
        print(f"          wikimedia = {top}")

        if dry_run:
            continue

        try:
            result = cloudinary.uploader.upload(
                wm_url,
                public_id=candidate["public_id"],
                overwrite=True,
                resource_type="image",
            )
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {table} SET image_path = %s WHERE id = %s",
                    (candidate["image_path"], row["id"]),
                )
            conn.commit()
            summary["uploaded"].append(
                {**candidate, "cloudinary_url": result["secure_url"]}
            )
            print(f"          UPLOADED  -> {result['secure_url']}")
        except cloudinary.exceptions.Error as e:
            print(f"          UPLOAD ERROR: {e}")
            summary["errors"].append({**candidate, "error": str(e)})
        except Exception as e:
            print(f"          DB ERROR: {e}")
            summary["errors"].append({**candidate, "error": str(e)})

    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="upload to Cloudinary and write to DB (default: dry-run)",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        db=os.getenv("DB_NAME", "tourisme_maroc"),
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )

    print(f"=== upload_missing_attractions.py — {'DRY-RUN' if dry_run else 'APPLY'} ===")
    try:
        attr = process_table(conn, "attractions", "attractions", dry_run)
        vest = process_table(
            conn, "patrimoine_vestimentaire", "vestimentaire", dry_run
        )
    finally:
        conn.close()

    print("\n=== SUMMARY ===")
    for label, s in (("attractions", attr), ("patrimoine_vestimentaire", vest)):
        print(
            f"  {label:25s} candidates={len(s['candidates']):3d}  "
            f"uploaded={len(s['uploaded']):3d}  "
            f"no_candidate={len(s['no_candidate']):3d}  "
            f"errors={len(s['errors']):3d}"
        )

    if dry_run:
        print(
            "\n[dry-run] No Cloudinary uploads or DB writes. "
            "Review candidates and re-run with --apply."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
