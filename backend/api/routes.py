from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter()


@router.get("/")
def home():
    return {"message": "Maintainer Agent is running"}


@router.get("/health")
def health():
    return {"status": "healthy"}


class ProjectAnalysisRequest(BaseModel):
    project_name: str
    description: str

@router.post("/analyze")
def analyze_project(request: ProjectAnalysisRequest):
    return {
        "project_name": request.project_name,
        "status": "received",
        "message": "The Maintainer Agent is ready to analyze this project.",
    }