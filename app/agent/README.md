# Agent Module - Monitoring Graph Implementation

Complete LangGraph-based monitoring system for automated Kubernetes incident detection and diagnostics.

## Module Structure

```
app/agent/
├── __init__.py           # Package exports
├── config.py             # LLM configuration (with placeholders)
├── schemas.py            # Pydantic models and TypedDict schemas
├── tools.py              # Tool registry and wrappers
├── monitoring_graph.py   # Complete LangGraph DAG for monitoring
├── memory.py             # Incident memory store for graph state
├── testing.py            # Mock clients for testing
└── README.md             # This file
```

## Quick Start

### 1. Configure LLM Provider

Edit `app/agent/config.py`:

```python
# Set environment variables OR update LLM_CONFIG directly
export LLM_PROVIDER="openai"          # or "anthropic", "ollama"
export LLM_API_KEY="sk-..."            # Your API key
export LLM_MODEL="gpt-4o"              # Model to use
```

Then implement `get_llm_client()`:

```python
def get_llm_client():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=LLM_CONFIG.model,
        api_key=LLM_CONFIG.api_key,
        temperature=LLM_CONFIG.temperature,
    )
```

### 2. Wire Kubernetes Tools

Edit `app/agent/tools.py` and uncomment actual tool imports:

```python
# Before (placeholders):
async def _get_pod_logs(...):
    logger.info("[PLACEHOLDER] get_pod_logs(...)")
    return {"logs": []}

# After (actual implementation):
async def _get_pod_logs(namespace: str, pod_name: str, ...):
    from Tools.pods import get_pod_logs as real_get_pod_logs
    return real_get_pod_logs(namespace, pod_name, ...)
```

Replace these placeholders:
- `_get_pod_logs` → `Tools.pods.get_pod_logs`
- `_get_pod_events` → `Tools.events.get_pod_events`
- `_get_pod_status` → `Tools.pods.get_pod_status`
- `_get_pod_metrics` → `Tools.metrics.get_pod_metrics`
- `_get_deployment_info` → `Tools.deployments.get_deployment_info`
- `_list_nodes` → `Tools.nodes.list_nodes`
- `_describe_pod` → `Tools.diagnostics.diagnose_pod`
- `_describe_deployment` → `Tools.diagnostics.diagnose_deployment`

### 3. Implement Database Persistence

Edit `app/agent/monitoring_graph.py`, `node_persist_incident()`:

```python
# Before (placeholder):
logger.info(f"[PLACEHOLDER] Persisting incident {incident.incident_id} to database")

# After (actual persistence):
from app.database.database import SessionLocal
from app.database.models import IncidentRecord as IncidentRecordModel

session = SessionLocal()
try:
    record = IncidentRecordModel(**incident.dict())
    session.add(record)
    session.commit()
    logger.info(f"Persisted incident {incident.incident_id}")
finally:
    session.close()
```

### 4. Implement Notifications

Edit `app/agent/monitoring_graph.py`, `node_notify_team()`:

```python
# Before (placeholder):
logger.info(f"[PLACEHOLDER] Notifying teams...")

# After (actual notification):
from app.api.routes.events import notify_incident
await notify_incident(incident)
```

## Monitoring Graph Flow

```
Input: Kubernetes Event
  ↓
1. Extract Event
  └─ Normalize and validate event
  ↓
2. Decide Tools (LLM)
  └─ LLM selects which diagnostic tools to call
  ↓
3. Collect Diagnostics
  └─ Execute selected tools in parallel
  ↓
4. Classify Severity
  └─ Apply deterministic rules to severity
  ↓
5. Resolve Team
  └─ Identify owning team
  ↓
6. Persist Incident
  └─ Save IncidentRecord to database
  ↓
7. Notify Team
  └─ Send WebSocket notification
  ↓
Output: IncidentRecord
```

## Data Schema

### Input: EnrichedEventInput
```python
{
    "resource_type": "Pod",
    "resource_name": "api-xyz-123",
    "namespace": "production",
    "reason": "CrashLoopBackOff",
    "severity": "CRITICAL",
    "teams": ["backend-team"],
    "timestamp": "2026-05-04T10:15:30Z",
    "message": "Back-off restarting failed container"
}
```

### Output: IncidentRecord
```python
{
    "incident_id": "inc_1234567890",
    "trace_id": "trace_prod_api_1234567890",
    "resource_type": "Pod",
    "resource_name": "api-xyz-123",
    "namespace": "production",
    "reason": "CrashLoopBackOff",
    "severity": "CRITICAL",
    "teams": ["backend-team"],
    "summary": "CrashLoopBackOff in production/api-xyz-123",
    "collected_diagnostics": {
        "get_pod_logs": {...},
        "get_pod_events": {...},
        ...
    },
    "tools_called": ["get_pod_logs", "get_pod_events", "get_pod_status", "get_pod_metrics"],
    "llm_reasoning": "CrashLoopBackOff typically indicates...",
    "root_cause_analysis": {
        "root_cause": "Application out of memory",
        "hypothesis_confidence": 0.92,
        "supporting_evidence": ["Memory usage near limit", "..."]
    },
    "suggested_actions": [
        {
            "action_type": "increase_memory_limit",
            "description": "Increase pod memory limit",
            "target_resource": "production/api-xyz-123"
        },
        ...
    ],
    "status": "OPEN",
    "created_at": "2026-05-04T10:15:30Z"
}
```

## Testing

### With Mock LLM (No API Key)

```python
from app.agent.config import LLMConfig, LLMProvider

# Use mock provider
config = LLMConfig(provider=LLMProvider.MOCK)

# Build and run graph
from app.agent.monitoring_graph import build_monitoring_graph
graph = build_monitoring_graph()

# Create test input
event = EnrichedEventInput(
    resource_type=ResourceType.POD,
    resource_name="test-pod",
    namespace="default",
    reason="CrashLoopBackOff",
    severity=SeverityLevel.CRITICAL,
    teams=["test-team"],
    timestamp=datetime.now(),
    dedup_fingerprint="test/pod/crash",
    raw_count=1,
    message="Test crash event"
)

# Run graph
result = await graph.ainvoke({"event": event})
print(result["incident_record"])
```

### With Real LLM

```python
import os
os.environ["OPENAI_API_KEY"] = "sk-..."

from app.agent.monitoring_graph import build_monitoring_graph
graph = build_monitoring_graph()

# Same as above - will use real LLM for tool selection
```

## Environment Variables

```bash
# LLM Configuration
export LLM_PROVIDER="openai"                    # openai, anthropic, ollama, mock
export LLM_API_KEY="sk-..."                     # API key if required
export LLM_MODEL="gpt-4o"                       # Model identifier
export LLM_BASE_URL="http://localhost:11434"    # For self-hosted (Ollama)
export LLM_TEMPERATURE="0.7"                    # Sampling temperature
export LLM_MAX_TOKENS="2000"                    # Max response length

# Kubernetes
export KUBECONFIG="/path/to/kubeconfig"         # kubeconfig file
export K8S_MODE="out-of-cluster"                # or "in-cluster"

# Database
export DATABASE_URL="sqlite:///./app.db"        # Database connection
```

## TODO - Placeholders to Fill

- [ ] `config.py` - Implement `get_llm_client()` for your chosen provider
- [ ] `tools.py` - Replace all `_get_*` placeholder functions with real Tool imports
- [ ] `tools.py` - Update tool parameters based on actual function signatures
- [ ] `monitoring_graph.py` - Implement database persistence in `node_persist_incident()`
- [ ] `monitoring_graph.py` - Implement WebSocket notification in `node_notify_team()`
- [ ] `monitoring_graph.py` - Wire `node_decide_tools()` to actual LLM client
- [ ] Create `app/agent/user_graph.py` for multi-step remediation (Phase 2)
- [ ] Update `app/main.py` to initialize monitoring graph in lifespan
- [ ] Wire `handle_agent_event()` in `app/api/routes/chat.py` to trigger monitoring graph

## Integration Points

### 1. Monitoring Pipeline Entry

In `monitoring/monitor.py`, after `EnrichedEvent` is created, trigger the graph:

```python
from app.agent.memory import get_incident_memory

# In EventProcessor or NotificationDispatcher
incident_memory = get_incident_memory()
result = await monitoring_graph.ainvoke({"event": enriched_event})
incident = result.get("incident_record")
incident_memory.store_incident(incident.incident_id, incident.dict())
```

### 2. Chat Integration

In `app/api/routes/chat.py`:

```python
from app.agent.memory import get_incident_memory

@router.post("/chat/sessions/{session_id}/messages")
async def chat_message(session_id: int, request: ChatRequest):
    # ... existing code ...
    
    # Load incident context if available
    incident_memory = get_incident_memory()
    incident_id = request.incident_id  # from chat request
    incident = incident_memory.get_incident(incident_id)
    
    # Pass to user graph for remediation planning
```

### 3. Approval Workflow

Wire incident suggestions to approval system:

```python
from app.database.models import ActionRequest

# When user approves an action
action_request = ActionRequest(
    user_id=user.id,
    action_type=suggestion.action_type,
    resource=suggestion.target_resource,
    description=suggestion.description,
    incident_id=incident.incident_id,
    status="PENDING_APPROVAL"
)
```

## Performance Notes

- **Parallel tool execution**: `node_collect_diagnostics()` runs all tools concurrently
- **LLM latency**: Tool selection adds 1-3s per incident
- **Memory usage**: Incidents cached in memory; configure cleanup as needed
- **Database writes**: Consider batching for high-volume clusters

## Next Steps

1. **Fill all placeholders** (see TODO section)
2. **Test with mock LLM** to validate flow
3. **Integrate with real LLM** when ready
4. **Run integration tests**: `pytest tests/test_tools.py -m integration`
5. **Build user graph** for multi-step remediation (separate module)
6. **Implement approval workflow** tying incidents to actions
7. **Add monitoring dashboard** to visualize incidents in real-time

## Troubleshooting

### "Tool 'get_pod_logs' not found"

Ensure you've implemented the tool wrapper in `tools.py`:
```python
# In tools.py
async def _get_pod_logs(...):
    from Tools.pods import get_pod_logs  # Add this import
    return get_pod_logs(...)  # Add this call
```

### "LLM client not implemented"

Ensure `get_llm_client()` is implemented in `config.py` and API key is set:
```bash
export OPENAI_API_KEY="sk-..."
```

### Graph not persisting incidents

Check that database persistence is implemented in `node_persist_incident()` and database URL is correct:
```bash
export DATABASE_URL="sqlite:///./app.db"
```

## References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
- Project: `CODEBASE_CONTEXT.md`
