from fastapi import FastAPI, HTTPException, Query, Path, status, Body

app=FastAPI()

class Taskread(TaskCreate):
    id: int
    
@app.post("/api/v1/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate = Body(...)):
    task={
    "id": 1,
    "title": payload.title,
    "description": payload.description,
    "status": "open",
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow
   }
    return task

  