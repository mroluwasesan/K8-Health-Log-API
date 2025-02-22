from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from pydantic import BaseModel
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List, Dict, Any
import httpx
import logging
import os
from string import Template
import uuid

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
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

# In-memory store for active monitoring tasks
active_tasks = {}

# Serve the logo
@app.get("/logo")
async def get_logo():
    return FileResponse("uptime.png")

# Integration JSON Endpoint
@app.get("/api/integration.json")
async def get_integration_json(request: Request):
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
            "key_features": ["Real-time Kubernetes error monitoring"],
            "author": "Rotimi Oluwasesan",
            "settings": [
                {
                    "label": "namespace",
                    "type": "text",
                    "required": True,
                    "default": "default",
                    "description": "Kubernetes namespace to monitor"
                },
                {
                    "label": "cluster_server",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "Kubernetes API server URL (e.g. https://api.cluster.local:6443)"
                },
                {
                    "label": "cluster_name",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "Kubernetes cluster name"
                },
                {
                    "label": "ca_cert",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "Base64-encoded cluster CA certificate"
                },
                {
                    "label": "service_account_token",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "Service account token for API access"
                },
                {
                    "label": "interval",
                    "type": "dropdown",
                    "options": ["1", "5", "10", "15", "30", "60"],
                    "required": True,
                    "default": "5",
                    "description": "Check interval in minutes"
                }
            ],
            "target_url": f"{base_url}/api/target",
            "tick_url": f"{base_url}/api/tick"
        }
    }

def generate_kubeconfig(settings: dict) -> str:
    required_fields = ['cluster_server', 'cluster_name', 'ca_cert', 'service_account_token', 'namespace']
    missing = [field for field in required_fields if not settings.get(field)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    template_path = "kubeconfig_template.yaml"
    if not os.path.exists(template_path):
        logger.error("Kubeconfig template not found")
        raise HTTPException(status_code=500, detail="Kubeconfig template missing")

    try:
        with open(template_path, "r") as f:
            template = Template(f.read())
        
        context_name = f"{settings['namespace']}-context"
        kubeconfig_content = template.substitute(
            CLUSTER_NAME=settings['cluster_name'],
            CLUSTER_SERVER=settings['cluster_server'],
            CLUSTER_CA=settings['ca_cert'],
            TOKEN=settings['service_account_token'],
            NAMESPACE=settings['namespace'],
            CONTEXT_NAME=context_name
        )

        kubeconfig_path = f"/tmp/kubeconfig-{uuid.uuid4()}.yaml"
        with open(kubeconfig_path, "w") as f:
            f.write(kubeconfig_content)
        
        logger.info(f"Generated kubeconfig at {kubeconfig_path}")
        return kubeconfig_path

    except Exception as e:
        logger.error(f"Kubeconfig generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Kubeconfig generation failed")

async def fetch_error_logs(namespace: str) -> List[Dict[str, Any]]:
    try:
        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod(namespace)
        errors = []

        for pod in pods.items:
            pod_name = pod.metadata.name
            try:
                logs = v1.read_namespaced_pod_log(
                    pod_name,
                    namespace,
                    tail_lines=100,
                    timestamps=True
                )
                error_lines = [
                    line for line in logs.split('\n') 
                    if any(keyword in line.lower() for keyword in ['error', 'exception', 'fail'])
                ]
                if error_lines:
                    errors.append({
                        "pod": pod_name,
                        "errors": error_lines[-5:],  # Last 5 error lines
                        "status": pod.status.phase,
                        "restarts": sum(container.restart_count for container in pod.status.container_statuses)
                    })
            except ApiException as e:
                logger.warning(f"Failed to get logs for {pod_name}: {str(e)}")
        
        return errors

    except ApiException as e:
        logger.error(f"Kubernetes API error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to access Kubernetes API")

async def send_to_telex(return_url: str, message: dict):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(return_url, json=message)
            response.raise_for_status()
            logger.info(f"Successfully sent to Telex: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to send to Telex: {str(e)}")

async def monitoring_worker(task_id: str, payload: MonitorPayload):
    try:
        logger.info(f"Starting monitoring task {task_id}")
        settings = {s.label: s.default for s in payload.settings}
        
        # Generate kubeconfig
        kubeconfig_path = generate_kubeconfig(settings)
        
        # Load configuration
        config.load_kube_config(config_file=kubeconfig_path)
        
        # Fetch logs
        errors = await fetch_error_logs(settings['namespace'])
        
        # Prepare response
        status = "error" if errors else "success"
        message = {
            "status": status,
            "message": f"Found {len(errors)} pods with errors" if errors else "No errors detected",
            "details": errors if errors else None,
            "channel_id": payload.channel_id
        }

        # Send response to Telex
        await send_to_telex(payload.return_url, message)

    except Exception as e:
        logger.error(f"Monitoring task failed: {str(e)}")
    finally:
        # Clean up task
        if task_id in active_tasks:
            del active_tasks[task_id]
        # Clean up kubeconfig
        if os.path.exists(kubeconfig_path):
            os.remove(kubeconfig_path)

@app.post("/api/tick", status_code=202)
async def handle_tick(payload: MonitorPayload, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    active_tasks[task_id] = {
        "status": "started",
        "started_at": datetime.now().isoformat()
    }
    
    background_tasks.add_task(monitoring_worker, task_id, payload)
    
    return {
        "status": "accepted",
        "task_id": task_id,
        "message": "Monitoring task started successfully"
    }

@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    return active_tasks.get(task_id, {"status": "not_found"})

@app.post("/test-webhook")
async def test_webhook(request: Request):
    data = await request.json()
    logger.info(f"Received test webhook: {data}")
    return {"status": "received"}