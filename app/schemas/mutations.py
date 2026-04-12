"""Request schemas for direct mutation endpoints."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ServicePortRequest(BaseModel):
    """Service port spec."""

    port: int = Field(..., ge=1, le=65535)
    target_port: int | str
    protocol: str = "TCP"
    name: Optional[str] = None


class LabelMetadataRequest(BaseModel):
    """Generic labels payload."""

    labels: dict[str, str] = Field(default_factory=dict)


class DataPayloadRequest(BaseModel):
    """Generic string map payload."""

    data: dict[str, str] = Field(..., min_length=1)


class CreateConfigMapRequest(BaseModel):
    """ConfigMap creation payload."""

    name: str = Field(..., min_length=1)
    namespace: str = Field(default="default", min_length=1)
    data: dict[str, str] = Field(..., min_length=1)
    labels: dict[str, str] = Field(default_factory=dict)


class PatchConfigMapRequest(BaseModel):
    """ConfigMap patch payload."""

    namespace: str = Field(default="default", min_length=1)
    data: dict[str, str] = Field(..., min_length=1)


class CreateSecretRequest(BaseModel):
    """Secret creation payload."""

    name: str = Field(..., min_length=1)
    namespace: str = Field(default="default", min_length=1)
    data: dict[str, str] = Field(..., min_length=1)
    secret_type: str = Field(default="Opaque", min_length=1)


class UpdateSecretRequest(BaseModel):
    """Secret update payload."""

    namespace: str = Field(default="default", min_length=1)
    data: dict[str, str] = Field(..., min_length=1)


class PodExecRequest(BaseModel):
    """Pod exec payload."""

    command: str | list[str]
    stdin: bool = False
    stdout: bool = True
    stderr: bool = True
    tty: bool = False


class ScaleRequest(BaseModel):
    """Replica count update payload."""

    replicas: int = Field(..., ge=0)


class DeploymentResourceLimitsPatchRequest(BaseModel):
    """Deployment resource limits patch payload."""

    container_name: Optional[str] = None
    cpu_request: Optional[str] = None
    cpu_limit: Optional[str] = None
    memory_request: Optional[str] = None
    memory_limit: Optional[str] = None
    namespace: str = Field(default="default", min_length=1)


class DeploymentEnvPatchRequest(BaseModel):
    """Deployment env var patch payload."""

    key: str = Field(..., min_length=1)
    value: str
    container_name: Optional[str] = None
    namespace: str = Field(default="default", min_length=1)


class DeploymentRollbackRequest(BaseModel):
    """Deployment rollback payload."""

    namespace: str = Field(default="default", min_length=1)
    revision: Optional[int] = Field(default=None, ge=0)


class CreateServiceRequest(BaseModel):
    """Service creation payload."""

    name: str = Field(..., min_length=1)
    namespace: str = Field(default="default", min_length=1)
    service_type: str = Field(default="ClusterIP", min_length=1)
    selector: dict[str, str] = Field(default_factory=dict)
    ports: list[ServicePortRequest] = Field(default_factory=lambda: [ServicePortRequest(port=80, target_port=8080)])
    labels: dict[str, str] = Field(default_factory=dict)


class PatchServiceRequest(BaseModel):
    """Service patch payload."""

    namespace: str = Field(default="default", min_length=1)
    selector: Optional[dict[str, str]] = None
    ports: Optional[list[ServicePortRequest]] = None
    labels: Optional[dict[str, str]] = None


class IngressPathRequest(BaseModel):
    """Ingress backend path payload."""

    path: str = "/"
    service: str = Field(..., min_length=1)
    port: int = Field(default=80, ge=1, le=65535)


class IngressRuleRequest(BaseModel):
    """Ingress rule payload."""

    host: Optional[str] = None
    paths: list[IngressPathRequest] = Field(default_factory=list)


class IngressTlsRequest(BaseModel):
    """Ingress TLS payload."""

    hosts: list[str] = Field(default_factory=list)
    secret_name: Optional[str] = None


class CreateIngressRequest(BaseModel):
    """Ingress creation payload."""

    name: str = Field(..., min_length=1)
    namespace: str = Field(default="default", min_length=1)
    rules: list[IngressRuleRequest] = Field(default_factory=list)
    tls: list[IngressTlsRequest] = Field(default_factory=list)
    annotations: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)


class PatchIngressRequest(BaseModel):
    """Ingress patch payload."""

    namespace: str = Field(default="default", min_length=1)
    labels: Optional[dict[str, str]] = None
    annotations: Optional[dict[str, str]] = None
