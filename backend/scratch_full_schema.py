import os
from dotenv import load_dotenv
import pymysql
import json

env_path = os.path.join(os.getcwd(), 'backend', '.env')
load_dotenv(env_path)

try:
    conn = pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME'),
        port=int(os.getenv('DB_PORT', 3306)),
        ssl={'verify_cert': False},
        cursorclass=pymysql.cursors.DictCursor
    )
    with conn.cursor() as cur:
        cur.execute('SHOW TABLES')
        tables = cur.fetchall()
        schema = {}
        for table_dict in tables:
            table_name = list(table_dict.values())[0]
            cur.execute(f'DESCRIBE {table_name}')
            schema[table_name] = cur.fetchall()
        print(json.dumps(schema, indent=2, default=str))
    conn.close()
except Exception as e:
    print(f"Error: {e}")
