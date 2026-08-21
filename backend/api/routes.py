from fastapi import APIRouter
from pydantic import BaseModel
from backend.services.project_analyzer import analyze_project as analyze_project_service
router = APIRouter()

class ProjectAnalysisRequest(BaseModel):
    project_name: str
    description: str
    file_path: str
    code: str

class AnalysisResult(BaseModel):
    project_name: str
    status: str
    summary: str
    findings: list[str]


@router.get("/")
def home():
    return {"message": "Maintainer Agent is running"}

@router.get("/health")
def health():
    return {"status": "healthy"}

@router.post("/analyze", response_model=AnalysisResult)
def analyze_project_endpoint(request: ProjectAnalysisRequest):
    return analyze_project_service(
        project_name=request.project_name,
        description=request.description,
        file_path= request.file_path,
        code=request.code,
    )


