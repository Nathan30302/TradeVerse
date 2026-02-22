# TradeVerse - Render Deployment Guide

## Quick Start - Deploy to Render in 3 Steps

### Prerequisites
- Render account (free at https://render.com)
- GitHub account with this repository
- GitHub OAuth token for private repos (if needed)

### Step 1: Create a Render Account & Connect GitHub
1. Go to https://render.com
2. Sign up for a free account
3. Click "New" → "Web Service"
4. Connect your GitHub account and authorize Render
5. Select the `Nathan30302/TradeVerse` repository

### Step 2: Create the Service
1. **Name**: `tradeverse`
2. **Environment**: Python 3
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `gunicorn -w 4 -b 0.0.0.0:$PORT app.wsgi:app`
5. **Plan**: Free
6. Click "Create Web Service"

### Step 3: Add PostgreSQL Database
1. Click "New" → "PostgreSQL"
2. **Name**: `tradeverse-db`
3. **Database Name**: `tradeverse`
4. **User**: `tradeverse_user`
5. **Plan**: Free
6. Click "Create Database"

### Step 4: Link Database to Web Service
1. Go to your `tradeverse` Web Service
2. Click "Environment"
3. Add manually (Render should auto-link):
   - **Key**: `DATABASE_URL`
   - **Value**: Copy from PostgreSQL instance details
4. Click "Save"

### Step 5: Configure Environment Variables
In your Web Service, go to "Environment" and add:

```
FLASK_ENV=production
SECRET_KEY=(Will be auto-generated, but you can set your own)
DATABASE_URL=(From PostgreSQL instance)
PYTHONUNBUFFERED=true
```

### Step 6: Deploy
1. Push any changes to GitHub (already done)
2. Render will auto-deploy when you push to main
3. Monitor deployment in "Logs" tab
4. Once deployed, you'll see a public URL like: `https://tradeverse-xxxx.onrender.com`

## Post-Deployment

### Initialize Database
1. Go to your Web Service dashboard
2. Click "Shell" tab
3. Run: `flask db upgrade`
4. Run: `flask init_db` (optional, if using custom init)

### Verify Deployment
1. Visit the public URL in your browser
2. Create a test account
3. Log in
4. Create a test trade
5. Verify data persists

## Troubleshooting

### Common Issues

#### "Application failed to start"
- Check logs for error messages
- Ensure `app.wsgi.app` is correct
- Verify DATABASE_URL is set

#### "Database connection failed"
- Verify DATABASE_URL environment variable is set
- Check PostgreSQL instance is running
- Ensure database name, user, and password match

#### "Port binding error"
- Ensure start command includes `-b 0.0.0.0:$PORT`
- Check no other services using that port

#### "Static files not loading"
- Static files are served correctly by Flask
- Check browser console for exact 404 paths
- Ensure routes are correct in Flask

### Check Logs
1. Go to Web Service dashboard
2. Click "Logs" tab
3. Select "Build Log" or "Deploy Log"
4. Look for error messages

## Application Details

- **Framework**: Flask 3.0 with Application Factory
- **Database**: PostgreSQL (free tier on Render)
- **ORM**: SQLAlchemy 2.0
- **Authentication**: Flask-Login with bcrypt
- **WSGI Server**: Gunicorn with 4 workers
- **Port**: Dynamic (set by Render via $PORT)

## Features
- User authentication and profiles
- Trading journal with trade tracking
- Trade plans and execution
- Performance metrics and analytics
- Dashboard with charts
- Support for multiple trading instruments
- Risk management features

## File Structure
```
TradeVerse/
├── app/
│   ├── __init__.py (Application Factory)
│   ├── wsgi.py (Gunicorn entry point)
│   ├── models/ (Database models)
│   ├── routes/ (API endpoints)
│   ├── templates/ (HTML templates)
│   ├── static/ (CSS, JS, images)
│   └── services/ (Business logic)
├── config.py (Configuration)
├── requirements.txt (Dependencies)
├── render.yaml (Render configuration)
└── migrations/ (Alembic database migrations)
```

## Database Migrations

The application uses Flask-Migrate (Alembic) for database versioning:

1. Migrations run automatically on deployment (pre-deploy command)
2. Create new migrations: `flask db migrate -m "description"`
3. Apply migrations: `flask db upgrade`
4. Rollback: `flask db downgrade`

## Monitoring

Render provides free monitoring:
- Check "Logs" tab for application output
- Monitor CPU and memory usage
- View error rates and response times

## Support

For issues:
1. Check Render documentation: https://render.com/docs
2. Check application logs on Render
3. Review GitHub issues: https://github.com/Nathan30302/TradeVerse/issues

---

**Created**: February 22, 2026
**Application Version**: 2.0.0
**Last Updated**: During deployment setup
