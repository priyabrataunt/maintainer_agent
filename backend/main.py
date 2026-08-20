from fastapi import FastAPI

from backend.api.routes import router

app = FastAPI(title="Maintainer Agent")

app.include_router(router)