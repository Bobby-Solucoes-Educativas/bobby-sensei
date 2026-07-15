import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection() -> psycopg.Connection:
    return psycopg.connect(_DATABASE_URL)
