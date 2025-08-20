from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class book(BaseModel):
    id : int|None= None
    title: str


books = [

    book(id=1, title="1984",),
    book(id=2, title="To Kill a Mockingbird")
]

@app.get("/books")
def list_books():
    return books

@app.get("/books/{id}")
def get_book(id: int):
    for b in books:
        if b.id == id:
            return b
    # raise HTTPException()

