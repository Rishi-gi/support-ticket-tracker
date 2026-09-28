"""
Database connection and shared constants.

Every other script imports get_collection() from here, so the connection
logic lives in one place. Credentials come from the .env file, never from
the code itself.
"""
import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ServerSelectionTimeoutError

load_dotenv()

# Allowed values. MongoDB won't enforce these for us (no fixed schema),
# so the application validates them before writing.
CATEGORIES = ["Network", "Billing", "Hardware", "Software", "Account"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
STATUSES = ["Open", "In Progress", "Resolved", "Closed"]


def get_db():
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("DB_NAME", "support_tracker")
    if not uri:
        sys.exit("MONGODB_URI is not set. Copy .env.example to .env and add your Atlas connection string.")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")  # fail fast if Atlas is unreachable
    except (ServerSelectionTimeoutError, ConfigurationError) as e:
        sys.exit(f"Could not connect to MongoDB. Check your URI and Atlas Network Access list.\n{e}")
    return client[db_name]


def get_collection():
    return get_db()["tickets"]


def ensure_base_indexes(tickets):
    """Indexes the app always needs (separate from the performance demo)."""
    # ticket_ref is the human-facing ID, so it must be unique.
    tickets.create_index("ticket_ref", unique=True, name="ticket_ref_unique")
