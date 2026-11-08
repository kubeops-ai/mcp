# KubeOps MCP Server

This repository contains the MCP server for KubeOps.

## Run locally

Create a virtual environment, install the dependencies, and start the server:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python .\server.py
```

The Streamable HTTP MCP endpoint is available at:

```text
http://127.0.0.1:8000/mcp
```

The server currently exposes the `ping` tool and the read-only Insight tools:

- `list_namespaces`
- `list_pods`
- `list_deployments`
- `list_services`
- `list_nodes`
- `get_pod_logs`
- `get_pod_events`
- `diagnose_pod`

All Kubernetes calls use the fixed Developer kubeconfig:

```text
~/.kube/k8s-developer.conf
```

The development server listens only on `127.0.0.1` until HTTP authentication
is added for remote deployment.

`diagnose_pod` uses the separate admin kubeconfig:

```text
~/.kube/k8s-admin.conf
```
