from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
import subprocess
import threading
import uuid
import os
import time

app = FastAPI(title="Hermes Distributed Dual-Mode Cloud Worker Node")

SECRET_KEY = os.getenv("WORKER_SECRET")

# In-memory background jobs registry (holds last 100 jobs)
JOBS = {}
JOBS_LOCK = threading.Lock()

class TaskRequest(BaseModel):
    code: str

def _execute_background_task(job_id: str, code: str):
    start_time = time.time()
    try:
        # Run long background task with up to 3600s (1 hour) limit
        process = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=3600
        )
        elapsed = round(time.time() - start_time, 3)
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "completed",
                "stdout": process.stdout,
                "stderr": process.stderr,
                "exit_code": process.returncode,
                "elapsed_seconds": elapsed,
                "completed_at": time.time()
            }
    except subprocess.TimeoutExpired:
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "timeout",
                "error": "Task exceeded maximum background limit (1 hour)",
                "elapsed_seconds": 3600.0,
                "completed_at": time.time()
            }
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id] = {
                "status": "error",
                "error": str(e),
                "elapsed_seconds": round(time.time() - start_time, 3),
                "completed_at": time.time()
            }

@app.get("/")
def home():
    return {
        "status": "online",
        "role": "Hermes Dual-Mode Swarm Worker",
        "capabilities": ["sync_execute", "async_background_jobs"],
        "ready": True
    }

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": time.time()}

# 1. Direct Synchronous Execution (Fast Mode - up to 300s)
@app.post("/execute")
def execute_task(task: TaskRequest, authorization: str = Header(None)):
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: WORKER_SECRET not set")
    if authorization != f"Bearer {SECRET_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    start_time = time.time()
    try:
        process = subprocess.run(
            ["python3", "-c", task.code],
            capture_output=True,
            text=True,
            timeout=300
        )
        elapsed = round(time.time() - start_time, 3)
        return {
            "status": "success",
            "stdout": process.stdout,
            "stderr": process.stderr,
            "exit_code": process.returncode,
            "elapsed_seconds": elapsed
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "Execution exceeded 300s limit", "elapsed_seconds": 300.0}
    except Exception as e:
        return {"status": "error", "error": str(e), "elapsed_seconds": round(time.time() - start_time, 3)}

# 2. Async Background Job Submission (Unlimited Long Tasks)
@app.post("/jobs/submit")
def submit_job(task: TaskRequest, authorization: str = Header(None)):
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: WORKER_SECRET not set")
    if authorization != f"Bearer {SECRET_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "submitted_at": time.time(),
            "stdout": None,
            "stderr": None
        }
    
    thread = threading.Thread(target=_execute_background_task, args=(job_id, task.code), daemon=True)
    thread.start()
    
    return {
        "status": "submitted",
        "job_id": job_id,
        "message": "Background job spawned successfully. Poll /jobs/{job_id} for output."
    }

# 3. Check Async Background Job Status
@app.get("/jobs/{job_id}")
def get_job_status(job_id: str, authorization: str = Header(None)):
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: WORKER_SECRET not set")
    if authorization != f"Bearer {SECRET_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    with JOBS_LOCK:
        if job_id not in JOBS:
            raise HTTPException(status_code=404, detail="Job ID not found")
        return JOBS[job_id]