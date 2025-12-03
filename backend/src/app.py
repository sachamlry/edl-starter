"""
TaskFlow Backend - FastAPI Task Management Service

A RESTful API for task management with TDD approach.

TP 1 & 2: Uses in-memory storage for simplicity
TP 3: Will introduce PostgreSQL database (see migration guide)
"""

from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import logging
from contextlib import asynccontextmanager
import uuid
from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from .database import get_db, init_db
from .models import TaskModel, TaskStatus, TaskPriority

from fastapi.middleware.cors import CORSMiddleware
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("taskflow")


# =============================================================================
# ENUMS & MODELS
# =============================================================================






class TaskCreate(BaseModel):
    """Model for creating a new task."""
    title: str = Field(..., min_length=1, max_length=200, description="Task title")
    description: Optional[str] = Field(None, max_length=1000, description="Task description")
    status: TaskStatus = Field(default=TaskStatus.TODO, description="Task status")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Task priority")
    assignee: Optional[str] = Field(None, max_length=100, description="Assigned user")
    due_date: Optional[datetime] = Field(None, description="Due date")


class TaskUpdate(BaseModel):
    """Model for updating a task - all fields optional for partial updates."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    assignee: Optional[str] = Field(None, max_length=100)
    due_date: Optional[datetime] = None


class Task(BaseModel):
    """Model for task response."""
    id: str  # ← Changé en str pour UUID
    title: str
    description: Optional[str] = None
    status: TaskStatus
    priority: TaskPriority
    assignee: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Permet la conversion depuis SQLAlchemy


# =============================================================================
# IN-MEMORY STORAGE (for Atelier 1 & 2)
# =============================================================================

# Simple dictionary to store tasks
# In Atelier 3, this will be replaced with PostgreSQL database



# =============================================================================
# FASTAPI APP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager - initialise la DB au démarrage."""
    logger.info("🚀 TaskFlow backend starting up...")
    init_db()  # Crée les tables
    logger.info("✅ Database initialized")
    yield
    logger.info("🛑 TaskFlow backend shutting down...")


app = FastAPI(
    title="TaskFlow API",
    description="Simple task management API for learning unit testing and CI/CD",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configuration CORS pour le frontend
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "Welcome to TaskFlow API",
        "version": "1.0.0",
        "docs": "/docs"
    }





@app.get("/tasks", response_model=List[Task])
async def get_tasks(
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    assignee: Optional[str] = None,
    db: Session = Depends(get_db)  # ← Toujours en dernier dans les paramètres
):
    """Get all tasks with optional filtering."""
    query = db.query(TaskModel)

    if status:
        query = query.filter(TaskModel.status == status)
    if priority:
        query = query.filter(TaskModel.priority == priority)
    if assignee:
        query = query.filter(TaskModel.assignee == assignee)

    return query.all()


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str, db: Session = Depends(get_db)) -> Task:
    """Get a single task by ID."""
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()

    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/tasks", response_model=Task, status_code=201)
async def create_task(task_data: TaskCreate, db: Session = Depends(get_db)) -> Task:
    """Create a new task."""
    # Validate title is not empty
    if not task_data.title or not task_data.title.strip():
        raise HTTPException(status_code=422, detail="Title cannot be empty")

    # Create new task with auto-generated UUID
    now = datetime.utcnow()

    task = TaskModel(
        id=str(uuid.uuid4()),
        title=task_data.title,
        description=task_data.description,
        status=task_data.status,
        priority=task_data.priority,
        assignee=task_data.assignee,
        due_date=task_data.due_date,
        created_at=now,
        updated_at=now
    )

    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info(f"Task created successfully: {task.id}")
    return task


@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: str, updates: TaskUpdate, db: Session = Depends(get_db)) -> Task:
    """Update an existing task."""
    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()

    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Apply updates
    for field, value in updates.dict(exclude_unset=True).items():
        setattr(task, field, value)

    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    logger.info(f"Task updated successfully: {task_id}")
    return task


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, db: Session = Depends(get_db)):

    task = db.query(TaskModel).filter(TaskModel.id == task_id).first()

    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    db.delete(task)
    db.commit()
    
    return None


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check with database status."""
    try:
        db.execute(text("SELECT 1"))
        tasks_count = db.query(TaskModel).count()
        return {
            "status": "healthy",
            "database": "connected",
            "tasks_count": tasks_count
        }
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)