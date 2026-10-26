import os

VK_TOKEN = os.environ.get("VK_TOKEN", "")
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
