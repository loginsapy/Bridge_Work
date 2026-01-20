import os
import psycopg2
url = os.environ.get('DATABASE_URL') or 'postgresql://evaluser:Killthenet22@evalserv.postgres.database.azure.com:5432/BridgeWork'
print('Using', url)
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("SELECT version_num FROM alembic_version")
rows = cur.fetchall()
print('alembic_version rows:', rows)
cur.close(); conn.close()
