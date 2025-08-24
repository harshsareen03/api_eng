import asyncio
import base64
from datetime import datetime, timedelta
from typing import AsyncGenerator, List, Optional

import jwt
import strawberry
from passlib.context import CryptContext
from fastapi import FastAPI, Request
from sqlmodel import Field, Session, SQLModel, create_engine, select
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

# ---------------------
# Config / Secrets
# ---------------------
JWT_SECRET = "my_super_secret_key_123"
JWT_ALGO = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

DB_URL = "sqlite:///./ecommerce.db"
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------
# DB Models (SQLModel)
# ---------------------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True)
    password_hash: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    price_cents: int
    currency: str = "USD"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    total_cents: int
    tax_cents: int
    currency: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OrderItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    product_id: int = Field(foreign_key="product.id")
    quantity: int
    unit_price_cents: int


def init_db():
    SQLModel.metadata.create_all(engine)


# ---------------------
# Utilities
# ---------------------
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(minutes=expires_minutes)}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.PyJWTError:
        raise Exception("Invalid token")


def encode_cursor(pk: int) -> str:
    return base64.urlsafe_b64encode(str(pk).encode()).decode()


def decode_cursor(cursor: str) -> int:
    return int(base64.urlsafe_b64decode(cursor.encode()).decode())


# Tax rules
TAX_RULES = {
    "US": 0.07,
    "IN": 0.18,
    "GB": 0.20,
    "DE": 0.19,
}


def calculate_tax(subtotal_cents: int, country: str) -> int:
    rate = TAX_RULES.get(country.upper(), 0.0)
    return int(round(subtotal_cents * rate))


# ---------------------
# Simple in-memory PubSub
# ---------------------
class InMemoryPubSub:
    def __init__(self):
        self.subscribers: List[asyncio.Queue] = []

    async def publish(self, message):
        for q in list(self.subscribers):
            await q.put(message)

    async def subscribe(self) -> AsyncGenerator:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.append(q)
        try:
            while True:
                item = await q.get()
                yield item
        finally:
            try:
                self.subscribers.remove(q)
            except ValueError:
                pass


pubsub = InMemoryPubSub()

# ---------------------
# GraphQL Types
# ---------------------
@strawberry.type
class UserType:
    id: int
    username: str
    createdAt: str


@strawberry.type
class ProductType:
    id: int
    name: str
    description: Optional[str]
    priceCents: int
    currency: str
    createdAt: str


@strawberry.type
class OrderItemType:
    productId: int
    quantity: int
    unitPriceCents: int


@strawberry.type
class OrderType:
    id: int
    userId: int
    totalCents: int
    taxCents: int
    currency: str
    createdAt: str
    items: List[OrderItemType]


@strawberry.type
class PageInfo:
    hasNextPage: bool
    endCursor: Optional[str]


@strawberry.type
class ProductEdge:
    cursor: str
    node: ProductType


@strawberry.type
class ProductConnection:
    edges: List[ProductEdge]
    pageInfo: PageInfo


@strawberry.type
class TokenType:
    id: int
    username: str
    accessToken: str
    tokenType: str = "bearer"


# ---------------------
# Inputs
# ---------------------
@strawberry.input
class RegisterInput:
    username: str
    password: str


@strawberry.input
class LoginInput:
    username: str
    password: str


@strawberry.input
class CreateProductInput:
    name: str
    description: Optional[str] = None
    priceCents: int
    currency: Optional[str] = "USD"


@strawberry.input
class OrderItemInput:
    productId: int
    quantity: int


@strawberry.input
class CreateOrderInput:
    items: List[OrderItemInput]
    shippingCountry: str


# ---------------------
# Context
# ---------------------
async def get_context(request: Request):
    auth = request.headers.get("authorization")
    user = None
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
        try:
            user_id = decode_token(token)
            with Session(engine) as session:
                user = session.get(User, user_id)
        except Exception:
            user = None
    return {"request": request, "user": user}


# ---------------------
# Helpers
# ---------------------
def product_to_gql(p: Product) -> ProductType:
    return ProductType(
        id=p.id,
        name=p.name,
        description=p.description,
        priceCents=p.price_cents,
        currency=p.currency,
        createdAt=p.created_at.isoformat(),
    )


def order_to_gql(order: Order) -> OrderType:
    with Session(engine) as session:
        items = session.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    item_types = [
        OrderItemType(productId=i.product_id, quantity=i.quantity, unitPriceCents=i.unit_price_cents)
        for i in items
    ]
    return OrderType(
        id=order.id,
        userId=order.user_id,
        totalCents=order.total_cents,
        taxCents=order.tax_cents,
        currency=order.currency,
        createdAt=order.created_at.isoformat(),
        items=item_types,
    )


# ---------------------
# Queries / Mutations / Subscriptions
# ---------------------
@strawberry.type
class Query:
    @strawberry.field
    def me(self, info: Info) -> Optional[UserType]:
        user = info.context.get("user")
        if not user:
            return None
        return UserType(id=user.id, username=user.username, createdAt=user.created_at.isoformat())

    @strawberry.field
    def product(self, id: int) -> Optional[ProductType]:
        with Session(engine) as session:
            p = session.get(Product, id)
            return product_to_gql(p) if p else None

    @strawberry.field
    def products(self, first: int = 10, after: Optional[str] = None) -> ProductConnection:
        with Session(engine) as session:
            stmt = select(Product).order_by(Product.id)
            if after:
                last_id = decode_cursor(after)
                stmt = stmt.where(Product.id > last_id)
            limit = min(max(1, first), 100)
            results = session.exec(stmt.limit(limit + 1)).all()
            has_next = len(results) > limit
            edges = [
                ProductEdge(cursor=encode_cursor(p.id), node=product_to_gql(p))
                for p in results[:limit]
            ]
            end_cursor = edges[-1].cursor if edges else None
            return ProductConnection(edges=edges, pageInfo=PageInfo(hasNextPage=has_next, endCursor=end_cursor))


@strawberry.type
class Mutation:
    @strawberry.mutation
    def register(self, input: RegisterInput) -> TokenType:
        with Session(engine) as session:
            existing = session.exec(select(User).where(User.username == input.username)).first()
            if existing:
                raise Exception("username already exists")
            u = User(username=input.username, password_hash=get_password_hash(input.password))
            session.add(u)
            session.commit()
            session.refresh(u)
            token = create_access_token(u.id)
            return TokenType(id=u.id, username=u.username, accessToken=token)

    @strawberry.mutation
    def login(self, input: LoginInput) -> TokenType:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == input.username)).first()
            if not user or not verify_password(input.password, user.password_hash):
                raise Exception("Invalid credentials")
            token = create_access_token(user.id)
            return TokenType(id=user.id, username=user.username, accessToken=token)

    @strawberry.mutation
    def createProduct(self, input: CreateProductInput, info: Info) -> ProductType:
        user = info.context.get("user")
        if not user:
            raise Exception("Authentication required")
        if input.priceCents <= 0:
            raise Exception("priceCents must be > 0")
        with Session(engine) as session:
            p = Product(
                name=input.name,
                description=input.description,
                price_cents=input.priceCents,
                currency=input.currency or "USD",
            )
            session.add(p)
            session.commit()
            session.refresh(p)
            return product_to_gql(p)

    @strawberry.mutation
    async def createOrder(self, input: CreateOrderInput, info: Info) -> OrderType:
        user = info.context.get("user")
        if not user:
            raise Exception("Authentication required")
        with Session(engine) as session:
            subtotal = 0
            for it in input.items:
                product = session.get(Product, it.productId)
                if not product:
                    raise Exception(f"product {it.productId} not found")
                if it.quantity <= 0:
                    raise Exception("quantity must be > 0")
                subtotal += product.price_cents * it.quantity
            tax = calculate_tax(subtotal, input.shippingCountry)
            total = subtotal + tax
            order = Order(user_id=user.id, total_cents=total, tax_cents=tax, currency="USD")
            session.add(order)
            session.commit()
            session.refresh(order)
            for it in input.items:
                product = session.get(Product, it.productId)
                oi = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=it.quantity,
                    unit_price_cents=product.price_cents,
                )
                session.add(oi)
            session.commit()
            session.refresh(order)
        await pubsub.publish(order_to_gql(order))
        return order_to_gql(order)


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def orderCreated(self) -> AsyncGenerator[OrderType, None]:
        async for order in pubsub.subscribe():
            yield order


# ---------------------
# FastAPI + GraphQL setup
# ---------------------
schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
graphql_app = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI()
app.include_router(graphql_app, prefix="/graphql")


@app.on_event("startup")
def on_startup():
    init_db()
