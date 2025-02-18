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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://staging.telextest.im", "http://telextest.im", "https://staging.telex.im", "https://telex.im"], # NB: telextest is a local url
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],
)

@app.get("/logo")
def get_logo():
    return FileResponse("uptime.png")

# Integration JSON Endpoint
@app.get("/api/integration.json")
def get_integration_json(request: Request):
    base_url = str(request.base_url).rstrip("/")
    if base_url.endswith("//"):
        base_url = base_url.rstrip("/")  # Remove trailing slashes
    base_url = base_url.replace("///", "//")
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
            "integration_category": "Monitoring & Logging",
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
                    "label": "api_server_port",
                    "type": "text",
                    "required": True,
                    "default": "6443",
                    "description": "The port of the Kubernetes API server."
                },
                {
                    "label": "ca_cert",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "The base64-encoded CA certificate for the Kubernetes cluster."
                },
                {
                    "label": "service_account_token",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "The service account token for authenticating with the Kubernetes API server."
                }
            ],

            "target_url": f"{base_url}/api/target",
            "tick_url": f"{base_url}/api/tick"
        }
    }


# Function to generate kubeconfig
def generate_kubeconfig(api_server_ip: str, api_server_port: str, ca_cert: str, service_account_token: str) -> str:
    kubeconfig = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": "my-cluster",
                "cluster": {
                    "server": f"https://{api_server_ip}:{api_server_port}",
                    "certificate-authority-data": ca_cert
                }
            }
        ],
        "users": [
            {
                "name": "k8s-monitor",
                "user": {
                    "token": service_account_token
                }
            }
        ],
        "contexts": [
            {
                "name": "my-context",
                "context": {
                    "cluster": "my-cluster",
                    "user": "k8s-monitor"
                }
            }
        ],
        "current-context": "my-context"
    }

    # Save kubeconfig to a file
    kubeconfig_path = "/tmp/kubeconfig.yaml"
    with open(kubeconfig_path, "w") as f:
        yaml.dump(kubeconfig, f)

    return kubeconfig_path

# Function to fetch pod logs and check for errors
def fetch_error_logs(namespace: str) -> List[Dict[str, Any]]:
    v1 = client.CoreV1Api()
    error_reports = []

    try:
        # Fetch all pods in the specified namespace
        pods = v1.list_namespaced_pod(namespace)
        for pod in pods.items:
            pod_name = pod.metadata.name

            # Fetch logs for the pod
            logs = []
            try:
                pod_logs = v1.read_namespaced_pod_log(pod_name, namespace)
                logs = pod_logs.split("\n")
            except ApiException as e:
                logs = [f"Failed to fetch logs: {str(e)}"]

            # Check for errors in logs
            error_logs = [log for log in logs if "error" in log.lower()]
            if error_logs:
                error_reports.append({
                    "pod_name": pod_name,
                    "namespace": namespace,
                    "logs": error_logs
                })
    except ApiException as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pod logs: {str(e)}")

    return error_reports

# Background task to monitor Kubernetes logs
async def monitor_task(payload: MonitorPayload):
    # Extract settings
    settings = {s.label: s.default for s in payload.settings}
    namespace = settings.get("namespace", "default")
    api_server_ip = settings.get("api_server_ip")
    api_server_port = settings.get("api_server_port", "6443")
    ca_cert = settings.get("ca_cert")
    service_account_token = settings.get("service_account_token")

    # Generate kubeconfig
    kubeconfig_path = generate_kubeconfig(api_server_ip, api_server_port, ca_cert, service_account_token)

    # Load kubeconfig
    try:
        config.load_kube_config(config_file=kubeconfig_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load kubeconfig: {str(e)}")

    # Fetch error logs
    error_reports = fetch_error_logs(namespace)

    # Prepare message for Telex
    if error_reports:
        message = "\n".join([
            f"Pod: {report['pod_name']}, Namespace: {report['namespace']}\n" +
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

# Tick Endpoint
@app.post("/api/tick", status_code=202)
def monitor(payload: MonitorPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(monitor_task, payload)
    return {"status": "accepted"}


