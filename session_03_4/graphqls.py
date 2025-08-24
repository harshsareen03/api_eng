import strawberry
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
from datetime import datetime
from typing import List

@strawberry.type
class TaskType:
    id: int
    title: str
    description: str
    status: str
    created_at: str = strawberry.field(name="created_at")  # 👈 force GraphQL to use snake_case

@strawberry.type
class Query:
    @strawberry.field
    def tasks(self, limit: int = 20) -> List[TaskType]:
        return [
            TaskType(
                id=1,
                title="Test GraphQL",
                description="A sample task",
                status="open",
                created_at=datetime.utcnow().isoformat(),
            )
        ][:limit]

schema = strawberry.Schema(query=Query)

app = FastAPI()
app.include_router(GraphQLRouter(schema), prefix="/graphql")
