from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.services.project_analyzer import (
    analyze_project as analyze_project_service,
)
from backend.services.project_analyzer import (
    analyze_project_folder as analyze_project_folder_service,
)

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


class ProjectFolderAnalysisRequest(BaseModel):
    project_name: str
    description: str
    project_path: str = Field(min_length=1)


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


@router.get("/db-health")
def db_health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
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


@router.post("/analyze-folder", response_model=AnalysisResult)
def analyze_project_folder_endpoint(request: ProjectFolderAnalysisRequest):
    try:
        return analyze_project_folder_service(
            project_name=request.project_name,
            description=request.description,
            project_path=request.project_path,
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
