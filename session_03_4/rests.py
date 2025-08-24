# main.py
import asyncio
import base64
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Generator, AsyncGenerator

from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from jose import jwt, JWTError
from passlib.context import CryptContext
import redis.asyncio as aioredis

# --------------------------
# CONFIG
# --------------------------
DB_PATH = "app.db"
JWT_SECRET = "SUPER_SECRET_CHANGE_ME"  # change for prod
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24  # 1 day
REDIS_URL = "redis://localhost:6379/0"
ORDER_CHANNEL = "orders"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Ecom REST demo")

redis_client: Optional[aioredis.Redis] = None

# --------------------------
# DB helpers
# --------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        price_cents INTEGER NOT NULL,
        currency TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tax_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country_code TEXT UNIQUE NOT NULL,
        percentage REAL NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        currency TEXT NOT NULL,
        subtotal_cents INTEGER NOT NULL,
        tax_cents INTEGER NOT NULL,
        total_cents INTEGER NOT NULL,
        country_code TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price_cents INTEGER NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    )""")
    conn.commit()
    conn.close()

# --------------------------
# Auth utils
# --------------------------
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire.isoformat()})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None

# --------------------------
# Cursor helpers
# --------------------------
def encode_cursor(item_id: int) -> str:
    return base64.urlsafe_b64encode(str(item_id).encode()).decode()

def decode_cursor(cursor: str) -> Optional[int]:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return None

# --------------------------
# DB operations (sync, used via asyncio.to_thread)
# --------------------------
def db_create_user(email: str, password: str, full_name: Optional[str] = None) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    pw_hash = hash_password(password)
    try:
        cur.execute(
            "INSERT INTO users (email, password_hash, full_name, created_at) VALUES (?, ?, ?, ?)",
            (email, pw_hash, full_name, now),
        )
        conn.commit()
        user_id = cur.lastrowid
        row = conn.execute("SELECT id, email, full_name, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()

def db_get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def db_get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT id, email, full_name, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def db_create_product(name: str, description: str, price_cents: int, currency: str) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO products (name, description, price_cents, currency, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, description, price_cents, currency.upper(), now),
    )
    conn.commit()
    pid = cur.lastrowid
    row = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()
    return dict(row)

def db_get_product(product_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def db_list_products(after_id: Optional[int], limit: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        if after_id:
            rows = conn.execute(
                "SELECT * FROM products WHERE id < ? ORDER BY id DESC LIMIT ?", (after_id, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM products ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def db_create_tax_rule(country_code: str, percentage: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO tax_rules (country_code, percentage) VALUES (?, ?)",
        (country_code.upper(), float(percentage)),
    )
    conn.commit()
    conn.close()

def db_get_tax_for_country(country_code: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM tax_rules WHERE country_code = ?", (country_code.upper(),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def db_create_order(user_id: int, items: List[Dict[str, Any]], currency: str, country_code: Optional[str]) -> Dict[str, Any]:
    """
    items: list of {"product_id": int, "quantity": int}
    """
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    # compute subtotal
    subtotal = 0
    for it in items:
        row = conn.execute("SELECT price_cents, currency FROM products WHERE id = ?", (it["product_id"],)).fetchone()
        if not row:
            conn.close()
            raise ValueError(f"product {it['product_id']} not found")
        price_cents = int(row["price_cents"])
        prod_currency = row["currency"]
        if prod_currency.upper() != currency.upper():
            conn.close()
            raise ValueError("currency mismatch for product")
        subtotal += price_cents * int(it["quantity"])
    # tax
    tax_rule = db_get_tax_for_country(country_code) if country_code else None
    tax_percent = float(tax_rule["percentage"]) if tax_rule else 0.0
    tax_amount = int(round(subtotal * tax_percent))
    total = subtotal + tax_amount
    # create order
    cur.execute(
        "INSERT INTO orders (user_id, currency, subtotal_cents, tax_cents, total_cents, country_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, currency.upper(), subtotal, tax_amount, total, (country_code or "").upper(), now),
    )
    conn.commit()
    order_id = cur.lastrowid
    # create items
    for it in items:
        row = conn.execute("SELECT price_cents FROM products WHERE id = ?", (it["product_id"],)).fetchone()
        cur.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents) VALUES (?, ?, ?, ?)",
            (order_id, it["product_id"], it["quantity"], row["price_cents"]),
        )
    conn.commit()
    order_row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(order_row)

def db_list_orders_for_user(user_id: int, after_id: Optional[int], limit: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        if after_id:
            rows = conn.execute(
                "SELECT * FROM orders WHERE user_id = ? AND id < ? ORDER BY id DESC LIMIT ?",
                (user_id, after_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# --------------------------
# Pydantic schemas
# --------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str]

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ProductCreateRequest(BaseModel):
    name: str
    description: Optional[str]
    price_cents: int
    currency: str

class ProductRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price_cents: int
    currency: str
    created_at: str

class ProductsPage(BaseModel):
    items: List[ProductRead]
    next_cursor: Optional[str]
    has_more: bool

class CreateOrderRequest(BaseModel):
    items: List[int]  # product ids
    quantities: List[int]
    currency: str
    country_code: Optional[str]

class OrderRead(BaseModel):
    id: int
    user_id: int
    currency: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    country_code: Optional[str]
    created_at: str

# --------------------------
# Dependency: get current user from Authorization header
# --------------------------
async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload or "user_id" not in payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await asyncio.to_thread(db_get_user_by_id, int(payload["user_id"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# --------------------------
# REST endpoints
# --------------------------

@app.post("/register", response_model=Dict[str, Any])
async def register(req: RegisterRequest):
    existing = await asyncio.to_thread(db_get_user_by_email, req.email)
    if existing:
        raise HTTPException(status_code=400, detail="User exists")
    user = await asyncio.to_thread(db_create_user, req.email, req.password, req.full_name)
    # hide sensitive fields
    return {"id": user["id"], "email": user["email"], "full_name": user.get("full_name"), "created_at": user["created_at"]}

@app.post("/login", response_model=AuthResponse)
async def login(req: RegisterRequest):
    user = await asyncio.to_thread(db_get_user_by_email, req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"user_id": user["id"]})
    return AuthResponse(access_token=token)

@app.post("/products", response_model=ProductRead)
async def create_product(req: ProductCreateRequest, current_user: Dict = Depends(get_current_user)):
    # In production check roles/permissions; here any authenticated user can create
    prod = await asyncio.to_thread(db_create_product, req.name, req.description or "", req.price_cents, req.currency)
    return ProductRead(**prod)

@app.get("/products", response_model=ProductsPage)
async def list_products(limit: int = 10, after: Optional[str] = None):
    # Cursor-based pagination (id cursor)
    after_id = decode_cursor(after) if after else None
    fetch_limit = limit + 1  # fetch one extra to detect has_more
    rows = await asyncio.to_thread(db_list_products, after_id, fetch_limit)
    has_more = len(rows) == fetch_limit
    if has_more:
        rows = rows[:-1]
        next_cursor = encode_cursor(rows[-1]["id"])
    else:
        next_cursor = None
    items = [ProductRead(**r) for r in rows]
    return ProductsPage(items=items, next_cursor=next_cursor, has_more=has_more)

@app.get("/products/{product_id}", response_model=ProductRead)
async def get_product(product_id: int):
    p = await asyncio.to_thread(db_get_product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return ProductRead(**p)

@app.post("/orders", response_model=OrderRead)
async def create_order(req: CreateOrderRequest, current_user: Dict = Depends(get_current_user)):
    # validate lengths
    if len(req.items) != len(req.quantities):
        raise HTTPException(status_code=400, detail="items and quantities length mismatch")
    payload_items = [{"product_id": pid, "quantity": q} for pid, q in zip(req.items, req.quantities)]
    try:
        order = await asyncio.to_thread(db_create_order, int(current_user["id"]), payload_items, req.currency, req.country_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # publish Redis event
    if redis_client:
        evt = {
            "type": "order_created",
            "order_id": order["id"],
            "user_id": order["user_id"],
            "total_cents": order["total_cents"],
            "currency": order["currency"],
            "created_at": order["created_at"],
        }
        await redis_client.publish(ORDER_CHANNEL, json.dumps(evt))
    return OrderRead(**order)

@app.get("/orders", response_model=List[OrderRead])
async def list_orders(limit: int = 10, after: Optional[str] = None, current_user: Dict = Depends(get_current_user)):
    after_id = decode_cursor(after) if after else None
    rows = await asyncio.to_thread(db_list_orders_for_user, int(current_user["id"]), after_id, limit)
    return [OrderRead(**r) for r in rows]

# SSE endpoint to stream order events (Redis-backed)
@app.get("/events/orders")
async def stream_orders(request: Request):
    if not redis_client:
        raise HTTPException(status_code=503, detail="PubSub not configured")

    async def event_generator() -> AsyncGenerator[str, None]:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(ORDER_CHANNEL)
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    data = msg.get("data")
                    if isinstance(data, (bytes, bytearray)):
                        data = data.decode()
                    # SSE format
                    yield f"data: {data}\n\n"
                await asyncio.sleep(0.01)
        finally:
            await pubsub.unsubscribe(ORDER_CHANNEL)
            await pubsub.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Health
@app.get("/health")
async def health():
    return {"status": "ok", "redis": bool(redis_client)}

# --------------------------
# Startup / shutdown
# --------------------------
@app.on_event("startup")
async def on_startup():
    global redis_client
    await asyncio.to_thread(create_tables)
    await asyncio.to_thread(db_create_tax_rule, "US", 0.07)
    await asyncio.to_thread(db_create_tax_rule, "IN", 0.18)
    try:
        redis_client = aioredis.from_url(REDIS_URL)
        await redis_client.ping()
        print("Connected to Redis")
    except Exception as e:
        print("Redis not available:", e)
        redis_client = None

@app.on_event("shutdown")
async def on_shutdown():
    global redis_client
    if redis_client:
        await redis_client.close()
