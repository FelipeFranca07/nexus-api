import os
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

APP_VERSION = os.getenv("APP_VERSION", "dev")

app = FastAPI(title="TaskFlow API", version=APP_VERSION)


class TaskIn(BaseModel):
    title: str
    done: bool = False


class Task(TaskIn):
    id: str


_tasks: dict[str, Task] = {}


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.get("/tasks", response_model=list[Task])
def list_tasks():
    return list(_tasks.values())


@app.post("/tasks", response_model=Task, status_code=201)
def create_task(task: TaskIn):
    task_id = str(uuid.uuid4())
    stored = Task(id=task_id, **task.model_dump())
    _tasks[task_id] = stored
    return stored


@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    del _tasks[task_id]
