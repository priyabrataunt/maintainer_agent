from fastapi import FastAPI

from backend.api.auth import router as auth_router
from backend.api.issues import router as issues_router
from backend.api.repositories import router as repositories_router
from backend.api.routes import router

app = FastAPI(title="Maintainer Agent")

app.include_router(router)
app.include_router(auth_router)
app.include_router(repositories_router)
app.include_router(issues_router)