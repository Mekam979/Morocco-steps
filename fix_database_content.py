import pymysql
import os
import sys
import unicodedata

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def normalize_filename(name: str) -> str:
    if not name:
        return name
    stem, ext = os.path.splitext(name)
    nfkd = unicodedata.normalize("NFKD", stem)
    ascii_stem = "".join(c for c in nfkd if not unicodedata.combining(c))
    ascii_stem = ascii_stem.lower().replace(" ", "_").replace("-", "_")
    return ascii_stem + ext.lower()

def fix_mojibake(text):
    if not text:
        return text
    try:
        # Check if it looks like CP850 mojibake of UTF-8
        # Try encoding to cp850 and decoding as utf-8
        # If it succeeds AND changes the text, it was mojibaked
        fixed = text.encode('cp850').decode('utf-8')
        if fixed != text:
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    
    try:
        fixed = text.encode('cp1252').decode('utf-8')
        if fixed != text:
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    return text

from dotenv import load_dotenv
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

def generate_and_apply_fixes():
    try:
        conn = pymysql.connect(**DB_CONFIG)
    except Exception as e:
        print(f"Cannot connect to DB: {e}")
        return

    sql_statements = []
    
    with conn.cursor() as cur:
        # Disable foreign key checks to allow updating primary keys
        cur.execute("SET foreign_key_checks = 0;")
        
        # 1. Fix Villes
        cur.execute("SELECT nom_ville, slogan, description, type_ville, image_path FROM villes")
        villes = cur.fetchall()
        for v in villes:
            updates = []
            params = []
            
            # fix encoding
            for col in ['nom_ville', 'slogan', 'description', 'type_ville']:
                old_val = v[col]
                new_val = fix_mojibake(old_val)
                if old_val != new_val:
                    updates.append(f"{col} = %s")
                    params.append(new_val)
            
            # fix image_path
            old_img = v['image_path']
            if old_img:
                new_img = normalize_filename(old_img)
                if old_img != new_img:
                    updates.append("image_path = %s")
                    params.append(new_img)
                    
            if updates:
                params.append(v['nom_ville'])
                query = f"UPDATE villes SET {', '.join(updates)} WHERE nom_ville = %s"
                
                # Make safe SQL string for the script output
                safe_updates = []
                for u, p in zip(updates, params[:-1]):
                    safe_p = pymysql.converters.escape_string(p)
                    safe_updates.append(f"{u.replace('%s', repr(safe_p))}")
                sql_statements.append(f"UPDATE villes SET {', '.join(safe_updates)} WHERE nom_ville = '{pymysql.converters.escape_string(v['nom_ville'])}';")
                
                # Execute in DB
                cur.execute(query, tuple(params))
                print(f"Updated ville: {v['nom_ville']}")
                
        # We should also do this for attractions, artisanat, hebergements, restaurants, etc.
        tables = [
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
        
        for table, text_cols, pk in tables:
            # check if table exists
            try:
                cur.execute(f"SELECT * FROM {table}")
                rows = cur.fetchall()
            except:
                continue
                
            # check if image_path exists in this table
            has_image = False
            if rows and 'image_path' in rows[0]:
                has_image = True
                
            for row in rows:
                updates = []
                params = []
                
                # fix encoding
                for col in text_cols:
                    if col in row:
                        old_val = row[col]
                        new_val = fix_mojibake(old_val)
                        if old_val != new_val:
                            updates.append(f"{col} = %s")
                            params.append(new_val)
                
                # fix image_path
                if has_image:
                    old_img = row['image_path']
                    if old_img:
                        new_img = normalize_filename(old_img)
                        if old_img != new_img:
                            updates.append("image_path = %s")
                            params.append(new_img)
                            
                if updates:
                    params.append(row[pk])
                    query = f"UPDATE {table} SET {', '.join(updates)} WHERE {pk} = %s"
                    
                    safe_updates = []
                    for u, p in zip(updates, params[:-1]):
                        if p is None:
                            safe_updates.append(f"{u.replace('%s', 'NULL')}")
                        else:
                            safe_p = pymysql.converters.escape_string(str(p))
                            safe_updates.append(f"{u.replace('%s', repr(safe_p))}")
                    sql_statements.append(f"UPDATE {table} SET {', '.join(safe_updates)} WHERE {pk} = {row[pk]};")
                    
                    cur.execute(query, tuple(params))
                    print(f"Updated {table} id {row[pk]}")

        cur.execute("SET foreign_key_checks = 1;")
        conn.commit()

    with open('fix_database_export.sql', 'w', encoding='utf-8') as f:
        f.write("-- SQL script to fix encoding and image paths\n")
        f.write("SET NAMES utf8mb4;\n")
        f.write("\n".join(sql_statements))
        
    print("Database updated and fix_database_export.sql created successfully.")

if __name__ == "__main__":
    generate_and_apply_fixes()
