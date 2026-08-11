"""
Создание БД на sqlite.
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'secret_santa.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

with sqlite3.connect(DB_PATH) as connection:
    cursor = connection.cursor()
    cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    gift_receiver_chat_id INTEGER,
    gift_receiver_full_name TEXT
);
''')
