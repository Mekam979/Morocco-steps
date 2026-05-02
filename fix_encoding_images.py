# -*- coding: utf-8 -*-
"""
fix_encoding_images.py
======================
Tasks:
  1. Rename image files → lowercase, accent-free, spaces → underscores
  2. Update every reference in HTML templates (src, CSS url(), JS arrays)
  3. Verify <meta charset="UTF-8"> exists in every HTML head

Run from the project root:
  python fix_encoding_images.py
"""

import os
import re
import unicodedata
import sys
import shutil

# Force UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT   = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR     = os.path.join(PROJECT_ROOT, "frontend", "static", "images")
TEMPLATES_DIR  = os.path.join(PROJECT_ROOT, "frontend", "templates")

# ─── Helper: strip accents + lowercase + spaces→underscores ──────────────────
def normalize_filename(name: str) -> str:
    """Agadir.png → agadir.png | Oukaïmeden.jpg → oukaimeden.jpg | El Jadida.jpeg → el_jadida.jpeg"""
    stem, ext = os.path.splitext(name)
    # Decompose unicode characters and drop combining marks
    nfkd = unicodedata.normalize("NFKD", stem)
    ascii_stem = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase and replace spaces/hyphens with underscores
    ascii_stem = ascii_stem.lower().replace(" ", "_").replace("-", "_")
    return ascii_stem + ext.lower()


# ─── 1. Collect rename mapping for the images/ root folder ───────────────────
def collect_renames():
    renames = {}   # old_name → new_name  (only when they differ)
    try:
        entries = os.listdir(IMAGES_DIR)
    except FileNotFoundError:
        print(f"[ERROR] Images dir not found: {IMAGES_DIR}")
        return renames

    for name in entries:
        full = os.path.join(IMAGES_DIR, name)
        if not os.path.isfile(full):
            continue  # skip sub-directories
        new_name = normalize_filename(name)
        if new_name != name:
            renames[name] = new_name
    return renames


# ─── 2. Apply file renames ────────────────────────────────────────────────────
def apply_renames(renames: dict):
    """Actually rename files on disk (uses a tmp step to handle same-volume case changes)."""
    for old, new in renames.items():
        src  = os.path.join(IMAGES_DIR, old)
        dst  = os.path.join(IMAGES_DIR, new)
        if os.path.exists(src):
            if src.lower() == dst.lower() and src != dst:
                # Same path modulo case (Windows) → need tmp step
                tmp = dst + "_tmp_rename_"
                os.rename(src, tmp)
                os.rename(tmp, dst)
            else:
                os.rename(src, dst)
            print(f"  [RENAME] {old:<40s} -> {new}")
        else:
            print(f"  [SKIP]   {old!r} not found (already renamed?)")


# ─── 3. Build a regex-based text replacement map ─────────────────────────────
def build_text_replacements(renames: dict) -> list:
    """
    Returns a list of (pattern, replacement) tuples to apply to HTML/CSS/JS text.
    We replace the OLD filename with the NEW filename wherever it appears as a
    literal string (in src=, url(), JS strings, etc.).
    Pattern is case-insensitive for safety.
    """
    replacements = []
    for old, new in sorted(renames.items(), key=lambda x: -len(x[0])):  # longest first
        # Escape special regex chars in old name
        escaped = re.escape(old)
        # Match the exact filename (no directory component) in any context
        pattern = re.compile(r'(?<![/\\])' + escaped, re.IGNORECASE)
        replacements.append((pattern, new))
    return replacements


# ─── 4. Fix HTML files ───────────────────────────────────────────────────────
CHARSET_TAG = '<meta charset="UTF-8">'

def fix_html_file(path: str, replacements: list):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        original = f.read()

    modified = original

    # a) Ensure <meta charset="UTF-8"> inside <head>
    if CHARSET_TAG.lower() not in modified.lower():
        modified = re.sub(
            r'(<head[^>]*>)',
            r'\1\n    ' + CHARSET_TAG,
            modified,
            count=1,
            flags=re.IGNORECASE
        )
        print(f"  [CHARSET] Added <meta charset> to {os.path.basename(path)}")

    # b) Replace old image names with new ones
    for pattern, new_name in replacements:
        modified = pattern.sub(new_name, modified)

    if modified != original:
        # Write UTF-8 BOM-free
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(modified)
        print(f"  [UPDATED] {os.path.basename(path)}")
    else:
        print(f"  [OK]      {os.path.basename(path)} (no changes needed)")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Morocco-steps — Encoding & Image Path Fixer")
    print("=" * 60)

    # Step 1 – collect renames
    print("\n[1/3] Scanning images directory …")
    renames = collect_renames()
    if renames:
        print(f"  Found {len(renames)} file(s) to rename:")
        for old, new in renames.items():
            print(f"    {old:<40s} -> {new}")
    else:
        print("  No files need renaming.")

    # Step 2 – rename on disk
    print("\n[2/3] Renaming files …")
    if renames:
        apply_renames(renames)
    else:
        print("  Nothing to rename.")

    # Step 3 – fix HTML
    print("\n[3/3] Updating HTML templates …")
    replacements = build_text_replacements(renames)
    html_files = [
        os.path.join(TEMPLATES_DIR, f)
        for f in os.listdir(TEMPLATES_DIR)
        if f.endswith(".html")
    ]
    for path in sorted(html_files):
        fix_html_file(path, replacements)

    print("\n" + "=" * 60)
    print("Done! All images renamed and HTML references updated.")
    print("=" * 60)
    print("\nIMPORTANT — next steps:")
    print("  1. Run: git add frontend/static/images frontend/templates")
    print("  2. Run: git commit -m 'fix: normalize image filenames to lowercase ASCII'")
    print("  3. Run: git push origin main")
    print("     (GitHub & jsDelivr are case-sensitive — new lowercase names will work)")
    print("\n  If your DB stores image_path values (e.g. 'Fes.jpeg'),")
    print("  run the SQL snippet below to normalise them:")
    print()
    # Print SQL for common DB fixes
    sql_fixes = [
        ("Agadir.png",         "agadir.png"),
        ("Al_Hoceima.png",     "al_hoceima.png"),
        ("Asilah.jpg",         "asilah.jpg"),
        ("Aventure.jpg",       "aventure.jpg"),
        ("Aventure_bg.jpg",    "aventure_bg.jpg"),
        ("Azrou.png",          "azrou.png"),
        ("Berkane.jpg",        "berkane.jpg"),
        ("Casablanca.webp",    "casablanca.webp"),
        ("Chefchaouen.jpg",    "chefchaouen.jpg"),
        ("El Jadida.jpeg",     "el_jadida.jpeg"),
        ("Essaouira.jpg",      "essaouira.jpg"),
        ("Fes.jpeg",           "fes.jpeg"),
        ("Haut_Atlas.jpg",     "haut_atlas.jpg"),
        ("Imlil.png",          "imlil.png"),
        ("Kenitra.webp",       "kenitra.webp"),
        ("Laayoune.jpeg",      "laayoune.jpeg"),
        ("Laayoune.png",       "laayoune.png"),
        ("Marrakech.jpg",      "marrakech.jpg"),
        ("Meknes.jpg",         "meknes.jpg"),
        ("Merzouga.png",       "merzouga.png"),
        ("Moyen Atlas.png",    "moyen_atlas.png"),
        ("Oualidia.jpg",       "oualidia.jpg"),
        ("Ouarzazate.webp",    "ouarzazate.webp"),
        ("Oukaïmeden.jpg",     "oukaimeden.jpg"),
        ("Rabat.png",          "rabat.png"),
        ("SAFI.jpg",           "safi.jpg"),
        ("Saidia.avif",        "saidia.avif"),
        ("Tanger.png",         "tanger.png"),
        ("Taourirt.jpg",       "taourirt.jpg"),
        ("Taza.jpg",           "taza.jpg"),
        ("Tetouan.jpg",        "tetouan.jpg"),
        ("Zagora.jpg",         "zagora.jpg"),
    ]
    print("  -- MySQL: update image_path in villes table")
    for old_p, new_p in sql_fixes:
        print(f"  UPDATE villes SET image_path = '{new_p}' WHERE image_path = '{old_p}';")


if __name__ == "__main__":
    main()
