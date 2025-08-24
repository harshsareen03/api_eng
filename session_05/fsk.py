from flask import Flask, request, redirect, make_response, g
import sqlite3
import base64
import json
from itsdangerous import URLSafeSerializer

app = Flask(__name__)
app.secret_key = "super-secret-key"   # for serializer

DB_FILE = "users.db"
serializer = URLSafeSerializer(app.secret_key)

# ---------------------- DB Helpers ----------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    if "db" in g:
        g.db.close()

def init_db():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )""")
    db.commit()

# ---------------------- Token Helpers ----------------------
def create_token(payload):
    return serializer.dumps(payload)

def verify_token(token):
    try:
        return serializer.loads(token)
    except Exception:
        return None

# ---------------------- HTML Views ----------------------
def home_page():
    return """
    <html><body>
      <h1>FaceLike (Flask)</h1>
      <form method="POST" action="/login">
        <input name="email" placeholder="Email">
        <input name="password" type="password" placeholder="Password">
        <button>Login</button>
      </form>
      <a href="/register">Register</a>
    </body></html>
    """

def register_page():
    return """
    <html><body>
      <h1>Register</h1>
      <form method="POST" action="/register">
        <input name="name" placeholder="Full name">
        <input name="email" placeholder="Email">
        <input name="password" type="password" placeholder="Password">
        <button>Sign Up</button>
      </form>
      <a href="/">Back</a>
    </body></html>
    """

def profile_page(user):
    return f"""
    <html><body>
      <h1>Hello, {user['name']}</h1>
      <p>Email: {user['email']}</p>
      <form method="POST" action="/logout"><button>Logout</button></form>
    </body></html>
    """

# ---------------------- Routes ----------------------
@app.route("/")
def home():
    return home_page()

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return register_page()
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]

    db = get_db()
    try:
        db.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, password))
        db.commit()
    except sqlite3.IntegrityError:
        return redirect("/register")

    token = create_token({"sub": email})
    resp = make_response(redirect("/profile"))
    resp.set_cookie("access_token", token, httponly=True)
    return resp

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]

    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
    user = cur.fetchone()
    if not user:
        return redirect("/")

    token = create_token({"sub": email})
    resp = make_response(redirect("/profile"))
    resp.set_cookie("access_token", token, httponly=True)
    return resp

@app.route("/profile")
def profile():
    token = request.cookies.get("access_token")
    payload = token and verify_token(token)
    if not payload:
        return redirect("/")

    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE email=?", (payload["sub"],))
    user = cur.fetchone()
    if not user:
        return redirect("/")

    return profile_page(user)

@app.route("/logout", methods=["POST"])
def logout():
    resp = make_response(redirect("/"))
    resp.delete_cookie("access_token")
    return resp

# ---------------------- Init + Run ----------------------
if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True, port=5000)
