"""
Re-upload every image in frontend/static/images/ to Cloudinary with a fixed
public_id so the resulting URLs are predictable and match the filenames stored
in the database.

Mapping:
  frontend/static/images/Agadir.png            -> villes/agadir
  frontend/static/images/attractions/Foo.jpg   -> attractions/foo
  frontend/static/images/artisanat/Bar.png     -> artisanat/bar
  frontend/static/images/vestimentaire/Baz.jpg -> vestimentaire/baz
"""

import os
import sys

from dotenv import load_dotenv

import cloudinary
import cloudinary.uploader

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', '.env'))

CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME', 'darytb39v')
API_KEY    = os.getenv('CLOUDINARY_API_KEY')
API_SECRET = os.getenv('CLOUDINARY_API_SECRET')

if not API_KEY or not API_SECRET:
    print("ERROR: CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET must be set in backend/.env")
    sys.exit(1)

cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=API_KEY,
    api_secret=API_SECRET,
    secure=True,
)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, 'frontend', 'static', 'images')

ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
SUBFOLDERS  = {'attractions', 'artisanat', 'vestimentaire'}


def iter_targets():
    """Yield (absolute_path, public_id) for every image to upload."""
    for entry in os.listdir(IMAGES_DIR):
        full = os.path.join(IMAGES_DIR, entry)
        if os.path.isfile(full):
            stem, ext = os.path.splitext(entry)
            if ext.lower() in ALLOWED_EXT:
                yield full, f"villes/{stem.lower()}"

    for sub in SUBFOLDERS:
        sub_dir = os.path.join(IMAGES_DIR, sub)
        if not os.path.isdir(sub_dir):
            continue
        for entry in os.listdir(sub_dir):
            full = os.path.join(sub_dir, entry)
            if os.path.isfile(full):
                stem, ext = os.path.splitext(entry)
                if ext.lower() in ALLOWED_EXT:
                    yield full, f"{sub}/{stem.lower()}"


def main():
    uploaded = 0
    failed   = 0
    failures = []

    targets = list(iter_targets())
    total   = len(targets)
    print(f"Found {total} images to upload to Cloudinary cloud '{CLOUD_NAME}'")

    for i, (path, public_id) in enumerate(targets, 1):
        try:
            cloudinary.uploader.upload(
                path,
                public_id=public_id,
                overwrite=True,
                use_filename=False,
                unique_filename=False,
            )
            uploaded += 1
            print(f"[{i}/{total}] OK  {public_id}")
        except Exception as e:
            failed += 1
            failures.append((public_id, str(e)))
            print(f"[{i}/{total}] FAIL {public_id} -> {e}")

    print("=" * 60)
    print(f"Uploaded: {uploaded}")
    print(f"Failed:   {failed}")
    if failures:
        print("Failures:")
        for pid, err in failures:
            print(f"  - {pid}: {err}")


if __name__ == '__main__':
    main()
