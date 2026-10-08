from fastapi import FastAPI

from backend.api.actions import router as actions_router
from backend.api.admin import router as admin_router
from backend.api.auth import router as auth_router
from backend.api.duplicates import router as duplicates_router
from backend.api.investigations import router as investigations_router
from backend.api.issues import router as issues_router
from backend.api.jobs import router as jobs_router
from backend.api.repositories import router as repositories_router
from backend.api.routes import router
from backend.api.search import router as search_router

app = FastAPI(title="Maintainer Agent")

app.include_router(router)
app.include_router(auth_router)
app.include_router(repositories_router)
app.include_router(issues_router)
app.include_router(search_router)
app.include_router(investigations_router)
app.include_router(duplicates_router)
app.include_router(actions_router)
app.include_router(jobs_router)
app.include_router(admin_router)