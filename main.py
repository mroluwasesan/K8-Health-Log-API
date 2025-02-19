# from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
# from pydantic import BaseModel
# from kubernetes import client, config
# from kubernetes.client.rest import ApiException
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import FileResponse
# from typing import List, Dict, Any
# import httpx
# import yaml
# import logging
# import os
# from string import Template

# # Set up logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# app = FastAPI()

# # Define models
# class Setting(BaseModel):
#     label: str
#     type: str
#     required: bool
#     default: str

# class MonitorPayload(BaseModel):
#     channel_id: str
#     return_url: str
#     settings: List[Setting]

# # Add CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://staging.telextest.im", "http://telextest.im", "https://staging.telex.im", "https://telex.im"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Serve the logo
# @app.get("/logo")
# def get_logo():
#     return FileResponse("uptime.png")

# # Integration JSON Endpoint
# @app.get("/api/integration.json")
# def get_integration_json(request: Request):
#     base_url = str(request.base_url).rstrip("/")
#     return {
#         "data": {
#             "date": {
#                 "created_at": "2025-02-17",
#                 "updated_at": "2025-02-17"
#             },
#             "descriptions": {
#                 "app_name": "K8s Health Monitor",
#                 "app_description": "Monitors Kubernetes pod logs for errors.",
#                 "app_url": base_url,
#                 "app_logo": "https://i.imgur.com/lZqvffp.png",
#                 "background_color": "#fff"
#             },
#             "integration_category": "Monitoring & Logging",
#             "integration_type": "interval",
#             "key_features": ["- monitors kubernetes"],
#             "author": "Rotimi Oluwasesan",
#             "settings": [
#                 {
#                     "label": "namespace",
#                     "type": "text",
#                     "required": True,
#                     "default": "default",
#                     "description": "The Kubernetes namespace to monitor. (kubectl get namespaces)"
#                 },
#                 {
#                     "label": "interval",
#                     "type": "dropdown",
#                     "options": ["1", "5", "10", "15", "30", "60"],
#                     "required": True,
#                     "default": "5",
#                     "description": "Interval (in minutes) at which logs are checked."
#                 },
#                 {
#                     "label": "api_server_ip",
#                     "type": "text",
#                     "required": True,
#                     "default": "",
#                     "description": "The IP address of the Kubernetes API server. (kubectl get svc -n default)"
#                 },
#                 {
#                     "label": "api_server_port",
#                     "type": "text",
#                     "required": True,
#                     "default": "6443",
#                     "description": "The port of the Kubernetes API server. (kubectl get svc -n default)"
#                 },
#                 {
#                     "label": "ca_cert",
#                     "type": "text",
#                     "required": True,
#                     "default": "",
#                     "description": "The base64-encoded CA certificate for the Kubernetes cluster. (kubectl config view --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"
#                 },
#                 {
#                     "label": "service_account_token",
#                     "type": "text",
#                     "required": True,
#                     "default": "",
#                     "description": "The service account token for authenticating with the Kubernetes API server. (kubectl get secrets -o jsonpath='{.items[?(@.metadata.annotations[\"kubernetes.io/service-account.name\"]==\"default\")].data.token}' | base64 --decode)"
#                 },
#                 {
#                     "label": "cluster_name",
#                     "type": "text",
#                     "required": True,
#                     "default": "kubernetes",
#                     "description": "The name of the Kubernetes cluster in the kubeconfig. (kubectl config get-clusters)"
#                 },
#                 {
#                     "label": "user_name",
#                     "type": "text",
#                     "required": True,
#                     "default": "k8s-monitor",
#                     "description": "The name of the user in the kubeconfig. (kubectl config get-users)"
#                 }
#             ],
#             "target_url": f"{base_url}/api/target",
#             "tick_url": f"{base_url}/api/tick"
#         }
#     }

# # Function to generate kubeconfig
# def generate_kubeconfig(
#     api_server_ip: str,
#     api_server_port: str,
#     ca_cert: str,
#     service_account_token: str,
#     cluster_name: str,
#     user_name: str,
# ) -> str:
#     # Load the kubeconfig template
#     with open("kubeconfig_template.yaml", "r") as file:
#         template = Template(file.read())

#     # Populate the template with user input
#     kubeconfig_content = template.substitute(
#         cluster_name=cluster_name,
#         api_server_ip=api_server_ip,
#         api_server_port=api_server_port,
#         ca_cert=ca_cert,
#         user_name=user_name,
#         service_account_token=service_account_token,
#     )

#     # Save the populated kubeconfig to a file
#     kubeconfig_path = "/tmp/kubeconfig.yaml"
#     with open(kubeconfig_path, "w") as file:
#         file.write(kubeconfig_content)

#     # Export the KUBECONFIG environment variable
#     os.environ["KUBECONFIG"] = kubeconfig_path

#     return kubeconfig_path

# # Function to fetch pod logs and check for errors
# def fetch_error_logs(namespace: str) -> List[Dict[str, Any]]:
#     v1 = client.CoreV1Api()
#     error_reports = []

#     try:
#         # Fetch all pods in the specified namespace
#         pods = v1.list_namespaced_pod(namespace)
#         for pod in pods.items:
#             pod_name = pod.metadata.name

#             # Fetch logs for the pod
#             logs = []
#             try:
#                 pod_logs = v1.read_namespaced_pod_log(pod_name, namespace)
#                 logs = pod_logs.split("\n")
#             except ApiException as e:
#                 logs = [f"Failed to fetch logs: {str(e)}"]

#             # Check for errors in logs
#             error_logs = [log for log in logs if "error" in log.lower()]
#             if error_logs:
#                 error_reports.append({
#                     "pod_name": pod_name,
#                     "namespace": namespace,
#                     "logs": error_logs
#                 })
#     except ApiException as e:
#         raise HTTPException(status_code=500, detail=f"Failed to fetch pod logs: {str(e)}")

#     return error_reports

# # Background task to monitor Kubernetes logs
# async def monitor_task(payload: MonitorPayload):
#     try:
#         # Extract settings
#         settings = {s.label: s.default for s in payload.settings}
#         logger.info(f"Settings received: {settings}")

#         namespace = settings.get("namespace", "default")
#         api_server_ip = settings.get("api_server_ip")
#         api_server_port = settings.get("api_server_port", "6443")
#         ca_cert = settings.get("ca_cert")
#         service_account_token = settings.get("service_account_token")
#         cluster_name = settings.get("cluster_name", "kubernetes")
#         user_name = settings.get("user_name", "k8s-monitor")

#         # Validate required settings
#         if not api_server_ip or not ca_cert or not service_account_token:
#             raise HTTPException(status_code=400, detail="Missing required settings: api_server_ip, ca_cert, or service_account_token")

#         # Generate kubeconfig
#         kubeconfig_path = generate_kubeconfig(
#             api_server_ip,
#             api_server_port,
#             ca_cert,
#             service_account_token,
#             cluster_name,
#             user_name,
#         )
#         logger.info(f"Kubeconfig generated at: {kubeconfig_path}")

#         # Load kubeconfig
#         try:
#             config.load_kube_config(config_file=kubeconfig_path)
#         except Exception as e:
#             raise HTTPException(status_code=500, detail=f"Failed to load kubeconfig: {str(e)}")

#         # Fetch error logs
#         error_reports = fetch_error_logs(namespace)
#         logger.info(f"Error reports: {error_reports}")

#         # Prepare message for Telex
#         if error_reports:
#             message = "\n".join([
#                 f"Pod: {report['pod_name']}, Namespace: {report['namespace']}\n" +
#                 "\n".join(report['logs'])
#                 for report in error_reports
#             ])
#         else:
#             message = "No errors found in Kubernetes logs."

#         # Data follows Telex webhook format
#         data = {
#             "message": message,
#             "username": "K8s Health Monitor",
#             "event_name": "K8s Error Report",
#             "status": "error" if error_reports else "success"
#         }

#         # Send data to Telex
#         async with httpx.AsyncClient() as client:
#             await client.post(payload.return_url, json=data)
#             logger.info(f"Data sent to Telex: {data}")

#     except Exception as e:
#         logger.error(f"Error in monitor_task: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))

# # Tick Endpoint
# @app.post("/api/tick", status_code=202)
# def monitor(payload: MonitorPayload, background_tasks: BackgroundTasks):
#     background_tasks.add_task(monitor_task, payload)
#     return {"status": "accepted"}






from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from pydantic import BaseModel
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List, Dict, Any
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
                    "description": "The Kubernetes namespace to monitor. (kubectl get namespaces)"
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
                    "description": "The IP address of the Kubernetes API server. (kubectl get svc -n default)"
                },
                {
                    "label": "api_server_port",
                    "type": "text",
                    "required": True,
                    "default": "6443",
                    "description": "The port of the Kubernetes API server. (kubectl get svc -n default)"
                },
                {
                    "label": "ca_cert",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "The base64-encoded CA certificate for the Kubernetes cluster. (kubectl config view --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"
                },
                {
                    "label": "service_account_token",
                    "type": "text",
                    "required": True,
                    "default": "",
                    "description": "The service account token for authenticating with the Kubernetes API server. (kubectl get secrets -o jsonpath='{.items[?(@.metadata.annotations[\"kubernetes.io/service-account.name\"]==\"default\")].data.token}' | base64 --decode)"
                },
                {
                    "label": "cluster_name",
                    "type": "text",
                    "required": True,
                    "default": "kubernetes",
                    "description": "The name of the Kubernetes cluster in the kubeconfig. (kubectl config get-clusters)"
                },
                {
                    "label": "user_name",
                    "type": "text",
                    "required": True,
                    "default": "k8s-monitor",
                    "description": "The name of the user in the kubeconfig. (kubectl config get-users)"
                }
            ],
            "target_url": f"{base_url}/api/target",
            "tick_url": f"{base_url}/api/tick"
        }
    }

# Function to generate kubeconfig
def generate_kubeconfig(
    api_server_ip: str,
    api_server_port: str,
    ca_cert: str,
    service_account_token: str,
    cluster_name: str,
    user_name: str,
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
        api_server_ip=api_server_ip,
        api_server_port=api_server_port,
        ca_cert=ca_cert,
        user_name=user_name,
        service_account_token=service_account_token,
    )

    # Save the populated kubeconfig to a temporary file
    kubeconfig_path = "/tmp/kubeconfig.yaml"
    try:
        with open(kubeconfig_path, "w") as file:
            file.write(kubeconfig_content)
        logger.info(f"Kubeconfig saved to: {kubeconfig_path}")
    except Exception as e:
        logger.error(f"Failed to write kubeconfig to {kubeconfig_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to write kubeconfig: {str(e)}")

    # Export the KUBECONFIG environment variable
    os.environ["KUBECONFIG"] = kubeconfig_path
    logger.info(f"KUBECONFIG environment variable set to: {kubeconfig_path}")

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
    try:
        # Extract settings
        settings = {s.label: s.default for s in payload.settings}
        logger.info(f"Settings received: {settings}")

        namespace = settings.get("namespace", "default")
        api_server_ip = settings.get("api_server_ip")
        api_server_port = settings.get("api_server_port", "6443")
        ca_cert = settings.get("ca_cert")
        service_account_token = settings.get("service_account_token")
        cluster_name = settings.get("cluster_name", "kubernetes")
        user_name = settings.get("user_name", "k8s-monitor")

        # Validate required settings
        if not api_server_ip or not ca_cert or not service_account_token:
            raise HTTPException(status_code=400, detail="Missing required settings: api_server_ip, ca_cert, or service_account_token")

        # Generate kubeconfig
        kubeconfig_path = generate_kubeconfig(
            api_server_ip,
            api_server_port,
            ca_cert,
            service_account_token,
            cluster_name,
            user_name,
        )
        logger.info(f"Kubeconfig generated at: {kubeconfig_path}")

        # Load kubeconfig
        try:
            config.load_kube_config(config_file=kubeconfig_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load kubeconfig: {str(e)}")

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