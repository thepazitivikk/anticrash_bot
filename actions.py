import sqlite3

def create_db():
    conn = sqlite3.connect('actions.db')
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS user_actions (
            user_id INTEGER PRIMARY KEY,
            role_changes INTEGER DEFAULT 0,
            channel_edits INTEGER DEFAULT 0,
            channel_deletions INTEGER DEFAULT 0,
            role_creations INTEGER DEFAULT 0,
            channel_creations INTEGER DEFAULT 0
        )
    ''')

    try:
        c.execute("ALTER TABLE user_actions ADD COLUMN role_creations INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE user_actions ADD COLUMN channel_creations INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

create_db()
print("Database and table 'user_actions' updated successfully.")
