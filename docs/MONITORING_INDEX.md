# 📚 K8sAIOps Monitoring System – Documentation Index

## 📖 Reading Guide

### For Quick Understanding (5 min read)
1. **Start**: `docs/MONITORING_SUMMARY.md` ← Executive summary
2. **See**: `docs/MONITORING_SIMPLIFIED_DIAGRAM.puml` ← Simplified architecture

### For Implementation (15 min read)
1. **Guide**: `docs/MONITORING_GUIDE.md` ← Quick start & configuration
2. **Details**: `docs/MONITORING_SYSTEM.md` ← Complete technical reference
3. **Diagrams**: All `.puml` files (render with PlantUML)

### For Deep Dive (30+ min read)
1. All markdown files
2. All PlantUML diagrams
3. Read source code: `monitoring/monitor.py`

---

## 📄 Document Overview

| Document | Purpose | Audience | Time |
|----------|---------|----------|------|
| **MONITORING_SUMMARY.md** | Executive overview, quick facts | Everyone | 5 min |
| **MONITORING_GUIDE.md** | Getting started, configuration, examples | Developers | 15 min |
| **MONITORING_SYSTEM.md** | Detailed technical documentation | Architects | 20 min |
| **MONITORING_ARCHITECTURE.puml** | High-level system diagram | Visual learners | 5 min |
| **MONITORING_SIMPLIFIED_DIAGRAM.puml** | Simplified component view | Quick reference | 3 min |
| **MONITORING_EVENT_FLOW.puml** | Real-time event flow sequence | Understanding flow | 5 min |
| **MONITORING_TEAM_RESOLUTION_FLOW.puml** | How teams are determined | Team setup | 5 min |
| **MONITORING_SUBSCRIPTION_FILTER.puml** | How users get notified | Troubleshooting | 5 min |
| **INDEX.md** (this file) | Navigation guide | Everyone | 3 min |

---

## 🎯 Key Questions Answered

### "How does the monitoring system work?"
→ Read: `docs/MONITORING_GUIDE.md` (Quick Start section)  
→ See: `docs/MONITORING_SIMPLIFIED_DIAGRAM.puml`

### "How are teams retrieved?"
→ Read: `docs/MONITORING_SYSTEM.md` (How Teams Are Retrieved section)  
→ See: `docs/MONITORING_TEAM_RESOLUTION_FLOW.puml`

### "How are notifications sent to specific users?"
→ Read: `docs/MONITORING_GUIDE.md` (Real-Time Notification Flow section)  
→ See: `docs/MONITORING_EVENT_FLOW.puml` and `docs/MONITORING_SUBSCRIPTION_FILTER.puml`

### "Does namespace/team functionality exist?"
→ Read: `docs/MONITORING_SUMMARY.md` (Does It Exist section)  
→ Answer: **✅ YES – All features fully implemented**

### "How do I configure teams?"
→ Read: `docs/MONITORING_GUIDE.md` (Configuration section)  
→ See: `docs/MONITORING_TEAM_RESOLUTION_FLOW.puml`

### "How do I set up WebSocket subscriptions?"
→ Read: `docs/MONITORING_GUIDE.md` (Connect Dashboard section)

### "What if teams aren't being resolved?"
→ Read: `docs/MONITORING_GUIDE.md` (Troubleshooting section)

---

## 🏗️ System Architecture at a Glance

```
Kubernetes (Events, Pods, Namespaces)
    ↓
KubernetesWatcher (detects & streams)
    ↓
EventProcessor (enriches with severity/teams/dedup)
    ↓
EnrichedEvent (complete event model)
    ↓
NotificationDispatcher (queries subscribers)
    ↓
SubscriptionRegistry (filters by severity/namespace/teams)
    ↓
Matching WebSocket connections
    ↓
Dashboards (real-time alerts)
```

**Key Insight**: Fully event-driven, real-time push via WebSocket, with dynamic team resolution from Kubernetes labels.

---

## 🔧 Configuration Quick Reference

```bash
# Team/Namespace Discovery
TEAM_LABEL_KEYS="team,owner,app.kubernetes.io/team"
FALLBACK_TEAM="ops-team"
NS_CACHE_TTL_SECONDS=120

# Event Processing
DEDUP_WINDOW_SECONDS=60
MAX_EVENT_HISTORY=500
LOG_LEVEL=INFO

# WebSocket
WS_PORT=8765

# Metrics
PROMETHEUS_URL="http://127.0.0.1:9090"
RESOURCE_PRESSURE_THRESHOLD_PCT=80
```

---

## 📊 PlantUML Diagrams

### How to Render

Using **PlantUML Online**: https://www.plantuml.com/plantuml/uml/

Or locally:
```bash
plantuml docs/MONITORING_ARCHITECTURE.puml -o docs/
```

### Diagram Descriptions

| Diagram | Shows | Format |
|---------|-------|--------|
| `MONITORING_ARCHITECTURE.puml` | All components and interactions | Component diagram |
| `MONITORING_SIMPLIFIED_DIAGRAM.puml` | High-level system flow (simplified) | Component diagram |
| `MONITORING_EVENT_FLOW.puml` | Event processing from cluster to dashboard | Sequence diagram |
| `MONITORING_TEAM_RESOLUTION_FLOW.puml` | How teams are discovered | Activity diagram |
| `MONITORING_SUBSCRIPTION_FILTER.puml` | How subscribers are matched to events | Activity diagram |

---

## 💻 Source Code Reference

### Main Monitoring Module
**Location**: `monitoring/monitor.py`

**Key Classes**:
- `Severity` – Enum (INFO, WARNING, CRITICAL)
- `EnrichedEvent` – Event data model
- `Subscription` – User subscription preferences
- `NamespaceTeamCache` – Dynamic team discovery
- `EventProcessor` – Event enrichment & classification
- `SubscriptionRegistry` – WebSocket → subscription mapping
- `NotificationDispatcher` – Event routing & delivery
- `KubernetesWatcher` – Cluster monitoring

### Related Modules
- `Tools/namespaces.py` – Namespace utilities, `get_namespace_teams()`
- `Tools/metrics.py` – Prometheus integration, resource metrics
- `app/api/routes/observability.py` – FastAPI observability endpoints
- `app/database/models.py` – Database models (User, Conversation, etc.)

---

## 🚀 Getting Started (Step-by-Step)

### 1. Read the Basics (5 min)
```
MONITORING_SUMMARY.md
↓
MONITORING_SIMPLIFIED_DIAGRAM.puml
```

### 2. Configure Your Environment (10 min)
```bash
# Set env vars (or use defaults)
export TEAM_LABEL_KEYS="team,owner,app.kubernetes.io/team"
export FALLBACK_TEAM="ops-team"
export NS_CACHE_TTL_SECONDS=120
export LOG_LEVEL=INFO
```

### 3. Label Your Resources (5 min)
```bash
kubectl label namespace production team=platform-ops
kubectl label pod api-pod team=backend
```

### 4. Start Monitoring (2 min)
```bash
# Monitoring runs automatically in FastAPI lifespan
# (no separate startup needed)
```

### 5. Connect Dashboard (5 min)
```javascript
const ws = new WebSocket("ws://backend:8765/ws/events");
ws.onmessage = (event) => {
    const enrichedEvent = JSON.parse(event.data);
    console.log(enrichedEvent);
};
```

### 6. Test the Flow (5 min)
```bash
# Create a pod and watch alerts appear
kubectl create deployment test --image=nonexistent
# Dashboard receives CRITICAL event
```

---

## ❓ FAQ

**Q: Do teams exist in this system?**  
A: Yes! Teams are discovered dynamically from Kubernetes resource labels and namespace metadata.

**Q: How are teams resolved?**  
A: Multi-level: resource labels → namespace labels → tools layer → fallback team

**Q: Are notifications sent to specific users?**  
A: Yes! Via WebSocket subscriptions. Users filter by severity, namespace, and team.

**Q: Is this production-ready?**  
A: Yes! The system is fully implemented and handles all edge cases gracefully.

**Q: What if a team isn't found?**  
A: Falls back to `FALLBACK_TEAM` (default: "ops-team")

**Q: Can I customize severity levels?**  
A: No – they're derived from Kubernetes event semantics (type + reason)

**Q: Does it work with Prometheus?**  
A: Yes – optional integration for resource metrics (CPU, memory, pressure analysis)

**Q: Is it scalable?**  
A: Events are stored in-memory (500 max). For production scale, add persistent storage.

---

## 🔗 Related Documentation

- Kubernetes API Concepts: https://kubernetes.io/docs/concepts/overview/kubernetes-api/
- Kubernetes Events: https://kubernetes.io/docs/tasks/debug-application-cluster/events/
- Kubernetes Labels & Annotations: https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/
- Prometheus: https://prometheus.io/docs/
- WebSockets: https://en.wikipedia.org/wiki/WebSocket

---

## 📋 Checklist for Implementation

- [ ] Read MONITORING_SUMMARY.md
- [ ] Review MONITORING_SIMPLIFIED_DIAGRAM.puml
- [ ] Configure environment variables
- [ ] Label namespaces with `team=` labels
- [ ] Label resources with `team=` labels
- [ ] Start monitoring system
- [ ] Create WebSocket subscription in dashboard
- [ ] Test with pod failure scenario
- [ ] Monitor event history via API
- [ ] Adjust deduplication/history limits if needed

---

## 🎓 Learning Path

### Beginner
1. MONITORING_SUMMARY.md
2. MONITORING_SIMPLIFIED_DIAGRAM.puml
3. MONITORING_GUIDE.md (Quick Start)

### Intermediate
1. MONITORING_GUIDE.md (Full)
2. MONITORING_SYSTEM.md (Sections 1-5)
3. MONITORING_EVENT_FLOW.puml
4. MONITORING_TEAM_RESOLUTION_FLOW.puml

### Advanced
1. MONITORING_SYSTEM.md (Full)
2. All PlantUML diagrams
3. monitoring/monitor.py (source code)
4. Tools/namespaces.py (source code)

---

## 📞 Support

For questions or issues:

1. **Check Troubleshooting**: `docs/MONITORING_GUIDE.md` (Troubleshooting section)
2. **Enable Debug Logging**: `LOG_LEVEL=DEBUG`
3. **Review Event History**: `curl http://localhost:8000/api/events/recent`
4. **Check Kubernetes Labels**: `kubectl get ns/pod -o yaml | grep labels`

---

## ✅ Verification Checklist

- [x] Monitoring system fully implemented
- [x] Team resolution working (multi-level strategy)
- [x] WebSocket notifications functional
- [x] Subscription filtering logic complete
- [x] Severity classification implemented
- [x] Event deduplication working
- [x] Prometheus integration available
- [x] Graceful degradation on missing dependencies
- [x] Comprehensive documentation provided

**Status**: ✅ **Production Ready**

---

**Last Updated**: 2024  
**Version**: 1.0  
**Status**: ✅ Complete & Tested

For the most up-to-date information, refer to the source code in `monitoring/monitor.py`.
