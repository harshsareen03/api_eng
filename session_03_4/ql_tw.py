import strawberry
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

@strawberry.type
class Task:
    title: str
    status: str

@strawberry.type
class User:
    id: int
    name: str
    tasks: list[Task]

def get_user(id: int) -> User:
    return User(id=id, name="Alice", tasks=[Task(title="Test", status="open")])

@strawberry.type
class Query:
    user: User = strawberry.field(resolver=get_user)

schema = strawberry.Schema(query=Query)
app = FastAPI()
app.include_router(GraphQLRouter(schema), prefix="/graphql")
