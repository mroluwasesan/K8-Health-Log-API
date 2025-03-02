from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from pydantic import BaseModel
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List, Dict, Any, ContextManager
from contextlib import contextmanager
import tempfile
import httpx
import yaml
import logging
import os
from string import Template

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

REQUIRED_K8S_SETTINGS = [
    "cluster_name",
    "api_server_url",
    "ca_cert",
    "service_account_token",
    "namespace",
    "api_server_ip",
]

@contextmanager
def temp_kubeconfig() -> ContextManager[str]:
    """Context manager for temporary kubeconfig file in current directory."""
    tmp = tempfile.NamedTemporaryFile(
        prefix='kubeconfig_',
        suffix='.yaml',
        dir=os.getcwd(),
        delete=False
    )
    try:
        yield tmp.name
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)

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
                    "label": "cluster_name",
                    "type": "text",
                    "required": True,
                    "default": "kubernetes",
                    "description": "The name of the Kubernetes cluster"
                },
                {
                    "label": "api_server_url",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "The Kubernetes API Server URL (e.g., https://api.cluster.com:6443)"
                },
                {
                    "label": "ca_cert",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "The base64-encoded cluster CA certificate"
                },
                {
                    "label": "service_account_token",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "The service account token for authentication"
                },
                {
                    "label": "namespace",
                    "type": "text",
                    "required": True,
                    "default": "default",
                    "description": "The target Kubernetes namespace to monitor"
                },
                {
                    "label": "user_name",
                    "type": "text",
                    "required": False,
                    "default": "k8s-monitor",
                    "description": "The name of the service account"
                },
                {
                    "label": "interval",
                    "type": "dropdown",
                    "options": ["1", "5", "10", "15", "30", "60"],
                    "required": True,
                    "default": "5",
                    "description": "Interval (in minutes) at which logs are checked"
                }
            ],
            "target_url": f"{base_url}/api/target",
            "tick_url": f"{base_url}/api/tick"
        }
    }

# Function to generate kubeconfig
def generate_kubeconfig(
    api_server_url: str,
    ca_cert: str,
    service_account_token: str,
    cluster_name: str,
    username: str,
    namespace: str
) -> str:
    # Load the kubeconfig template
    try:
        with open("kubeconfig_template.yaml", "r") as file:
            template = Template(file.read())
    except FileNotFoundError:
        logger.error("kubeconfig_template.yaml not found. Ensure the file exists in the project directory.")
        raise HTTPException(status_code=500, detail="kubeconfig_template.yaml not found.")

    # Populate the template with user input
    kubeconfig_content = template.substitute(
        cluster_name=cluster_name,
        api_server_url=api_server_url,
        ca_cert=ca_cert,
        user_name=username,
        service_account_token=service_account_token,
        namespace=namespace
    )

    # Use context manager to handle the temporary file
    with temp_kubeconfig() as kubeconfig_path:
        try:
            with open(kubeconfig_path, "w") as file:
                file.write(kubeconfig_content)
            logger.info(f"Kubeconfig saved to: {kubeconfig_path}")
            
            # Export the KUBECONFIG environment variable
            os.environ["KUBECONFIG"] = kubeconfig_path
            logger.info(f"KUBECONFIG environment variable set to: {kubeconfig_path}")
            
            return kubeconfig_path
        except Exception as e:
            logger.error(f"Failed to write kubeconfig: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to write kubeconfig: {str(e)}")

# Function to fetch pod logs and check for errors
def fetch_error_logs(namespace: str) -> List[Dict[str, Any]]:
    v1 = client.CoreV1Api()
    error_reports = []

    try:
        # Fetch all pods in the specified namespace
        pods = v1.list_namespaced_pod(namespace)
        for pod in pods.items:
            pod_name = pod.metadata.name

            try:
                # Enhanced log fetching with more options
                pod_logs = v1.read_namespaced_pod_log(
                    pod_name, 
                    namespace,
                    tail_lines=1000,  # Get last 1000 lines
                    timestamps=True,   # Include timestamps
                    previous=False     # Current container logs
                )
                logs = pod_logs.split("\n")

                # Enhanced error detection
                error_logs = []
                for i, log in enumerate(logs):
                    # Check for various error indicators
                    if any(indicator in log.lower() for indicator in [
                        "error",
                        "exception",
                        "fail",
                        "fatal",
                        "panic",
                        "critical"
                    ]):
                        # Include context (2 lines before and after)
                        start_idx = max(0, i - 2)
                        end_idx = min(len(logs), i + 3)
                        context_logs = logs[start_idx:end_idx]
                        error_logs.extend(context_logs)
                        error_logs.append("---")  # Separator

                if error_logs:
                    error_reports.append({
                        "pod_name": pod_name,
                        "namespace": namespace,
                        "logs": error_logs,
                        "status": pod.status.phase,
                        "container_statuses": [
                            {
                                "name": status.name,
                                "ready": status.ready,
                                "restart_count": status.restart_count,
                                "state": str(status.state)
                            }
                            for status in (pod.status.container_statuses or [])
                        ]
                    })

            except ApiException as e:
                error_reports.append({
                    "pod_name": pod_name,
                    "namespace": namespace,
                    "error": f"Failed to fetch logs: {str(e)}",
                    "status": pod.status.phase
                })

    except ApiException as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch pod logs in namespace {namespace}: {str(e)}"
        )

    return error_reports

# Background task to monitor Kubernetes logs
async def monitor_task(payload: MonitorPayload):
    kubeconfig_path = None
    try:
        # Extract settings
        settings = {s.label: s.default for s in payload.settings}
        logger.info(f"Settings received: {settings}")

        # Extract all required fields
        cluster_name = settings.get("cluster_name")
        api_server_url = settings.get("api_server_url")
        ca_cert = settings.get("ca_cert")
        service_account_token = settings.get("service_account_token")
        namespace = settings.get("namespace", "default")
        user_name = settings.get("user_name", "k8s-monitor")

        # Validate required settings
        missing = [field for field in REQUIRED_K8S_SETTINGS if not settings.get(field)]
        if missing:
            logger.error(f"Missing required Kubernetes settings: {missing}")
            raise HTTPException(
                status_code=400,
                detail=f"Missing required settings: {', '.join(missing)}"
            )

        # Generate kubeconfig in the current directory
        kubeconfig_path = generate_kubeconfig(
            api_server_url=api_server_url,
            ca_cert=ca_cert,
            service_account_token=service_account_token,
            cluster_name=cluster_name,
            username=user_name,
            namespace=namespace
        )

        # Load kubeconfig
        config.load_kube_config(config_file=kubeconfig_path)

        # Fetch error logs
        error_reports = fetch_error_logs(namespace)
        logger.info(f"Error reports: {error_reports}")

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
            logger.info(f"Data sent to Telex: {data}")

    except Exception as e:
        logger.error(f"Error in monitor_task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Tick Endpoint
@app.post("/api/tick", status_code=202)
def monitor(payload: MonitorPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(monitor_task, payload)
    return {"status": "accepted"}

@app.post("/test-webhook")
async def test_webhook(request: Request):
    data = await request.json()
    print("Received webhook data:", data)
    return {"status": "received"}

