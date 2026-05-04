"""
Backfill image_path in attractions and patrimoine_vestimentaire by deriving
a slug from `nom` and matching it against Cloudinary public_ids.

Defaults to dry-run. Pass --apply to commit UPDATEs.

    python backfill_images.py            # dry-run, no DB writes
    python backfill_images.py --apply    # write proposed UPDATEs
"""

import argparse
import os
import sys
import unicodedata
from pathlib import Path

import cloudinary
import cloudinary.api
import cloudinary.exceptions
import pymysql
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


ACCENT_MAP = {
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "â": "a", "à": "a", "ä": "a",
    "ô": "o", "ö": "o",
    "û": "u", "ù": "u", "ü": "u",
    "î": "i", "ï": "i",
    "ç": "c",
}

ARTICLES = (" de ", " d'", " l'", " el ", " al ")


def _pre_slug(name: str) -> str:
    """Normalize for comparison; keeps spaces so article patterns can match."""
    s = name.strip().lower()
    for k, v in ACCENT_MAP.items():
        s = s.replace(k, v)
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    s = s.replace("’", "'")
    for ch in ("‐", "(", ")", "[", "]"):
        s = s.replace(ch, "")
    return s


def _to_slug(s: str) -> str:
    s = s.replace("'", "")
    s = s.replace(" ", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def canonicalize(s: str) -> str:
    """Same canonical form applied to slugs and to Cloudinary public_ids."""
    return _to_slug(_pre_slug(s))


def slug_variants(name: str) -> list[str]:
    """Two candidates: full slug, then article-stripped slug (deduped)."""
    pre = _pre_slug(name)
    full = _to_slug(pre)

    padded = " " + pre + " "
    for art in ARTICLES:
        while art in padded:
            padded = padded.replace(art, " ")
    short = _to_slug(padded.strip())

    out = [full]
    if short and short != full:
        out.append(short)
    return [s for s in out if s]


def fetch_folder_resources(folder: str) -> dict[str, str]:
    """Map canonicalize(relative public_id) → format. Cloudinary URL serving
    is accent-insensitive, so canonicalizing keys lets no-accent slugs match
    accented public_ids (e.g. slug 'cafe_hafa' matches public_id 'café_hafa')."""
    out: dict[str, str] = {}
    next_cursor = None
    prefix = f"{folder}/"
    while True:
        kwargs = dict(
            type="upload", prefix=prefix, max_results=500, resource_type="image"
        )
        if next_cursor:
            kwargs["next_cursor"] = next_cursor
        res = cloudinary.api.resources(**kwargs)
        for r in res.get("resources", []):
            pid = r["public_id"]
            if pid.startswith(prefix):
                relative = pid[len(prefix):]
                out[canonicalize(relative)] = r.get("format", "jpg")
        next_cursor = res.get("next_cursor")
        if not next_cursor:
            break
    return out


def find_match(resources: dict[str, str], name: str) -> tuple[str | None, str | None]:
    """Returns (matched_slug, filename) on hit, (None, None) on miss."""
    for slug in slug_variants(name):
        if slug in resources:
            return slug, f"{slug}.{resources[slug]}"
        for ext in ("jpg", "png", "webp"):
            key = f"{slug}.{ext}"
            if key in resources:
                return slug, key
    return None, None


def detect_pk(cur, table: str) -> str:
    cur.execute(f"SHOW KEYS FROM {table} WHERE Key_name = 'PRIMARY'")
    rows = cur.fetchall()
    if not rows:
        raise RuntimeError(f"{table} has no primary key")
    if len(rows) > 1:
        raise RuntimeError(f"{table} has composite primary key (not handled)")
    return rows[0]["Column_name"]


def process_table(conn, table: str, folder: str, dry_run: bool, sql_file=None) -> dict:
    summary: dict = {"updated": [], "not_found": []}
    with conn.cursor() as cur:
        pk = detect_pk(cur, table)
        cur.execute(
            f"SELECT {pk} AS pk, nom_ville, nom FROM {table} "
            f"WHERE image_path IS NULL OR image_path = ''"
        )
        rows = cur.fetchall()

    print(f"\n[{table}] {len(rows)} NULL/empty rows (pk={pk}); listing Cloudinary {folder}/...")
    resources = fetch_folder_resources(folder)
    print(f"  fetched {len(resources)} public_ids in {folder}/")

    for row in rows:
        matched_slug, filename = find_match(resources, row["nom"])
        nom_short = (row["nom"][:38] + "…") if len(row["nom"]) > 38 else row["nom"]
        if matched_slug:
            summary["updated"].append(
                {"pk": row["pk"], "nom_ville": row["nom_ville"],
                 "nom": row["nom"], "filename": filename, "slug": matched_slug}
            )
            print(f"  MATCH   {row['nom_ville']:18s} {nom_short:40s} -> {filename}")
        else:
            tried = slug_variants(row["nom"])
            summary["not_found"].append(
                {"pk": row["pk"], "nom_ville": row["nom_ville"],
                 "nom": row["nom"], "slugs_tried": tried}
            )
            print(f"  no-hit  {row['nom_ville']:18s} {nom_short:40s}    tried={tried}")

    if not dry_run and summary["updated"]:
        with conn.cursor() as cur:
            for item in summary["updated"]:
                cur.execute(
                    f"UPDATE {table} SET image_path = %s WHERE {pk} = %s",
                    (item["filename"], item["pk"]),
                )
                if sql_file:
                    fn_escaped = item["filename"].replace("'", "''")
                    sql_file.write(
                        f"UPDATE {table} SET image_path = '{fn_escaped}' "
                        f"WHERE {pk} = {item['pk']};\n"
                    )
        conn.commit()
        if sql_file:
            sql_file.write(f"-- {len(summary['updated'])} rows updated in {table}\n\n")
        print(f"  -> committed {len(summary['updated'])} rows to {table}")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="commit UPDATEs (default: dry-run)")
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

    print(f"=== backfill_images.py — {'DRY-RUN' if dry_run else 'APPLY'} ===")
    sql_file = None
    if not dry_run:
        sql_path = Path(__file__).parent / "backfill_aiven.sql"
        sql_file = open(sql_path, "w", encoding="utf-8")
        sql_file.write(
            "-- Generated by backfill_images.py — replays the local-DB UPDATEs\n"
            "-- against another instance (e.g. Aiven). Run inside the target schema.\n\n"
        )
        print(f"writing SQL to {sql_path}")
    try:
        attr = process_table(conn, "attractions", "attractions", dry_run, sql_file)
        vest = process_table(conn, "patrimoine_vestimentaire", "vestimentaire", dry_run, sql_file)
    finally:
        conn.close()
        if sql_file:
            sql_file.close()

    print("\n=== SUMMARY ===")
    for label, s in (("attractions", attr), ("patrimoine_vestimentaire", vest)):
        print(f"  {label:25s} matched={len(s['updated']):3d}  not_found={len(s['not_found']):3d}")

    if dry_run:
        print("\n[dry-run] No DB writes performed. Re-run with --apply to commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
