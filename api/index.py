import sys
import os

# Ensure the root directory of the repository is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app
from werkzeug.middleware.proxy_fix import ProxyFix

# Disable strict slashes globally to prevent redirect loops on edge proxies
app.url_map.strict_slashes = False

class VercelPathCorrectionMiddleware:
    """
    Ensures WSGI PATH_INFO accurately reflects the client's requested URL
    behind Vercel serverless edge rewrites and removes internal entrypoint prefixes.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path_info = environ.get("PATH_INFO", "")
        forwarded_uri = (
            environ.get("HTTP_X_FORWARDED_URI")
            or environ.get("HTTP_X_REAL_PATH")
            or environ.get("HTTP_X_VERCEL_PATH")
            or environ.get("HTTP_X_MATCHED_PATH")
        )
        if forwarded_uri:
            clean_path = forwarded_uri.split("?")[0]
            environ["PATH_INFO"] = clean_path
        elif path_info.startswith("/api/index.py"):
            environ["PATH_INFO"] = path_info[len("/api/index.py"):] or "/"
        elif path_info.startswith("/api/index"):
            environ["PATH_INFO"] = path_info[len("/api/index"):] or "/"
        elif path_info.startswith("/api"):
            environ["PATH_INFO"] = path_info[len("/api"):] or "/"

        return self.wsgi_app(environ, start_response)

# Apply proxy fix and path correction middleware
app.wsgi_app = VercelPathCorrectionMiddleware(ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1))

if __name__ == "__main__":
    app.run()
