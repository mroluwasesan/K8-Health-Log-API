


from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from pydantic import BaseModel
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List, Dict, Any
import httpx
import os
import yaml
import logging
import subprocess

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Define models
class Setting(BaseModel):
    label: str
    type: str
    required: bool
    default: str

class MonitorPayload(BaseModel):
    channel_id: str
    return_url: str
    settings: List[Setting]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://staging.telextest.im", "http://telextest.im", "https://staging.telex.im", "https://telex.im"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the logo
@app.get("/logo")
def get_logo():
    return FileResponse("uptime.png")

# Integration JSON Endpoint
@app.get("/api/integration.json")
def get_integration_json(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return {
        "data": {
            "date": {
                "created_at": "2025-02-17",
                "updated_at": "2025-02-17"
            },
            "descriptions": {
                "app_name": "K8s Health Monitor",
                "app_description": "Monitors Kubernetes pod logs for errors.",
                "app_url": base_url,
                "app_logo": "https://i.imgur.com/lZqvffp.png",
                "background_color": "#fff"
            },
            "integration_category": "Monitoring & Logging",
            "integration_type": "interval",
            "key_features": ["- monitors kubernetes"],
            "author": "Rotimi Oluwasesan",
            "settings": [
                {
                    "label": "namespace",
                    "type": "text",
                    "required": True,
                    "default": "default",
                    "description": "The Kubernetes namespace to monitor."
                },
                {
                    "label": "interval",
                    "type": "dropdown",
                    "options": ["1", "5", "10", "15", "30", "60"],
                    "required": True,
                    "default": "5",
                    "description": "Interval (in minutes) at which logs are checked."
                },
                {
                    "label": "api_server_ip",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "The IP address of the Kubernetes API server."
                },
                {
                    "label": "ssh_username",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "The SSH username for the Kubernetes server."
                },
                {
                    "label": "ssh_password",
                    "type": "password",
                    "required": True,
                    "default": "",
                    "description": "The SSH password for the Kubernetes server."
                },
                {
                    "label": "ssh_port",
                    "type": "text",
                    "required": False,
                    "default": "22",
                    "description": "The SSH port for the Kubernetes server."
                }
            ],
            "target_url": f"{base_url}/api/target",
            "tick_url": f"{base_url}/api/tick"
        }
    }

# Function to fetch error logs using SSH
def fetch_error_logs_ssh(
    server_ip: str,
    ssh_username: str,
    ssh_password: str,
    ssh_port: str,
    namespace: str,
) -> List[Dict[str, Any]]:
    # Define the error pattern
    ERROR_PATTERN = "Error|Failed|CrashLoopBackOff"

    # Define the SSH command
    ssh_command = f"""
    kubectl get pods -n {namespace} --no-headers -o custom-columns=":metadata.name" | while read POD; do
        kubectl logs "\$POD" -n {namespace} 2>&1
    done | grep -E "{ERROR_PATTERN}"
    """

    # Use sshpass to execute the command remotely
    command = [
        "sshpass",
        "-p", ssh_password,
        "ssh",
        "-p", ssh_port,
        "-o", "LogLevel=ERROR",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "StrictHostKeyChecking=no",
        f"{ssh_username}@{server_ip}",
        ssh_command
    ]

    try:
        # Execute the command and capture the output
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        logs = result.stdout.splitlines()

        # Format the logs into a list of dictionaries
        error_reports = []
        if logs:
            error_reports.append({
                "namespace": namespace,
                "logs": logs
            })

        return error_reports

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch logs via SSH: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs via SSH: {str(e)}")

# Background task to monitor Kubernetes logs
async def monitor_task(payload: MonitorPayload):
    try:
        # Extract settings
        settings = {s.label: s.default for s in payload.settings}
        logger.info(f"Settings received: {settings}")

        namespace = settings.get("namespace", "default")
        api_server_ip = settings.get("api_server_ip")
        ssh_username = settings.get("ssh_username")
        ssh_password = settings.get("ssh_password")
        ssh_port = settings.get("ssh_port", "22")

        # Validate required settings
        if not api_server_ip or not ssh_username or not ssh_password:
            raise HTTPException(status_code=400, detail="Missing required settings: api_server_ip, ssh_username, or ssh_password")

        # Fetch error logs using SSH
        error_reports = fetch_error_logs_ssh(api_server_ip, ssh_username, ssh_password, ssh_port, namespace)
        logger.info(f"Error reports: {error_reports}")

        # Prepare message for Telex
        if error_reports:
            message = "\n".join([
                f"Namespace: {report['namespace']}\n" +
                "\n".join(report['logs'])
                for report in error_reports
            ])
        else:
            message = "No errors found in Kubernetes logs."

        # Data follows Telex webhook format
        data = {
            "message": message,
            "username": "K8s Health Monitor",
            "event_name": "K8s Error Report",
            "status": "error" if error_reports else "success"
        }

        # Send data to Telex
        async with httpx.AsyncClient() as client:
            await client.post(payload.return_url, json=data)
            logger.info(f"Data sent to Telex: {data}")

    except Exception as e:
        logger.error(f"Error in monitor_task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Tick Endpoint
@app.post("/api/tick", status_code=202)
def monitor(payload: MonitorPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(monitor_task, payload)
    return {"status": "accepted"}