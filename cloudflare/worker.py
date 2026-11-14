"""
Cloudflare Python Worker Entrypoint for Sabro Networks.
Utilizes Cloudflare Workers Python runtime (Pyodide), WSGI bridge,
Cloudflare Hyperdrive connection pooling, and Cloudflare R2 bindings.
"""
import os
from workers import wsgi
from app import app

async def on_fetch(request, env):
    """
    Handles incoming HTTP requests at the Cloudflare edge.
    Injects Hyperdrive database connection strings and environment bindings.
    """
    # 1. Hyperdrive Connection Injection
    if hasattr(env, "HYPERDRIVE"):
        try:
            conn_str = getattr(env.HYPERDRIVE, "connection_string", None)
            if conn_str:
                os.environ["DATABASE_URL"] = str(conn_str)
                os.environ["DATABASE_BACKEND"] = "postgres"
        except Exception:
            pass
    elif hasattr(env, "DATABASE_URL") and str(env.DATABASE_URL):
        os.environ["DATABASE_URL"] = str(env.DATABASE_URL)
        os.environ["DATABASE_BACKEND"] = "postgres"

    # 2. R2 Storage Configuration Injection
    if hasattr(env, "CLOUDFLARE_R2_BUCKET_NAME") and str(env.CLOUDFLARE_R2_BUCKET_NAME):
        os.environ["CLOUDFLARE_R2_BUCKET_NAME"] = str(env.CLOUDFLARE_R2_BUCKET_NAME)
    if hasattr(env, "CLOUDFLARE_R2_PUBLIC_URL") and str(env.CLOUDFLARE_R2_PUBLIC_URL):
        os.environ["CLOUDFLARE_R2_PUBLIC_URL"] = str(env.CLOUDFLARE_R2_PUBLIC_URL)

    # 3. Dispatch to Flask WSGI Application
    return await wsgi.fetch(app, request, env)

# Export standard WSGI entrypoint for Cloudflare Workers
entrypoint = wsgi.entrypoint(app)
