from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import subprocess
import os
import time

app = FastAPI(title="Hermes Remote Worker Node")

# Secret key is strictly read from environment variable (Never hardcoded)
SECRET_KEY = os.getenv("WORKER_SECRET")

class TaskRequest(BaseModel):
    code: str

@app.get("/")
def home():
    return {"status": "online", "role": "Hermes Swarm Worker", "ready": True}

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": time.time()}

@app.post("/execute")
def execute_task(task: TaskRequest, authorization: str = Header(None)):
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: WORKER_SECRET not set in environment")
        
    if authorization != f"Bearer {SECRET_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid Secret Key")
    
    start_time = time.time()
    try:
        # Run the task with Python 3 (120s extended execution limit)
        process = subprocess.run(
            ["python3", "-c", task.code],
            capture_output=True,
            text=True,
            timeout=120
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
        return {
            "status": "timeout",
            "error": "Execution exceeded 120s limit",
            "elapsed_seconds": 120.0
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "elapsed_seconds": round(time.time() - start_time, 3)
        }