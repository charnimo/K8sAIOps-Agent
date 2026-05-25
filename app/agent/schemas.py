"""Data schemas for agent system.

Includes IncidentRecord, graph states, and tool definitions.
"""

from typing import Any, Dict, List, Optional, TypedDict
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================================
# ENUMS
# ============================================================================


class SeverityLevel(str, Enum):
    """Incident severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, Enum):
    """Incident lifecycle status."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    REMEDIATION_PLANNED = "REMEDIATION_PLANNED"
    REMEDIATION_IN_PROGRESS = "REMEDIATION_IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class ResourceType(str, Enum):
    """Kubernetes resource types."""

    POD = "Pod"
    DEPLOYMENT = "Deployment"
    HPA = "HorizontalPodAutoscaler"
    STATEFULSET = "StatefulSet"
    DAEMONSET = "DaemonSet"
    JOB = "Job"
    CRONJOB = "CronJob"
    SERVICE = "Service"
    INGRESS = "Ingress"
    CONFIGMAP = "ConfigMap"
    SECRET = "Secret"
    NODE = "Node"
    NAMESPACE = "Namespace"


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class EnrichedEventInput(BaseModel):
    """Enriched Kubernetes event ready for incident processing."""

    resource_type: ResourceType
    resource_name: str
    namespace: str
    reason: str
    severity: SeverityLevel
    teams: List[str]
    timestamp: datetime
    dedup_fingerprint: str
    raw_count: int
    message: str
    additional_context: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class DiagnosticResult(BaseModel):
    """Result from executing a single diagnostic tool."""

    tool_name: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0

    class Config:
        use_enum_values = True


class RootCauseAnalysis(BaseModel):
    """LLM-generated root cause analysis."""

    root_cause: str
    hypothesis_confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: List[str]
    reasoning: str


class SuggestedAction(BaseModel):
    """Action suggested by LLM for remediation."""

    action_type: str
    description: str
    target_resource: str
    priority: int = 1
    estimated_risk: str = "LOW"
    rationale: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)


class RemediationStep(BaseModel):
    """Single ordered remediation step for handoff to another agent."""

    step_number: int
    action_type: str
    description: str
    target_resource: str
    why: str
    evidence: List[str] = Field(default_factory=list)
    estimated_risk: str = "LOW"


class IncidentRecord(BaseModel):
    """Complete incident record from detection through investigation."""

    # Identifiers
    incident_id: str
    trace_id: str
    conversation_id: Optional[int] = None

    # Resource information
    resource_type: ResourceType
    resource_name: str
    namespace: str
    reason: str

    # Severity & team
    severity: SeverityLevel
    teams: List[str]

    # Summaries
    summary: str
    detailed_summary: Optional[str] = None
    log_snapshot: Optional[str] = None

    # Investigation data
    collected_diagnostics: Dict[str, Any] = Field(default_factory=dict)
    tools_called: List[str] = Field(default_factory=list)

    # LLM analysis
    llm_reasoning: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_response_model: Optional[str] = None
    llm_response_source: Optional[str] = None
    root_cause_analysis: Optional[RootCauseAnalysis] = None
    suggested_actions: List[SuggestedAction] = Field(default_factory=list)
    remediation_plan: List[RemediationStep] = Field(default_factory=list)
    evidence_map: Dict[str, List[str]] = Field(default_factory=dict)

    # Recipient routing
    concerned_person: Optional[Dict[str, Any]] = None
    concerned_users: List[Dict[str, Any]] = Field(default_factory=list)
    owner_hints: List[str] = Field(default_factory=list)

    # Lifecycle
    status: IncidentStatus = IncidentStatus.OPEN
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None

    # Audit trail
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        use_enum_values = True


# ============================================================================
# LANGGRAPH STATE SCHEMAS (TypedDict for type hints)
# ============================================================================


class MonitoringGraphState(TypedDict, total=False):
    """State for the monitoring graph.

    Tracks all data from event detection through incident persistence.
    """

    # Input
    event: EnrichedEventInput

    # Node 2: LLM Tool Selection
    tools_to_call: List[str]
    llm_tool_reasoning: str
    llm_provider: str
    llm_model: str
    llm_response_model: str
    llm_response_source: str
    suggested_action_tools: List[str]
    remediation_plan: List[Dict[str, Any]]
    evidence_map: Dict[str, List[str]]

    # Node 3: Collect Diagnostics
    collected_diagnostics: Dict[str, DiagnosticResult]

    # Node 4: Classify Severity
    severity: SeverityLevel
    root_cause_analysis: RootCauseAnalysis
    summary: str
    detailed_summary: str
    suggested_actions: List[SuggestedAction]

    # Node 5: Resolve Team
    teams: List[str]

    # Node 5b: Resolve Recipient
    concerned_person: Dict[str, Any]
    concerned_users: List[Dict[str, Any]]
    owner_hints: List[str]

    # Evidence snapshot
    log_snapshot: str

    # Node 6: Persist Incident
    incident_record: IncidentRecord

    # Error tracking
    errors: List[str]

    # Metadata
    execution_start_time: datetime
    execution_end_time: Optional[datetime]


# ============================================================================
# TOOL REGISTRY SCHEMAS
# ============================================================================


class ToolDefinition(BaseModel):
    """Definition of a tool available to the agent."""

    name: str
    description: str
    category: str  # "diagnostics", "mutation", "query", etc.
    parameters: Dict[str, Any]  # Schema for tool parameters
    returns: Dict[str, Any]  # Schema for tool return value
    permission_required: Optional[str] = None
    is_read_only: bool = True

    class Config:
        use_enum_values = True


