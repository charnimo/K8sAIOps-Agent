"""Shared request and response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ResourceTargetRequest(BaseModel):
    """Simple namespaced resource identifier."""

    name: str = Field(..., min_length=1)
    namespace: str = Field(default="default", min_length=1)


class DeploymentDiagnosisRequest(ResourceTargetRequest):
    """Deployment diagnosis request payload."""

    include_pod_details: bool = False
    include_resource_pressure: bool = False


class ServiceTargetRequest(ResourceTargetRequest):
    """Service diagnosis request payload."""


class ChatMessageRequest(BaseModel):
    """User chat message payload."""

    content: str = Field(..., min_length=1)


class ActionTarget(BaseModel):
    """Generic action target."""

    name: str = Field(..., min_length=1)
    namespace: str = Field(default="default", min_length=1)


class ActionRequestCreate(BaseModel):
    """Create a new action request."""

    type: str = Field(..., min_length=1)
    target: ActionTarget
    params: dict[str, Any] = Field(default_factory=dict)

