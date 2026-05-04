"""Testing utilities for agent system.

Includes mock LLM client for development and testing without API keys.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MockLLMClient:
    """Mock LLM client for testing and development.

    Returns deterministic responses based on event patterns.
    """

    def __init__(self):
        """Initialize mock LLM client."""
        self.call_count = 0

    async def invoke(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Mock LLM invoke method.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Mock response dict
        """
        self.call_count += 1

        # Extract the prompt to understand what to mock
        last_message = messages[-1].get("content", "")

        # Mock tool selection based on event type
        if "CrashLoopBackOff" in last_message:
            return {
                "content": json.dumps(
                    {
                        "tools": [
                            "get_pod_logs",
                            "get_pod_events",
                            "get_pod_status",
                            "get_pod_metrics",
                        ],
                        "reasoning": "CrashLoopBackOff typically indicates app crash or OOM. Need logs to see error, events for K8s context, status for restart count, metrics to check resource usage.",
                    }
                )
            }

        elif "OOMKilled" in last_message:
            return {
                "content": json.dumps(
                    {
                        "tools": [
                            "get_pod_logs",
                            "get_pod_metrics",
                            "get_pod_status",
                        ],
                        "reasoning": "OOMKilled indicates memory pressure. Need metrics to confirm, logs to see if app detected it, and status for restart info.",
                    }
                )
            }

        elif "ImagePullBackOff" in last_message:
            return {
                "content": json.dumps(
                    {
                        "tools": ["get_pod_events", "get_pod_status"],
                        "reasoning": "ImagePullBackOff means registry pull failed. Events and status should show the error.",
                    }
                )
            }

        elif "FailedScheduling" in last_message:
            return {
                "content": json.dumps(
                    {
                        "tools": ["get_pod_events", "get_pod_status", "list_nodes"],
                        "reasoning": "FailedScheduling means pod can't fit on nodes. Need events for specific reason, status for requirements, list_nodes to check capacity.",
                    }
                )
            }

        # Default response
        return {
            "content": json.dumps(
                {
                    "tools": ["get_pod_logs", "get_pod_events", "get_pod_status"],
                    "reasoning": "Generic diagnostic tools for investigation.",
                }
            )
        }

    def generate(self, prompt: str) -> str:
        """Mock LLM generate method.

        Args:
            prompt: Prompt text

        Returns:
            Mock response text
        """
        response = json.dumps(
            {
                "tools": ["get_pod_logs", "get_pod_events", "get_pod_status"],
                "reasoning": "Mock response for development",
            }
        )
        return response


class MockKubernetesClient:
    """Mock Kubernetes client for testing without cluster access."""

    def __init__(self):
        """Initialize mock K8s client."""
        pass

    async def get_pod_logs(
        self, namespace: str, pod_name: str, container: Optional[str] = None
    ) -> List[str]:
        """Mock get_pod_logs."""
        return [
            "[ERROR] Connection refused",
            "[ERROR] Retrying connection...",
            "[ERROR] Max retries exceeded",
        ]

    async def get_pod_events(self, namespace: str, pod_name: str) -> List[Dict]:
        """Mock get_pod_events."""
        return [
            {
                "reason": "BackOff",
                "message": "Back-off restarting failed container",
                "count": 5,
            },
            {"reason": "Pulling", "message": "Pulling image", "count": 1},
        ]

    async def get_pod_status(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        """Mock get_pod_status."""
        return {
            "phase": "CrashLoopBackOff",
            "restart_count": 7,
            "conditions": [
                {"type": "Ready", "status": "False", "reason": "CrashLoopBackOff"},
            ],
        }

    async def get_pod_metrics(self, namespace: str, pod_name: str) -> Dict[str, str]:
        """Mock get_pod_metrics."""
        return {
            "cpu_usage": "500m",
            "memory_usage": "950Mi",
            "cpu_limit": "1000m",
            "memory_limit": "512Mi",
        }


class MockDatabase:
    """Mock database for testing without real database."""

    def __init__(self):
        """Initialize mock database."""
        self.incidents = {}
        self.next_id = 1

    def save_incident(self, incident_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Save incident record."""
        incident_dict["id"] = self.next_id
        self.incidents[self.next_id] = incident_dict
        self.next_id += 1
        return incident_dict

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Get incident by ID."""
        for incident in self.incidents.values():
            if incident.get("incident_id") == incident_id:
                return incident
        return None
