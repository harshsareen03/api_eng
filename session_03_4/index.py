# prompt of copilot:

# You are an expert Python developer. Generate a complete, runnable FastAPI project scaffold that uses SQLModel and SQLite for persistent storage, with the following:
# - API base path /api/v1
# - Resource "Task" with fields id, title, description, status, created_at, updated_at
# - Provide endpoints: list (with cursor pagination), create, read, patch (partial update), delete
# - Use Pydantic validation for request and response models.
# - Return proper HTTP status codes (201 on create, 204 on delete, 404 when not found, 422 for validation)
# - Include tests using pytest + TestClient that cover creating a task, validation failure, retrieving a task, and update.
# - Include a README section showing how to run the server and the tests.
# - Keep code simple and idiomatic, add comments explaining key parts.

# Generate all files: main.py, test_api.py, requirements.txt, README.md.

# main.py
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query, Path, status, Body
from sqlmodel import SQLModel, Field, create_engine, Session, select
from datetime import datetime
from pydantic import BaseModel, constr

DB_URL = "sqlite:///./app.db"
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})

class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: constr(min_length=1, max_length=200)
    description: Optional[str] = None
    task_name: Optional[str] = None
    status: str = Field(default="open", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class TaskCreate(BaseModel):
    title: constr(min_length=1, max_length=200)
    description: Optional[str] = None
    due_date: Optional[datetime] = None

class TaskRead(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

class TaskUpdate(BaseModel):
    title: Optional[constr(min_length=1, max_length=200)]
    description: Optional[str]
    status: Optional[str]

def init_db():
    SQLModel.metadata.create_all(engine)

app = FastAPI(title="Tasks API", version="1.0.0")

@app.on_event("startup")
def on_startup():
    init_db()

@app.post("/api/v1/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate = Body(...)):
    with Session(engine) as session:
        task = Task(title=payload.title, description=payload.description)
        session.add(task)
        session.commit()
        session.refresh(task)
        return task

@app.get("/api/v1/tasks", response_model=List[TaskRead])
def list_tasks(limit: int = Query(20, ge=1, le=100), before_id: Optional[int] = Query(None)):
    """
    Simple cursor-style pagination using `before_id` to get tasks with id < before_id
    """
    with Session(engine) as session:
        stmt = select(Task).order_by(Task.id.desc()).limit(limit)
        if before_id:
            stmt = stmt.where(Task.id < before_id)
        results = session.exec(stmt).all()
        return results

@app.get("/api/v1/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int = Path(..., gt=0)):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

@app.patch("/api/v1/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        updated = False
        if payload.title is not None:
            task.title = payload.title
            updated = True
        if payload.description is not None:
            task.description = payload.description
            updated = True
        if payload.status is not None:
            if payload.status not in ("open", "in_progress", "done"):
                raise HTTPException(status_code=400, detail="Invalid status")
            task.status = payload.status
            updated = True
        if updated:
            task.updated_at = datetime.utcnow()
            session.add(task)
            session.commit()
            session.refresh(task)
        return task

@app.delete("/api/v1/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        session.delete(task)
        session.commit()
        return None

# Simple health check
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
