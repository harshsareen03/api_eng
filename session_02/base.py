from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Session model
class Session(BaseModel):
    id: int
    title: str
    speaker: str
    duration: int  # in minutes

# In-memory "database"
sessions: Dict[int, Session] = {}

# POST - Create a new session
@app.post("/sessions/", response_model=Session)
def create_session(session: Session):
    if session.id in sessions:
        raise HTTPException(status_code=400, detail="Session already exists")
    sessions[session.id] = session
    return session

# GET - Retrieve a session
@app.get("/sessions/{session_id}", response_model=Session)
def get_session(session_id: int):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]

# PUT - Replace a session (full update)
@app.put("/sessions/{session_id}", response_model=Session)
def update_session(session_id: int, session: Session):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    sessions[session_id] = session
    return session

# PATCH - Partial update
@app.patch("/sessions/{session_id}", response_model=Session)
def patch_session(session_id: int, session: dict):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    stored_session = sessions[session_id].dict()
    updated_session = stored_session | session  # merge dicts
    sessions[session_id] = Session(**updated_session)
    return sessions[session_id]

# DELETE - Remove a session
@app.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del sessions[session_id]
    return {"detail": "Session deleted"}
