import os
from app import create_app

# Respect FLASK_ENV so production hosts (Heroku-style Procfile, etc.) load ProductionConfig.
config_name = os.getenv("FLASK_ENV") or "default"
app = create_app(config_name)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
