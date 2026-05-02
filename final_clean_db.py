import pymysql
import os
import sys
import unicodedata
import re
from dotenv import load_dotenv

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', '.env'))

DB_CONFIG = {
    'host':        os.getenv('DB_HOST', 'localhost'),
    'port':        int(os.getenv('DB_PORT', 3306)),
    'user':        os.getenv('DB_USER', 'root'),
    'password':    os.getenv('DB_PASSWORD', ''),
    'db':          os.getenv('DB_NAME', 'tourisme_maroc'),
    'cursorclass': pymysql.cursors.DictCursor,
    'charset':     'utf8mb4'
}

def hard_fix_mojibake(text):
    if not text:
        return text
    
    # Common known bad strings we can just replace directly
    replacements = {
        "ÔÇÖ": "'",
        "├╣": "ù",
        "├¿": "è",
        "├ó": "â",
        "├»": "ï",
        "├®": "é",
        "├ê": "Ê",
        "├º": "ç",
        "├á": "à",
        "├": "à", 
        "┬": "",
        "Ã©": "é",
        "Ã¨": "è",
        "Ã": "à",
        "â€™": "'",
        "œ": "oe",
        "├«": "î",
        "├┤": "ô"
    }
    
    # First attempt systematic decode
    try:
        fixed = text.encode('cp850').decode('utf-8')
        if fixed != text:
            text = fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
        
    try:
        fixed = text.encode('cp1252').decode('utf-8')
        if fixed != text:
            text = fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
        
    # Hard replace any remaining known bad patterns
    for bad, good in replacements.items():
        text = text.replace(bad, good)
        
    return text

def normalize_image_path(name: str) -> str:
    if not name:
        return name
    
    # Fix mojibake first! So Ouka├»meden becomes Oukaïmeden
    name = hard_fix_mojibake(name)
    
    stem, ext = os.path.splitext(name)
    nfkd = unicodedata.normalize("NFKD", stem)
    ascii_stem = "".join(c for c in nfkd if not unicodedata.combining(c))
    
    # Force pure ascii for image paths: strictly lowercase, no spaces, no accents
    ascii_stem = re.sub(r'[^a-zA-Z0-9_\-\s]', '', ascii_stem)
    ascii_stem = ascii_stem.lower().replace(" ", "_").replace("-", "_")
    
    ext = ext.lower()
    return ascii_stem + ext

def run_cleaning():
    try:
        conn = pymysql.connect(**DB_CONFIG)
    except Exception as e:
        print(f"Cannot connect: {e}")
        return
        
    tables = [
        ('villes', ['nom_ville', 'slogan', 'description', 'type_ville'], 'nom_ville'),
        ('attractions', ['nom', 'description'], 'id'),
        ('activites', ['description'], 'id'),
        ('restaurants', ['nom', 'description', 'specialites'], 'id'),
        ('specialites_ville', ['nom_plat'], 'id'),
        ('artisanat', ['nom_artisanat', 'description'], 'id'),
        ('hebergements', ['nom'], 'id'),
        ('patrimoine_vestimentaire', ['nom', 'description'], 'id'),
        ('evenements', ['nom', 'periode', 'description'], 'id'),
        ('transports', ['type'], 'id')
    ]
    
    with conn.cursor() as cur:
        cur.execute("SET foreign_key_checks = 0;")
        
        for table, text_cols, pk in tables:
            try:
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
            except:
                continue
                
            has_image = False
            if rows and 'image_path' in rows[0]:
                has_image = True
                
            for row in rows:
                updates = []
                params = []
                
                for col in text_cols:
                    if col in row and row[col]:
                        old_val = row[col]
                        new_val = hard_fix_mojibake(old_val)
                        if old_val != new_val:
                            updates.append(f"{col} = %s")
                            params.append(new_val)
                            
                if has_image and row['image_path']:
                    old_img = row['image_path']
                    new_img = normalize_image_path(old_img)
                    if old_img != new_img:
                        updates.append("image_path = %s")
                        params.append(new_img)
                        
                if updates:
                    params.append(row[pk])
                    query = f"UPDATE {table} SET {', '.join(updates)} WHERE {pk} = %s"
                    cur.execute(query, tuple(params))
                    print(f"Cleaned {table} : {row[pk]}")
                    
        cur.execute("SET foreign_key_checks = 1;")
        conn.commit()
    print("Database is completely clean now.")

if __name__ == '__main__':
    run_cleaning()
