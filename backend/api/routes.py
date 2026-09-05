from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.project_analyzer import analyze_project as analyze_project_service

router = APIRouter()


class SourceFile(BaseModel):
    file_path: str
    code: str


class ProjectAnalysisRequest(BaseModel):
    project_name: str
    description: str
    file_path: str
    code: str
    files: list[SourceFile] = Field(default_factory=list)


class Finding(BaseModel):
    file_path: str
    rule: str
    severity: Literal["info", "warning", "error"]
    message: str


class AnalysisResult(BaseModel):
    project_name: str
    status: str
    summary: str
    findings: list[Finding]


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
        file_path=request.file_path,
        code=request.code,
        files=[file.model_dump() for file in request.files],
    )
