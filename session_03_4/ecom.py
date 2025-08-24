# Real-time E-commerce GraphQL API with FastAPI + Strawberry + SQLite (SQLModel)
# Features:
# - Queries: products, product, customers, orders, order
# - Mutations: create/update product & customer, place order, update order status
# - Subscriptions (real-time): orderCreated, orderUpdated(orderId)
# - Input validation & clear error messages
# - Simple in-memory PubSub for live updates
# - SQLite persistence (ecom.db)
# prompt for github copilot:Create a single-file FastAPI + Strawberry GraphQL e-commerce API using SQLite (SQLModel).

# Include:
# - Models: Product(id, title, description, price_cents, stock, created_at, updated_at),
#   Customer(id, name, email, created_at),
#   Order(id, customer_id, status, total_cents, timestamps),
#   OrderItem(id, order_id, product_id, quantity, unit_price_cents, subtotal_cents).
# - Queries: products(search, inStock, limit, offset), product(id), customers, orders(customerId, status, limit, offset), order(id).
# - Mutations: createProduct, updateProduct, createCustomer, placeOrder(customerId, items[{productId, quantity}]), updateOrderStatus(orderId, status).
# - Subscriptions: orderCreated, orderUpdated(orderId) using in-memory PubSub.
# - Use camelCase in GraphQL, inputs validated (no negative prices/stock, check stock on order).
# - Provide a health route and startup DB init.
# - Show run instructions with uvicorn.
# Keep it clean, commented, and idiomatic.

from __future__ import annotations
from typing import Optional, List, AsyncGenerator, Dict, Any
from datetime import datetime
import asyncio

from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
import strawberry

from sqlmodel import SQLModel, Field, create_engine, Session, select

# ---------------------------
# Database Models (SQLModel)
# ---------------------------

DB_URL = "sqlite:///./ecom.db"
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})

class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    description: Optional[str] = None
    price_cents: int = Field(default=0, ge=0)  # store money in cents
    stock: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id")
    status: str = Field(default="pending")  # pending, paid, shipped, delivered, cancelled
    total_cents: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class OrderItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    product_id: int = Field(foreign_key="product.id")
    quantity: int = Field(default=1, ge=1)
    unit_price_cents: int = Field(default=0, ge=0)
    subtotal_cents: int = Field(default=0, ge=0)

def init_db():
    SQLModel.metadata.create_all(engine)

# ---------------------------
# Simple PubSub (in-memory)
# ---------------------------

class EventBus:
    def __init__(self) -> None:
        self._topics: Dict[str, List[asyncio.Queue]] = {}

    async def publish(self, topic: str, payload: Any) -> None:
        for q in self._topics.get(topic, []):
            await q.put(payload)

    async def subscribe(self, topic: str) -> AsyncGenerator[Any, None]:
        q: asyncio.Queue = asyncio.Queue()
        self._topics.setdefault(topic, []).append(q)
        try:
            while True:
                item = await q.get()
                yield item
        finally:
            self._topics[topic].remove(q)

bus = EventBus()

# Topic helpers
def topic_order_created() -> str:
    return "order_created"

def topic_order_updated(order_id: int | None = None) -> str:
    return f"order_updated:{order_id}" if order_id else "order_updated:*"

# ---------------------------
# GraphQL Types & Inputs
# ---------------------------

def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"

@strawberry.type
class ProductType:
    id: int
    title: str
    description: Optional[str]
    price_cents: int
    stock: int
    created_at: str
    updated_at: str

@strawberry.type
class CustomerType:
    id: int
    name: str
    email: str
    created_at: str

@strawberry.type
class OrderItemType:
    id: int
    product_id: int
    quantity: int
    unit_price_cents: int
    subtotal_cents: int

@strawberry.type
class OrderType:
    id: int
    customer_id: int
    status: str
    total_cents: int
    created_at: str
    updated_at: str
    items: List[OrderItemType]

@strawberry.type
class OrderEventType:
    order_id: int
    status: str
    total_cents: int
    emitted_at: str

@strawberry.input
class ProductCreateInput:
    title: str
    description: Optional[str] = None
    price_cents: int = 0
    stock: int = 0

@strawberry.input
class ProductUpdateInput:
    title: Optional[str] = None
    description: Optional[str] = None
    price_cents: Optional[int] = None
    stock: Optional[int] = None

@strawberry.input
class CustomerCreateInput:
    name: str
    email: str

@strawberry.input
class OrderItemInput:
    product_id: int
    quantity: int = 1

# ---------------------------
# Mappers (DB -> GraphQL)
# ---------------------------

def to_product_type(p: Product) -> ProductType:
    return ProductType(
        id=p.id, title=p.title, description=p.description,
        price_cents=p.price_cents, stock=p.stock,
        created_at=iso(p.created_at), updated_at=iso(p.updated_at)
    )

def to_customer_type(c: Customer) -> CustomerType:
    return CustomerType(id=c.id, name=c.name, email=c.email, created_at=iso(c.created_at))

def to_order_item_type(oi: OrderItem) -> OrderItemType:
    return OrderItemType(
        id=oi.id, product_id=oi.product_id, quantity=oi.quantity,
        unit_price_cents=oi.unit_price_cents, subtotal_cents=oi.subtotal_cents
    )

def to_order_type(session: Session, o: Order) -> OrderType:
    items = session.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all()
    return OrderType(
        id=o.id, customer_id=o.customer_id, status=o.status, total_cents=o.total_cents,
        created_at=iso(o.created_at), updated_at=iso(o.updated_at),
        items=[to_order_item_type(oi) for oi in items]
    )

# ---------------------------
# GraphQL Root: Query
# ---------------------------

@strawberry.type
class Query:
    @strawberry.field
    def products(self, search: Optional[str] = None, in_stock: Optional[bool] = None,
                 limit: int = 20, offset: int = 0) -> List[ProductType]:
        with Session(engine) as session:
            stmt = select(Product)
            if search:
                like = f"%{search}%"
                stmt = stmt.where((Product.title.ilike(like)) | (Product.description.ilike(like)))
            if in_stock is True:
                stmt = stmt.where(Product.stock > 0)
            stmt = stmt.order_by(Product.id.desc()).offset(offset).limit(min(limit, 100))
            rows = session.exec(stmt).all()
            return [to_product_type(p) for p in rows]

    @strawberry.field
    def product(self, id: int) -> Optional[ProductType]:
        with Session(engine) as session:
            p = session.get(Product, id)
            return to_product_type(p) if p else None

    @strawberry.field
    def customers(self, limit: int = 20, offset: int = 0) -> List[CustomerType]:
        with Session(engine) as session:
            stmt = select(Customer).order_by(Customer.id.desc()).offset(offset).limit(min(limit, 100))
            rows = session.exec(stmt).all()
            return [to_customer_type(c) for c in rows]

    @strawberry.field
    def orders(self, customer_id: Optional[int] = None, status: Optional[str] = None,
               limit: int = 20, offset: int = 0) -> List[OrderType]:
        with Session(engine) as session:
            stmt = select(Order)
            if customer_id:
                stmt = stmt.where(Order.customer_id == customer_id)
            if status:
                stmt = stmt.where(Order.status == status)
            stmt = stmt.order_by(Order.id.desc()).offset(offset).limit(min(limit, 100))
            rows = session.exec(stmt).all()
            return [to_order_type(session, o) for o in rows]

    @strawberry.field
    def order(self, id: int) -> Optional[OrderType]:
        with Session(engine) as session:
            o = session.get(Order, id)
            return to_order_type(session, o) if o else None

# ---------------------------
# GraphQL Root: Mutation
# ---------------------------

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled"}

@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_product(self, input: ProductCreateInput) -> ProductType:
        if input.price_cents < 0 or input.stock < 0:
            raise ValueError("price_cents and stock must be non-negative")
        with Session(engine) as session:
            p = Product(
                title=input.title, description=input.description,
                price_cents=input.price_cents, stock=input.stock
            )
            session.add(p)
            session.commit(); session.refresh(p)
            return to_product_type(p)

    @strawberry.mutation
    def update_product(self, id: int, input: ProductUpdateInput) -> ProductType:
        with Session(engine) as session:
            p = session.get(Product, id)
            if not p:
                raise ValueError("product not found")
            if input.title is not None: p.title = input.title
            if input.description is not None: p.description = input.description
            if input.price_cents is not None:
                if input.price_cents < 0:
                    raise ValueError("price_cents must be >= 0")
                p.price_cents = input.price_cents
            if input.stock is not None:
                if input.stock < 0:
                    raise ValueError("stock must be >= 0")
                p.stock = input.stock
            p.updated_at = datetime.utcnow()
            session.add(p); session.commit(); session.refresh(p)
            return to_product_type(p)

    @strawberry.mutation
    def create_customer(self, input: CustomerCreateInput) -> CustomerType:
        with Session(engine) as session:
            c = Customer(name=input.name, email=input.email)
            session.add(c); session.commit(); session.refresh(c)
            return to_customer_type(c)

    @strawberry.mutation
    async def place_order(self, customer_id: int, items: List[OrderItemInput]) -> OrderType:
        if not items:
            raise ValueError("items cannot be empty")
        with Session(engine) as session:
            customer = session.get(Customer, customer_id)
            if not customer:
                raise ValueError("customer not found")

            # Validate items and compute totals
            total = 0
            prepared: List[Dict[str, int]] = []
            for it in items:
                if it.quantity <= 0:
                    raise ValueError("quantity must be positive")
                prod = session.get(Product, it.product_id)
                if not prod:
                    raise ValueError(f"product {it.product_id} not found")
                if prod.stock < it.quantity:
                    raise ValueError(f"insufficient stock for product {prod.id}")
                subtotal = prod.price_cents * it.quantity
                total += subtotal
                prepared.append({
                    "product_id": prod.id,
                    "quantity": it.quantity,
                    "unit_price_cents": prod.price_cents,
                    "subtotal_cents": subtotal
                })

            # Create order + items, decrement stock
            order = Order(customer_id=customer_id, status="pending", total_cents=total)
            session.add(order); session.commit(); session.refresh(order)

            for pr in prepared:
                oi = OrderItem(order_id=order.id, **pr)
                session.add(oi)
                # decrement stock
                prod = session.get(Product, pr["product_id"])
                prod.stock -= pr["quantity"]
                prod.updated_at = datetime.utcnow()
                session.add(prod)

            order.updated_at = datetime.utcnow()
            session.add(order); session.commit()

            # Publish real-time event
            await bus.publish(topic_order_created(), OrderEventType(
                order_id=order.id, status=order.status, total_cents=order.total_cents,
                emitted_at=iso(datetime.utcnow())
            ))
            await bus.publish(topic_order_updated(order.id), OrderEventType(
                order_id=order.id, status=order.status, total_cents=order.total_cents,
                emitted_at=iso(datetime.utcnow())
            ))

            return to_order_type(session, order)

    @strawberry.mutation
    async def update_order_status(self, order_id: int, status: str) -> OrderType:
        status = status.lower()
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status. valid: {sorted(VALID_STATUSES)}")
        with Session(engine) as session:
            order = session.get(Order, order_id)
            if not order:
                raise ValueError("order not found")
            order.status = status
            order.updated_at = datetime.utcnow()
            session.add(order); session.commit()
            # Publish real-time update
            await bus.publish(topic_order_updated(order.id), OrderEventType(
                order_id=order.id, status=order.status, total_cents=order.total_cents,
                emitted_at=iso(datetime.utcnow())
            ))
            return to_order_type(session, order)

# ---------------------------
# GraphQL Root: Subscription
# ---------------------------

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def order_created(self) -> AsyncGenerator[OrderEventType, None]:
        async for ev in bus.subscribe(topic_order_created()):
            yield ev

    @strawberry.subscription
    async def order_updated(self, order_id: int) -> AsyncGenerator[OrderEventType, None]:
        async for ev in bus.subscribe(topic_order_updated(order_id)):
            yield ev

# ---------------------------
# App wiring
# ---------------------------

schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
app = FastAPI(title="E-commerce GraphQL API")
app.include_router(GraphQLRouter(schema), prefix="/graphql")

@app.on_event("startup")
def _startup() -> None:
    init_db()

# Optional health check (handy for Docker/k8s)
@app.get("/health")
def health():
    return {"status": "ok", "time": iso(datetime.utcnow())}
