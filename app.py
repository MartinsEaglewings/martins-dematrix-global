from flask import Flask, request, jsonify, render_template, session
import sqlite3
import psycopg2
import psycopg2.extras
import os
import time

app = Flask(__name__)
app.secret_key = 'dematrix_red_gold_secret'

# Use PostgreSQL if DATABASE_URL is provided by Render, else fallback to SQLite locally
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    if DATABASE_URL:
        # Render PostgreSQL connection
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    else:
        # Local SQLite fallback
        conn = sqlite3.connect('dematrix.db')
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        # PostgreSQL syntax
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(150) UNIQUE NOT NULL,
                password TEXT NOT NULL,
                last_seen DOUBLE PRECISION DEFAULT 0
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                author VARCHAR(100) NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS private_messages (
                id SERIAL PRIMARY KEY,
                sender VARCHAR(100) NOT NULL,
                recipient VARCHAR(100) NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read INTEGER DEFAULT 0
            );
        ''')
    else:
        # SQLite syntax
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                last_seen REAL DEFAULT 0
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS private_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read INTEGER DEFAULT 0
            );
        ''')

    conn.commit()
    cursor.close()
    conn.close()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()

    if not username or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        if DATABASE_URL:
            cursor.execute("INSERT INTO users (username, email, password, last_seen) VALUES (%s, %s, %s, %s)", 
                           (username, email, password, time.time()))
        else:
            cursor.execute("INSERT INTO users (username, email, password, last_seen) VALUES (?, ?, ?, ?)", 
                           (username, email, password, time.time()))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message': 'Registration successful! Please log in now.'}), 201
    except Exception:
        return jsonify({'error': 'Username or email already exists'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    identity = data.get('identity', '').strip()
    password = data.get('password', '').strip()

    if not identity or not password:
        return jsonify({'error': 'Please enter both username/email and password'}), 400

    conn = get_db()
    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)", (identity, identity))
    else:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)", (identity, identity))
    
    user = cursor.fetchone()

    if not user:
        cursor.close()
        conn.close()
        return jsonify({'error': 'No account found with this username or email'}), 404

    # Verify password match
    if user['password'] != password:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Incorrect password'}), 401

    # Login successful - Update last_seen
    if DATABASE_URL:
        cursor.execute("UPDATE users SET last_seen = %s WHERE id = %s", (time.time(), user['id']))
    else:
        cursor.execute("UPDATE users SET last_seen = ? WHERE id = ?", (time.time(), user['id']))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    session['user'] = user['username']
    return jsonify({'message': 'Login successful', 'username': user['username']}), 200

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    data = request.get_json() or {}
    username = data.get('username')
    if username:
        conn = get_db()
        cursor = conn.cursor()
        if DATABASE_URL:
            cursor.execute("UPDATE users SET last_seen = %s WHERE username = %s", (time.time(), username))
        else:
            cursor.execute("UPDATE users SET last_seen = ? WHERE username = ?", (time.time(), username))
        conn.commit()
        cursor.close()
        conn.close()
    return jsonify({'status': 'ok'})

@app.route('/api/online-users', methods=['GET'])
def get_online_users():
    conn = get_db()
    cutoff = time.time() - 15
    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT username FROM users WHERE last_seen > %s ORDER BY username ASC", (cutoff,))
    else:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE last_seen > ? ORDER BY username ASC", (cutoff,))
    
    users = [row['username'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(users)

@app.route('/api/posts', methods=['GET', 'POST'])
def handle_posts():
    conn = get_db()

    if request.method == 'POST':
        data = request.get_json() or {}
        author = data.get('author') or session.get('user')
        content = data.get('content', '').strip()

        if not author or not content:
            conn.close()
            return jsonify({'error': 'Post content cannot be empty'}), 400

        cursor = conn.cursor()
        if DATABASE_URL:
            cursor.execute("INSERT INTO posts (author, content) VALUES (%s, %s)", (author, content))
        else:
            cursor.execute("INSERT INTO posts (author, content) VALUES (?, ?)", (author, content))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message': 'Post created successfully'}), 201

    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT author, content, TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') as timestamp FROM posts ORDER BY id DESC")
    else:
        cursor = conn.cursor()
        cursor.execute("SELECT author, content, timestamp FROM posts ORDER BY id DESC")
    
    posts = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(posts)

@app.route('/api/private-messages', methods=['GET', 'POST'])
def handle_private_messages():
    conn = get_db()

    if request.method == 'POST':
        data = request.get_json() or {}
        sender = data.get('sender')
        recipient = data.get('recipient')
        content = data.get('content', '').strip()

        if not sender or not recipient or not content:
            conn.close()
            return jsonify({'error': 'Recipient and content are required'}), 400

        cursor = conn.cursor()
        if DATABASE_URL:
            cursor.execute("INSERT INTO private_messages (sender, recipient, content) VALUES (%s, %s, %s)", 
                           (sender, recipient, content))
        else:
            cursor.execute("INSERT INTO private_messages (sender, recipient, content) VALUES (?, ?, ?)", 
                           (sender, recipient, content))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message': 'Private message sent'}), 201

    user1 = request.args.get('user1')
    user2 = request.args.get('user2')

    if not user1 or not user2:
        conn.close()
        return jsonify({'error': 'Both user parameters are required'}), 400

    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("UPDATE private_messages SET is_read = 1 WHERE recipient = %s AND sender = %s", (user1, user2))
    else:
        cursor.execute("UPDATE private_messages SET is_read = 1 WHERE recipient = ? AND sender = ?", (user1, user2))
    conn.commit()

    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            SELECT sender, recipient, content, TO_CHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') as timestamp 
            FROM private_messages 
            WHERE (sender = %s AND recipient = %s) OR (sender = %s AND recipient = %s)
            ORDER BY id ASC
        ''', (user1, user2, user2, user1))
    else:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sender, recipient, content, timestamp 
            FROM private_messages 
            WHERE (sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?)
            ORDER BY id ASC
        ''', (user1, user2, user2, user1))

    messages = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(messages)

@app.route('/api/unread-counts', methods=['GET'])
def get_unread_counts():
    username = request.args.get('username')
    if not username:
        return jsonify({})

    conn = get_db()
    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('''
            SELECT sender, COUNT(*) as count 
            FROM private_messages 
            WHERE recipient = %s AND is_read = 0 
            GROUP BY sender
        ''', (username,))
    else:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sender, COUNT(*) as count 
            FROM private_messages 
            WHERE recipient = ? AND is_read = 0 
            GROUP BY sender
        ''', (username,))
    
    counts = {row['sender']: row['count'] for row in cursor.fetchall()}
    cursor.close()
    conn.close()
    return jsonify(counts)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
