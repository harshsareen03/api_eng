"""
FastAPI app with registration + login (Facebook-like frontend using Bootstrap) and JWT auth.
Single-file app — no external template files. Uses sqlite3 for storage, python-jose for JWT,
and passlib for password hashing. Does NOT use pyjwt.

How to run:
1. pip install fastapi uvicorn python-jose[cryptography] passlib
2. python fastapi_facebook_like_auth.py
3. Open http://127.0.0.1:8000 in your browser

Notes:
- This serves Bootstrap via CDN and stores HTML templates inside the file.
- JWTs are returned in a cookie named "access_token" and also available via API responses.
- For demo only. Do NOT use default SECRET_KEY in production.
"""
from fastapi import FastAPI, Request, Form, HTTPException, status, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError
from passlib.context import CryptContext
import sqlite3
from datetime import datetime, timedelta
from jinja2 import Template
import secrets

# ---------- Configuration ----------
SECRET_KEY = "change_this_to_a_long_random_secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day
DB_PATH = "users.db"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()

# ---------- Simple SQLite helpers ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

init_db()

def create_user(name: str, email: str, password: str):
    password_hash = pwd_context.hash(password)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (email, name, password_hash, datetime.utcnow().isoformat()),
        )
        conn.commit()
        user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return None
    conn.close()
    return {"id": user_id, "email": email, "name": name}

def get_user_by_email(email: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, email, name, password_hash, created_at FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "name": row[2], "password_hash": row[3], "created_at": row[4]}

# ---------- JWT helpers ----------

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# ---------- HTML templates (Bootstrap CDN) ----------
BASE_CSS = """
<link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css\" rel=\"stylesheet\"> 
<style>
body{background:#f0f2f5}
.login-card{max-width:420px;margin:60px auto}
.fb-brand{font-family: 'Helvetica', Arial, sans-serif; color:#1877f2; font-weight:700}
.small-muted{color:#65676b}
.profile-card{max-width:720px;margin:40px auto}
</style>
"""

HOME_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\"> 
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> 
    <title>FaceLike - Home</title>
    {base_css}
  </head>
  <body>
    <div class=\"container\">
      <div class=\"row\">
        <div class=\"col-md-6\"> 
          <div class=\"mt-5\"> 
            <h1 class=\"fb-brand\">FaceLike</h1>
            <p class=\"lead\">Connect with friends and the world around you on FaceLike.</p>
            <ul>
              <li>Share updates</li>
              <li>See what friends are doing</li>
              <li>Private messages</li>
            </ul>
          </div>
        </div>
        <div class=\"col-md-6\"> 
          <div class=\"card login-card p-4 shadow-sm\">
            <h4 class=\"mb-3\">Log in</h4>
            <form method=\"post\" action=\"/login\">
              <div class=\"mb-2\">
                <input name=\"email\" class=\"form-control\" placeholder=\"Email address\" required>
              </div>
              <div class=\"mb-3\">
                <input name=\"password\" type=\"password\" class=\"form-control\" placeholder=\"Password\" required>
              </div>
              <button class=\"btn btn-primary w-100\" type=\"submit\">Log In</button>
            </form>
            <hr>
            <p class=\"small-muted\">New to FaceLike?</p>
            <a href=\"/register\" class=\"btn btn-success w-100\">Create new account</a>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
"""

REGISTER_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\"> 
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> 
    <title>FaceLike - Sign Up</title>
    {base_css}
  </head>
  <body>
    <div class=\"container\">
      <div class=\"card login-card p-4 shadow-sm mt-5\">
        <h3>Create an account</h3>
        <p class=\"small-muted\">It\'s quick and easy.</p>
        <form method=\"post\" action=\"/register\">
          <div class=\"mb-2\">
            <input name=\"name\" class=\"form-control\" placeholder=\"Full name\" required>
          </div>
          <div class=\"mb-2\">
            <input name=\"email\" type=\"email\" class=\"form-control\" placeholder=\"Email address\" required>
          </div>
          <div class=\"mb-2\">
            <input name=\"password\" type=\"password\" class=\"form-control\" placeholder=\"New password\" required>
          </div>
          <button class=\"btn btn-success w-100\" type=\"submit\">Sign Up</button>
        </form>
        <hr>
        <a href=\"/\" class=\"btn btn-link\">Back to login</a>
      </div>
    </div>
  </body>
</html>
"""


PROFILE_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\"> 
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> 
    <title>FaceLike - Profile</title>
    {base_css}
  </head>
  <body>
    <div class=\"container\">
      <div class=\"card profile-card p-4 shadow-sm mt-4\">
        <div class=\"d-flex justify-content-between\">
          <h3>Hello, {{ name }}</h3>
          <form method=\"post\" action=\"/logout\"><button class=\"btn btn-outline-secondary\">Log out</button></form>
        </div>
        <p class=\"small-muted\">Email: {{ email }}</p>
        <hr>
        <h5>What's on your mind?</h5>
        <div class=\"mb-3\">
          <textarea class=\"form-control\" rows=\"3\">Share something...</textarea>
        </div>
        <button class=\"btn btn-primary\">Post</button>
      </div>
    </div>
  </body>
</html>
"""

# ---------- Utility: render template strings with Jinja2 Template ----------
def render_html(template_str: str, **context):
    t = Template(template_str)
    return t.render(**context)

# ---------- Routes (GET pages) ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render_html(HOME_HTML, base_css=BASE_CSS)

@app.get("/register", response_class=HTMLResponse)
def register_get():
    return render_html(REGISTER_HTML, base_css=BASE_CSS)

@app.get("/profile", response_class=HTMLResponse)
def profile_get(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/", status_code=302)
    payload = verify_access_token(token)
    if not payload:
        return RedirectResponse(url="/", status_code=302)
    user = get_user_by_email(payload.get("sub"))
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_html(PROFILE_HTML, base_css=BASE_CSS, name=user["name"], email=user["email"])

# ---------- Routes (form posts) ----------
@app.post("/register")
def register_post(name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    user = create_user(name=name.strip(), email=email.strip().lower(), password=password)
    if not user:
        # user exists
        resp = RedirectResponse(url="/register", status_code=303)
        return resp
    # create token and set cookie
    access_token = create_access_token({"sub": user["email"]}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    resp = RedirectResponse(url="/profile", status_code=303)
    resp.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
    return resp

@app.post("/login")
def login_post(response: Response, email: str = Form(...), password: str = Form(...)):
    user = get_user_by_email(email.strip().lower())
    if not user:
        return RedirectResponse(url="/", status_code=303)
    if not pwd_context.verify(password, user["password_hash"]):
        return RedirectResponse(url="/", status_code=303)
    access_token = create_access_token({"sub": user["email"]}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    resp = RedirectResponse(url="/profile", status_code=303)
    resp.set_cookie(key="access_token", value=access_token, httponly=True, samesite="lax")
    return resp

@app.post("/logout")
def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("access_token")
    return resp

# ---------- JSON API endpoints (for SPA or mobile clients) ----------
@app.post("/api/register")
def api_register(payload: dict):
    name = payload.get("name")
    email = payload.get("email")
    password = payload.get("password")
    if not (name and email and password):
        raise HTTPException(status_code=400, detail="Missing fields")
    user = create_user(name=name.strip(), email=email.strip().lower(), password=password)
    if not user:
        raise HTTPException(status_code=400, detail="User already exists")
    token = create_access_token({"sub": user["email"]}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": token, "token_type": "bearer"}

@app.post("/api/login")
def api_login(payload: dict):
    email = payload.get("email")
    password = payload.get("password")
    if not (email and password):
        raise HTTPException(status_code=400, detail="Missing fields")
    user = get_user_by_email(email.strip().lower())
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if not pwd_context.verify(password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_access_token({"sub": user["email"]}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": token, "token_type": "bearer"}

# ---------- Run with: uvicorn fastapi_facebook_like_auth:app --reload ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fastapi_facebook_like_auth:app", host="127.0.0.1", port=8000, reload=True)
