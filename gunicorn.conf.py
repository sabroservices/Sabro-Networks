import os

# Dynamic port binding for Render, Heroku, Railway, and Cloud platforms
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Concurrency & Performance settings
workers = 2
threads = 4
timeout = 120

# Stream logs directly to standard out / standard error for Cloud log viewers
accesslog = "-"
errorlog = "-"
loglevel = "info"
