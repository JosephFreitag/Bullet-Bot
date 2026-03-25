import sqlite3
import bcrypt
import os

class DatabaseService:
    # 1. Add db_path as a keyword argument
    def __init__(self, db_name="data.db", db_path=None):
        # 2. Prioritize db_path (from main.py) over the default db_name
        self.db_name = db_path if db_path else db_name
        
        # 3. Ensure the connection uses the correct filename
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );
        """)
        # Add user_id to conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id)
            );
        """)
        self.conn.commit()

    def create_user(self, username, password):
        """Creates a new user with a hashed password."""
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        cursor = self.conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                           (username, password_hash))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None # Username already exists

    def get_user(self, username):
        """Retrieves a user by username."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user:
            return {"id": user[0], "username": user[1], "password_hash": user[2]}
        return None

    def get_user_by_id(self, user_id):
        """Retrieves a user by id (for restoring a saved session)."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "username": row[1]}
        return None

    def verify_user(self, username, password):
        """Verifies a user's password."""
        user = self.get_user(username)
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
            return user
        return None

    def create_conversation(self, user_id, title):
        """Creates a new conversation for a user."""
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO conversations (user_id, title) VALUES (?, ?)", (user_id, title))
        self.conn.commit()
        return cursor.lastrowid

    def get_conversations(self, user_id):
        """Retrieves all conversations for a given user."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, title FROM conversations WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        return cursor.fetchall()

    def add_message(self, conversation_id, role, content):
        """Adds a message to a specific conversation."""
        if conversation_id is None:
            return
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content)
        )
        self.conn.commit()

    def get_messages(self, conversation_id):
        """Retrieves all messages for a given conversation."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,)
        )
        return [{"role": role, "content": content} for role, content in cursor.fetchall()]

    def close(self):
        self.conn.close()

    def delete_conversation(self, conversation_id):
        """Deletes a conversation and all its associated messages."""
        cursor = self.conn.cursor()
        try:
            # If you have foreign keys with ON DELETE CASCADE, 
            # deleting the conversation will auto-delete the messages.
            cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Delete Error: {e}")
            return False
