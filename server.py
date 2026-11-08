"""KubeOps MCP server entry point for read-only Insight operations."""

import logging
from pathlib import Path

from kubernetes import client, config
from mcp.server.mcpserver import MCPServer


mcp = MCPServer("KubeOps MCP Server")
DEVELOPER_KUBECONFIG = Path.home() / ".kube" / "k8s-developer.conf"
ADMIN_KUBECONFIG = Path.home() / ".kube" / "k8s-admin.conf"
MAX_POD_EVENTS = 10
logger = logging.getLogger("kubeops.mcp")


def open_developer_client():
    """Open Kubernetes using the fixed read-only Developer kubeconfig."""
    logger.info("Opening Kubernetes client with the Developer kubeconfig.")
    return config.new_client_from_config(
        config_file=str(DEVELOPER_KUBECONFIG), persist_config=False
    )


def open_admin_client():
    """Open Kubernetes using the fixed admin kubeconfig for diagnosis."""
    logger.info("Opening Kubernetes client with the admin kubeconfig.")
    return config.new_client_from_config(
        config_file=str(ADMIN_KUBECONFIG), persist_config=False
    )


@mcp.tool()
def ping(message: str = "KubeOps MCP server is running") -> str:
    """Return a simple response to verify that the MCP server is reachable."""
    return message


@mcp.tool()
def list_namespaces() -> list[str]:
    """List all namespace names in the live Kubernetes cluster."""
    with open_developer_client() as api_client:
        logger.info("Kubernetes SDK: list namespaces.")
        namespaces = client.CoreV1Api(api_client).list_namespace(_request_timeout=10)
    return sorted(namespace.metadata.name for namespace in namespaces.items)


@mcp.tool()
def list_pods(namespace: str = "default") -> list[str]:
    """List pod names in one namespace. If omitted, use default."""
    namespace = namespace.strip() or "default"
    with open_developer_client() as api_client:
        logger.info("Kubernetes SDK: list pods in namespace %s.", namespace)
        pods = client.CoreV1Api(api_client).list_namespaced_pod(
            namespace=namespace, _request_timeout=10
        )
    return sorted(pod.metadata.name for pod in pods.items)


@mcp.tool()
def list_deployments(namespace: str = "default") -> list[str]:
    """List deployment names in one namespace. If omitted, use default."""
    namespace = namespace.strip() or "default"
    with open_developer_client() as api_client:
        logger.info("Kubernetes SDK: list deployments in namespace %s.", namespace)
        deployments = client.AppsV1Api(api_client).list_namespaced_deployment(
            namespace=namespace, _request_timeout=10
        )
    return sorted(deployment.metadata.name for deployment in deployments.items)


@mcp.tool()
def list_services(namespace: str = "default") -> list[str]:
    """List service names in one namespace. If omitted, use default."""
    namespace = namespace.strip() or "default"
    with open_developer_client() as api_client:
        logger.info("Kubernetes SDK: list services in namespace %s.", namespace)
        services = client.CoreV1Api(api_client).list_namespaced_service(
            namespace=namespace, _request_timeout=10
        )
    return sorted(service.metadata.name for service in services.items)


@mcp.tool()
def list_nodes() -> list[str]:
    """List cluster nodes with readiness, roles, IP, and kubelet version."""
    with open_developer_client() as api_client:
        logger.info("Kubernetes SDK: list cluster nodes.")
        nodes = client.CoreV1Api(api_client).list_node(_request_timeout=10)

    details = []
    role_prefix = "node-role.kubernetes.io/"
    for node in sorted(nodes.items, key=lambda item: item.metadata.name):
        status = node.status or client.V1NodeStatus()
        ready = next(
            (condition.status for condition in status.conditions or []
             if condition.type == "Ready"),
            "Unknown",
        )
        readiness = {"True": "Ready", "False": "NotReady"}.get(ready, "Unknown")
        roles = sorted(
            label.removeprefix(role_prefix)
            for label in (node.metadata.labels or {})
            if label.startswith(role_prefix)
        )
        internal_ip = next(
            (address.address for address in status.addresses or []
             if address.type == "InternalIP"),
            "Unknown",
        )
        version = status.node_info.kubelet_version if status.node_info else "Unknown"
        details.append(
            f"{node.metadata.name} | {readiness} | Roles: {', '.join(roles) or 'None'}"
            f" | Internal IP: {internal_ip} | Kubelet: {version}"
        )
    return details


@mcp.tool()
def get_pod_logs(
    pod_name: str,
    namespace: str = "default",
    container: str = "",
    tail_lines: int = 100,
) -> list[str]:
    """Get recent logs from a pod using the Developer kubeconfig."""
    namespace = namespace.strip() or "default"
    tail_lines = max(1, min(tail_lines, 500))
    with open_developer_client() as api_client:
        logger.info("Kubernetes SDK: get logs for pod %s in namespace %s.", pod_name, namespace)
        log_text = client.CoreV1Api(api_client).read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container.strip() or None,
            tail_lines=tail_lines,
            timestamps=True,
            _request_timeout=10,
        )
    return log_text.splitlines() or ["No log lines found."]


@mcp.tool()
def get_pod_events(pod_name: str, namespace: str = "default") -> list[str]:
    """Get recent Kubernetes events for a pod."""
    namespace = namespace.strip() or "default"
    with open_developer_client() as api_client:
        api = client.CoreV1Api(api_client)
        logger.info("Kubernetes SDK: get events for pod %s in namespace %s.", pod_name, namespace)
        pod = api.read_namespaced_pod(
            name=pod_name, namespace=namespace, _request_timeout=10
        )
        events = api.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.uid={pod.metadata.uid}",
            _request_timeout=10,
        )

    recent_events = sorted(
        events.items,
        key=lambda event: str(
            event.last_timestamp
            or event.event_time
            or event.metadata.creation_timestamp
        ),
        reverse=True,
    )[:MAX_POD_EVENTS]
    return [
        f"{event.type or 'Unknown'} ({event.reason or 'Unknown'}): "
        f"{event.message or 'No message'}"
        for event in recent_events
    ] or ["No events found."]


@mcp.tool()
def diagnose_pod(pod_name: str, namespace: str = "default") -> list[str]:
    """Diagnose a pod using admin access, status, and warning events."""
    namespace = namespace.strip() or "default"
    with open_admin_client() as api_client:
        api = client.CoreV1Api(api_client)
        logger.info("Kubernetes SDK: diagnose pod %s in namespace %s.", pod_name, namespace)
        pod = api.read_namespaced_pod(
            name=pod_name, namespace=namespace, _request_timeout=10
        )
        status = pod.status or client.V1PodStatus()
        details = [
            f"Pod: {namespace}/{pod.metadata.name}",
            f"Phase: {status.phase or 'Unknown'}",
        ]
        for condition in status.conditions or []:
            if condition.status != "True":
                details.append(
                    f"Condition {condition.type}: {condition.status}"
                    f" - {condition.message or 'No message'}"
                )
        statuses = (status.init_container_statuses or []) + (
            status.container_statuses or []
        )
        for container in statuses:
            details.append(
                f"Container {container.name}: ready={container.ready}, "
                f"restarts={container.restart_count}"
            )
            if container.state and container.state.waiting:
                details.append(
                    f"Waiting reason: {container.state.waiting.reason or 'Unknown'}"
                )
            if container.state and container.state.terminated:
                terminated = container.state.terminated
                details.append(
                    f"Termination: {terminated.reason or 'Unknown'}, "
                    f"exit code {terminated.exit_code}"
                )
            if container.last_state and container.last_state.terminated:
                previous = container.last_state.terminated
                details.append(
                    f"Previous termination: {previous.reason or 'Unknown'}, "
                    f"exit code {previous.exit_code}"
                )
        events = api.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.uid={pod.metadata.uid},type=Warning",
            _request_timeout=10,
        )
    recent_events = sorted(
        events.items,
        key=lambda event: str(
            event.last_timestamp
            or event.event_time
            or event.metadata.creation_timestamp
        ),
        reverse=True,
    )[:MAX_POD_EVENTS]
    for event in recent_events:
        details.append(
            f"Warning event ({event.reason or 'Unknown'}): "
            f"{event.message or 'No message'}"
        )
    if not recent_events:
        details.append("No warning events found for this pod.")
    return details


if __name__ == "__main__":
    # Keep this first development server local until HTTP authentication is added.
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8000,
        stateless_http=True,
    )
