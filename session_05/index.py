from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from fastapi.middleware.cors import CORSMiddleware

# SQLite setup
DATABASE_URL = "sqlite:///./ecom.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# Models
class ProductDB(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    in_stock = Column(Boolean, default=True)

Base.metadata.create_all(bind=engine)

# Schemas
class Product(BaseModel):
    id: int
    name: str
    price: float
    in_stock: bool
    class Config:
        orm_mode = True

class ProductCreate(BaseModel):
    name: str
    price: float
    in_stock: bool = True

# FastAPI app
app = FastAPI(title="E-commerce API")

# 🔑 Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # For dev, allow all. In prod, restrict.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Routes
@app.get("/products", response_model=List[Product])
def list_products(db: Session = Depends(get_db)):
    return db.query(ProductDB).all()

@app.post("/products", response_model=Product)
def create_product(p: ProductCreate, db: Session = Depends(get_db)):
    new = ProductDB(**p.dict())
    db.add(new)
    db.commit()
    db.refresh(new)
    return new

@app.get("/products/{pid}", response_model=Product)
def get_product(pid: int, db: Session = Depends(get_db)):
    prod = db.query(ProductDB).get(pid)
    if not prod:
        raise HTTPException(404, "Product not found")
    return prod

@app.delete("/products/{pid}")
def delete_product(pid: int, db: Session = Depends(get_db)):
    prod = db.query(ProductDB).get(pid)
    if not prod:
        raise HTTPException(404, "Product not found")
    db.delete(prod)
    db.commit()
    return {"deleted": True}
