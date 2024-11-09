import sqlite3


def initialize_database():
    conn = sqlite3.connect('actions.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_actions (
                    user_id INTEGER PRIMARY KEY,
                    role_changes INTEGER DEFAULT 0,
                    channel_edits INTEGER DEFAULT 0,
                    channel_deletions INTEGER DEFAULT 0,
                    role_creations INTEGER DEFAULT 0,
                    channel_creations INTEGER DEFAULT 0,
                    bot_adds INTEGER DEFAULT 0,
                    webhook_creates INTEGER DEFAULT 0
                 )''')

    # Проверка наличия всех нужных столбцов
    existing_columns = [row[1] for row in c.execute("PRAGMA table_info(user_actions)").fetchall()]

    # Добавляем столбцы, если они отсутствуют
    if 'bot_adds' not in existing_columns:
        c.execute("ALTER TABLE user_actions ADD COLUMN bot_adds INTEGER DEFAULT 0")
    if 'webhook_creates' not in existing_columns:
        c.execute("ALTER TABLE user_actions ADD COLUMN webhook_creates INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


initialize_database()
