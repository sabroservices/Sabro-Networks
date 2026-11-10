import sys
import os

# Ensure the root directory of the repository is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app

# Vercel Serverless Function entrypoint
if __name__ == "__main__":
    app.run()
