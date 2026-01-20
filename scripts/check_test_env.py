"""Quick check to ensure tests won't run against a remote DB.

Exit code 0 -> safe
Exit code 1 -> unsafe
"""
import os
from app.utils.safety import is_safe_db_uri

uri = os.environ.get('DATABASE_URL') or os.environ.get('SQLALCHEMY_DATABASE_URI') or ''
if not uri:
    print('No DATABASE_URL/SQLALCHEMY_DATABASE_URI set; assuming safe (sqlite in-memory by default when using TestConfig).')
    raise SystemExit(0)

if is_safe_db_uri(uri):
    print('DB URI appears safe:', uri)
    raise SystemExit(0)

print('Unsafe DB URI detected:', uri)
print('If you REALLY intend to run tests against this remote DB set TESTING env var and ensure you know the consequences.')
raise SystemExit(1)