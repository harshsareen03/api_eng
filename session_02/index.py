from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Database setup (SQLite for demo)
DATABASE_URL = "sqlite:///./sessio.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# SQLAlchemy Model (DB table)
class SessionDB(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    speaker = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)  # minutes
    location = Column(String, nullable=True)

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic Schemas
class SessionCreate(BaseModel):
    title: str
    speaker: str
    duration: int
    location: Optional[str] = None

class SessionUpdate(BaseModel):
    title: Optional[str] = None
    speaker: Optional[str] = None
    duration: Optional[int] = None
    location: Optional[str] = None

class SessionResponse(SessionCreate):
    id: int

    class Config:
        orm_mode = True

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# FastAPI app
app = FastAPI()

# POST - Create Session
@app.post("/sessions/", response_model=SessionResponse)
def create_session(session: SessionCreate, db: Session = Depends(get_db)):
    new_session = SessionDB(**session.dict())
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session

# GET - Retrieve Session
@app.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

# GET ALL - List Sessions
@app.get("/sessions/", response_model=List[SessionResponse])
def list_sessions(db: Session = Depends(get_db)):
    return db.query(SessionDB).all()

# PUT - Full Update
@app.put("/sessions/{session_id}", response_model=SessionResponse)
def update_session(session_id: int, session: SessionCreate, db: Session = Depends(get_db)):
    db_session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    for key, value in session.dict().items():
        setattr(db_session, key, value)
    db.commit()
    db.refresh(db_session)
    return db_session

# PATCH - Partial Update
@app.patch("/sessions/{session_id}", response_model=SessionResponse)
def patch_session(session_id: int, session: SessionUpdate, db: Session = Depends(get_db)):
    db_session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    for key, value in session.dict(exclude_unset=True).items():
        setattr(db_session, key, value)
    db.commit()
    db.refresh(db_session)
    return db_session

# DELETE - Remove Session
@app.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    db_session = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(db_session)
    db.commit()
    return {"detail": "Session deleted"}


