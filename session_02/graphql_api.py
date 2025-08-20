# main.py
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as DBSession
import dataclasses
import strawberry
from strawberry.fastapi import GraphQLRouter

# ---------- Database (SQLite) ----------
DATABASE_URL = "sqlite:///./sessionql.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class SessionDB(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    speaker = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)   # minutes
    location = Column(String, nullable=True)

# create table(s)
Base.metadata.create_all(bind=engine)

# ---------- FastAPI app ----------
app = FastAPI(title="Sessions REST + GraphQL example")

# Middleware: attach a DB session to request.state (used by GraphQL context)
@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    request.state.db = SessionLocal()
    try:
        response = await call_next(request)
        return response
    finally:
        request.state.db.close()

# REST dependency (for REST endpoints)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Pydantic models (REST) ----------
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

# ---------- REST endpoints ----------
@app.post("/sessions/", response_model=SessionResponse)
def create_session_rest(body: SessionCreate, db: DBSession = Depends(get_db)):
    new = SessionDB(**body.dict())
    db.add(new)
    db.commit()
    db.refresh(new)
    return new

@app.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session_rest(session_id: int, db: DBSession = Depends(get_db)):
    s = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s

@app.get("/sessions/", response_model=List[SessionResponse])
def list_sessions_rest(db: DBSession = Depends(get_db)):
    return db.query(SessionDB).all()

@app.put("/sessions/{session_id}", response_model=SessionResponse)
def update_session_rest(session_id: int, body: SessionCreate, db: DBSession = Depends(get_db)):
    s = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    for k, v in body.dict().items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s

@app.patch("/sessions/{session_id}", response_model=SessionResponse)
def patch_session_rest(session_id: int, body: SessionUpdate, db: DBSession = Depends(get_db)):
    s = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    for k, v in body.dict(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s

@app.delete("/sessions/{session_id}")
def delete_session_rest(session_id: int, db: DBSession = Depends(get_db)):
    s = db.query(SessionDB).filter(SessionDB.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(s)
    db.commit()
    return {"detail": "deleted"}

# ---------- GraphQL types & helpers ----------
@strawberry.type
class SessionType:
    id: int
    title: str
    speaker: str
    duration: int
    location: Optional[str]

@strawberry.input
class SessionCreateInput:
    title: str
    speaker: str
    duration: int
    location: Optional[str] = None

@strawberry.input
class SessionPatchInput:
    title: Optional[str] = None
    speaker: Optional[str] = None
    duration: Optional[int] = None
    location: Optional[str] = None

def dbmodel_to_type(s: SessionDB) -> SessionType:
    return SessionType(
        id=s.id,
        title=s.title,
        speaker=s.speaker,
        duration=s.duration,
        location=s.location,
    )

# GraphQL Query
@strawberry.type
class Query:
    @strawberry.field
    def session(self, info, id: int) -> Optional[SessionType]:
        db: DBSession = info.context["db"]
        s = db.query(SessionDB).filter(SessionDB.id == id).first()
        if not s:
            return None
        return dbmodel_to_type(s)

    @strawberry.field
    def sessions(self, info) -> List[SessionType]:
        db: DBSession = info.context["db"]
        rows = db.query(SessionDB).all()
        return [dbmodel_to_type(r) for r in rows]

# GraphQL Mutations
@strawberry.type
class Mutation:
    @strawberry.mutation(name="createSession")
    def create_session(self, info, input: SessionCreateInput) -> SessionType:
        db: DBSession = info.context["db"]
        payload = dataclasses.asdict(input)
        new = SessionDB(**payload)
        db.add(new)
        db.commit()
        db.refresh(new)
        return dbmodel_to_type(new)

    @strawberry.mutation(name="updateSession")
    def update_session(self, info, id: int, input: SessionCreateInput) -> SessionType:
        db: DBSession = info.context["db"]
        s = db.query(SessionDB).filter(SessionDB.id == id).first()
        if not s:
            raise Exception("Session not found")
        for k, v in dataclasses.asdict(input).items():
            setattr(s, k, v)
        db.commit()
        db.refresh(s)
        return dbmodel_to_type(s)

    @strawberry.mutation(name="patchSession")
    def patch_session(self, info, id: int, input: SessionPatchInput) -> SessionType:
        db: DBSession = info.context["db"]
        s = db.query(SessionDB).filter(SessionDB.id == id).first()
        if not s:
            raise Exception("Session not found")
        for k, v in dataclasses.asdict(input).items():
            # treat `None` as "not provided" (do not overwrite) — if you want to explicitly set NULL,
            # you'd need a different pattern to distinguish "omitted" vs "null".
            if v is not None:
                setattr(s, k, v)
        db.commit()
        db.refresh(s)
        return dbmodel_to_type(s)

    @strawberry.mutation(name="deleteSession")
    def delete_session(self, info, id: int) -> bool:
        db: DBSession = info.context["db"]
        s = db.query(SessionDB).filter(SessionDB.id == id).first()
        if not s:
            return False
        db.delete(s)
        db.commit()
        return True
        
    @strawberry.mutation(name="createSessions")
    def create_sessions(self, info, inputs: List[SessionCreateInput]) -> List[SessionType]:
        db: DBSession = info.context["db"]
        created = []
        for inp in inputs:
            payload = dataclasses.asdict(inp)
            new = SessionDB(**payload)
            db.add(new)
            db.commit()
            db.refresh(new)
            created.append(dbmodel_to_type(new))
        return created


# ---------- GraphQL app & wiring ----------
schema = strawberry.Schema(query=Query, mutation=Mutation)

# context_getter uses the DB session created in the middleware (request.state.db)
async def get_context(request: Request):
    return {"request": request, "db": request.state.db}

graphql_router = GraphQLRouter(schema, graphiql=True, context_getter=get_context)
app.include_router(graphql_router, prefix="/graphql")
