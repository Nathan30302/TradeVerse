#!/usr/bin/env python3
"""
Render Deployment Configuration Validator

Validates that the TradeVerse application is properly configured for Render deployment.
Run this to verify all production requirements are met before manual Render setup.
"""

import os
import sys
import json

def check_file_exists(path, description):
    """Check if a required file exists"""
    if os.path.exists(path):
        print(f"✓ {description}: {path}")
        return True
    else:
        print(f"✗ MISSING: {description}: {path}")
        return False

def check_content_in_file(path, content, description):
    """Check if required content exists in a file"""
    if not os.path.exists(path):
        print(f"✗ FILE NOT FOUND: {path}")
        return False
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            file_content = f.read()
            if content in file_content:
                print(f"✓ {description}: Found in {path}")
                return True
            else:
                print(f"✗ MISSING: {description}: Not found in {path}")
                return False
    except Exception as e:
        print(f"✗ ERROR reading {path}: {e}")
        return False

def validate_production_setup():
    """Validate all production requirements for Render"""
    
    print("=" * 70)
    print("TradeVerse - Render Deployment Configuration Validator")
    print("=" * 70)
    print()
    
    checks = []
    
    # 1. Check WSGI entry point
    print("1. Checking WSGI Configuration...")
    checks.append(check_file_exists("app/wsgi.py", "WSGI entry point"))
    checks.append(check_content_in_file(
        "app/wsgi.py", 
        "from app import create_app", 
        "WSGI imports create_app"
    ))
    checks.append(check_content_in_file(
        "app/wsgi.py",
        "app = create_app(config_name)",
        "WSGI creates app instance"
    ))
    print()
    
    # 2. Check production config
    print("2. Checking Production Configuration...")
    checks.append(check_file_exists("config.py", "Configuration module"))
    checks.append(check_content_in_file(
        "config.py",
        "class ProductionConfig",
        "ProductionConfig class exists"
    ))
    checks.append(check_content_in_file(
        "config.py",
        "SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL'",
        "Uses DATABASE_URL env var for production"
    ))
    checks.append(check_content_in_file(
        "config.py",
        "SESSION_COOKIE_SECURE = True",
        "HTTPS cookies enabled in production"
    ))
    print()
    
    # 3. Check requirements
    print("3. Checking Requirements...")
    checks.append(check_file_exists("requirements.txt", "Requirements file"))
    checks.append(check_content_in_file(
        "requirements.txt",
        "gunicorn>=21.0.0",
        "Gunicorn included"
    ))
    checks.append(check_content_in_file(
        "requirements.txt",
        "psycopg2-binary",
        "PostgreSQL driver included"
    ))
    checks.append(check_content_in_file(
        "requirements.txt",
        "Flask==3.0.0",
        "Flask included"
    ))
    print()
    
    # 4. Check Render configuration
    print("4. Checking Render Configuration...")
    checks.append(check_file_exists("render.yaml", "Render configuration"))
    checks.append(check_content_in_file(
        "render.yaml",
        "startCommand: gunicorn",
        "Gunicorn start command configured"
    ))
    checks.append(check_content_in_file(
        "render.yaml",
        "fromDatabase",
        "Database configuration in render.yaml"
    ))
    print()
    
    # 5. Check Procfile
    print("5. Checking Procfile...")
    checks.append(check_file_exists("Procfile", "Procfile exists"))
    checks.append(check_content_in_file(
        "Procfile",
        "gunicorn",
        "Procfile contains gunicorn command"
    ))
    print()
    
    # 6. Check runtime
    print("6. Checking Python Runtime...")
    checks.append(check_file_exists("runtime.txt", "Python runtime file"))
    checks.append(check_content_in_file(
        "runtime.txt",
        "python",
        "Python version specified"
    ))
    print()
    
    # 7. Check migrations
    print("7. Checking Database Migrations...")
    checks.append(check_file_exists("migrations/alembic.ini", "Alembic config"))
    print()
    
    # 8. Check models
    print("8. Checking Database Models...")
    checks.append(check_file_exists("app/models/__init__.py", "Models package"))
    checks.append(check_file_exists("app/models/user.py", "User model"))
    checks.append(check_file_exists("app/models/trade.py", "Trade model"))
    print()
    
    # Summary
    print("=" * 70)
    passed = sum(checks)
    total = len(checks)
    print(f"VALIDATION RESULTS: {passed}/{total} checks passed")
    print("=" * 70)
    print()
    
    if passed == total:
        print("✓ All production requirements are met!")
        print()
        print("NEXT STEPS - Manual Render Deployment:")
        print()
        print("1. Go to https://render.com and sign up (free)")
        print("2. Connect your GitHub account")
        print("3. Click 'New' → 'Web Service'")
        print("4. Select 'Nathan30302/TradeVerse' repository")
        print("5. Configure:")
        print("   - Name: tradeverse")
        print("   - Environment: Python 3")
        print("   - Build: pip install -r requirements.txt")
        print("   - Start: gunicorn -w 4 -b 0.0.0.0:$PORT app.wsgi:app")
        print("   - Plan: Free")
        print("6. Click 'Create Web Service'")
        print("7. Wait for build to complete (~2-3 minutes)")
        print()
        print("8. After web service is created:")
        print("   - Click 'New' → 'PostgreSQL'")
        print("   - Name: tradeverse-db")
        print("   - Database: tradeverse")
        print("   - Plan: Free")
        print("   - Create and wait for database to initialize")
        print()
        print("9. Go back to web service, click 'Environment'")
        print("   - Add DATABASE_URL from PostgreSQL instance")
        print("   - AUTO_GENERATE or SET SECRET_KEY")
        print()
        print("10. Render will auto-redeploy, check logs")
        print("11. Once deployed, visit: https://tradeverse-xxxx.onrender.com")
        print()
        return 0
    else:
        print("✗ Some requirements are missing!")
        print("Please fix the issues listed above before deployment.")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(validate_production_setup())
