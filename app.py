from flask import Flask, request, jsonify, render_template, session
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'dematrix_red_gold_secret'
DB_FILE = 'dematrix.db'

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not username or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)", (username, email, password))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Registration successful! Please log in now.'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username or email already exists'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    identity = data.get('identity', '').strip()
    password = data.get('password', '').strip()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE (username = ? OR email = ?) AND password = ?", (identity, identity, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session['user'] = user['username']
        return jsonify({'message': 'Login successful', 'username': user['username']}), 200
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/posts', methods=['GET', 'POST'])
def handle_posts():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.get_json() or {}
        author = data.get('author') or session.get('user')
        content = data.get('content', '').strip()

        if not author or not content:
            conn.close()
            return jsonify({'error': 'Post content cannot be empty'}), 400

        cursor.execute("INSERT INTO posts (author, content) VALUES (?, ?)", (author, content))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Post created successfully'}), 201

    cursor.execute("SELECT author, content, timestamp FROM posts ORDER BY id DESC")
    posts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(posts)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
