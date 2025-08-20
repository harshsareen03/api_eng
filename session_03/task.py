from pydantic import BaseModel, constr
from typing import Optional
from datetime import datetime

class TaskCreate(BaseModel):
    title: constr(min_length=1, max_length=200)
    description: Optional[str] = None
    due_date: Optional[datetime] = None

class TaskRead(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

class TaskUpdate(BaseModel):
    title: Optional[constr(min_length=1, max_length=200)]
    description: Optional[str]
    status: Optional[str]