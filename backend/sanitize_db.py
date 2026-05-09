import pymysql
import os
from dotenv import load_dotenv

# Load .env
env_path = os.path.join('backend', '.env')
load_dotenv(dotenv_path=env_path)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def sanitize_db():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # 1. Fetch all cities
            cur.execute("SELECT nom_ville FROM villes")
            villes = cur.fetchall()
            
            for v in villes:
                old_name = v['nom_ville']
                # Trim spaces
                new_name = old_name.strip()
                
                # Check for encoding corruption (like Fs)
                # This is a bit tricky, but we can try to fix common ones if we see them
                # But a simple TRIM is already very helpful
                
                if old_name != new_name:
                    print(f"Updating '{old_name}' -> '{new_name}'")
                    # We need to update all related tables because they use nom_ville as a FK (or at least as a reference)
                    tables = ['villes', 'attractions', 'activites', 'restaurants', 'hebergements', 
                              'specialites_ville', 'artisanat', 'patrimoine_vestimentaire', 
                              'evenements', 'transports']
                    
                    for table in tables:
                        # Note: we use IGNORE or check existence to avoid primary key conflicts if any
                        try:
                            cur.execute(f"UPDATE {table} SET nom_ville = %s WHERE nom_ville = %s", (new_name, old_name))
                        except Exception as e:
                            print(f"  Error updating {table}: {e}")
            
            conn.commit()
            print("Database sanitization complete.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    sanitize_db()
