"""Pre-deployment checks for TradeVerse

Run: python scripts/predeploy_check.py

Checks performed:
- SECRET_KEY present and not default placeholders
- FLASK_ENV not set to development for production deploy
- Procfile exists and references gunicorn
- requirements.txt contains gunicorn and a Postgres driver
- run.py does not force debug=True
- No tracked .pyc or __pycache__ remain
- tradeverse.db is not tracked

This script is non-destructive and only reports issues.
"""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
print('Running pre-deploy checks in', ROOT)
issues = []

# SECRET_KEY
secret = os.environ.get('SECRET_KEY')
if not secret:
    issues.append('Missing SECRET_KEY environment variable. Set SECRET_KEY in the environment or secrets manager.')
else:
    if secret in ('dev-secret-key-please-change-in-production','prod-key-change-me-immediately'):
        issues.append('SECRET_KEY is set but uses a known placeholder value. Use a secure random secret.')

# FLASK_ENV check
flask_env = os.environ.get('FLASK_ENV')
if flask_env == 'development':
    issues.append('FLASK_ENV is set to development. Ensure FLASK_ENV=production for production deploys.')

# Procfile
procfile = os.path.join(ROOT, 'Procfile')
if not os.path.exists(procfile):
    issues.append('Missing Procfile — add a Procfile that runs Gunicorn (e.g. "web: python -m gunicorn app.wsgi:app").')
else:
    with open(procfile, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'gunicorn' not in content.lower():
        issues.append('Procfile present but does not reference gunicorn.')

# requirements.txt checks
req = os.path.join(ROOT, 'requirements.txt')
if not os.path.exists(req):
    issues.append('Missing requirements.txt')
else:
    with open(req, 'r', encoding='utf-8') as f:
        reqtxt = f.read().lower()
    if 'gunicorn' not in reqtxt:
        issues.append('requirements.txt does not list gunicorn')
    if 'psycopg2' not in reqtxt and 'psycopg2-binary' not in reqtxt:
        issues.append('requirements.txt does not list a Postgres driver (psycopg2 or psycopg2-binary) — add one if using Postgres in production')

# run.py debug check
runpy = os.path.join(ROOT, 'run.py')
if os.path.exists(runpy):
    with open(runpy, 'r', encoding='utf-8') as f:
        r = f.read()
    if 'debug=True' in r and 'debug=app.config.get' not in r:
        issues.append('run.py contains debug=True; this could enable the debugger if executed directly. Prefer using Gunicorn in production.')

# git tracked pyc / __pycache__
try:
    p = subprocess.run(['git','ls-files','*.pyc'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT)
    pyc = [l for l in p.stdout.splitlines() if l.strip()]
    p2 = subprocess.run(['git','ls-files'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT)
    pycache = [l for l in p2.stdout.splitlines() if '__pycache__' in l]
    if pyc or pycache:
        issues.append(f'Found tracked compiled files: {len(pyc)} .pyc and {len(pycache)} __pycache__ entries. They should be removed from the repo and added to .gitignore.')
except Exception:
    issues.append('Could not check tracked .pyc / __pycache__ (git not available).')

# tradeverse.db tracked?
try:
    p = subprocess.run(['git','ls-files','tradeverse.db'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT)
    if p.stdout.strip():
        issues.append('tradeverse.db is still tracked by git. Remove it from tracking before deploying.')
except Exception:
    issues.append('Could not check tradeverse.db tracking (git not available).')

# Summary
print('\nPre-deploy check summary:')
if not issues:
    print('  OK — no issues found.')
    sys.exit(0)
else:
    print('  Found issues:')
    for it in issues:
        print('   -', it)
    sys.exit(2)
