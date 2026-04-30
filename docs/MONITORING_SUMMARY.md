# 📊 Monitoring System – Executive Summary

## System Overview

Your K8sAIOps Agent has a **sophisticated real-time Kubernetes monitoring system** that:

1. **Watches** Kubernetes Events, Pods, and Namespaces cluster-wide
2. **Enriches** events with severity classification and team assignment
3. **Routes** events to specific users based on their team/namespace subscriptions
4. **Delivers** via WebSocket (real-time push, not polling)
5. **Integrates** with Prometheus for resource metrics

---

## 🎯 Quick Facts

| Aspect | Implementation |
|--------|-----------------|
| **Architecture** | Event-driven, async-first (asyncio) |
| **Notification Method** | WebSocket (real-time push) |
| **Team Discovery** | Dynamic (from K8s labels/annotations) |
| **Event Filtering** | Multi-level (severity, namespace, team) |
| **Deduplication** | Fingerprint-based rolling window (60s default) |
| **Scalability** | In-memory event history (500 events max) |
| **External Dependency** | Prometheus (optional, for metrics) |

---

## 🔄 High-Level Flow

```
Kubernetes Event
     ↓
KubernetesWatcher (detects)
     ↓
EventProcessor (enriches: severity, teams, dedup)
     ↓
EnrichedEvent (with all metadata)
     ↓
NotificationDispatcher (queries registry)
     ↓
SubscriptionRegistry (filters by user preferences)
     ↓
Matching WebSocket connections
     ↓
Dashboard (displays alert)
```

---

## 👥 How Teams Are Retrieved

### Multi-Level Resolution:
1. **Resource Labels** – Pod/Deployment labels (team, owner, app.kubernetes.io/team)
2. **Namespace Labels** – Namespace labels (same keys)
3. **Tools Layer** – Calls `tools.namespaces.get_namespace_teams()` function
4. **Fallback** – Uses `FALLBACK_TEAM` env var (default: "ops-team")

### Example:
```yaml
Pod with label: team=backend
  ↓ (if not present)
Namespace label: team=platform-ops
  ↓ (if not present)
tools.namespaces.get_namespace_teams("production") → ["ops-team"]
  ↓ (if not present)
FALLBACK_TEAM="ops-team"
```

Result: `teams = [backend]` OR `[platform-ops]` OR `[ops-team]`

---

## 📨 How Notifications Are Sent to Specific Users

### WebSocket-Based Subscription Model:

**1. User Connects**
```json
WebSocket: ws://backend:8765/ws/events
Subscribe with:
{
  "user_id": "alice@example.com",
  "namespaces": [],              // empty = all
  "teams": ["platform-ops"],     // only this team
  "severities": ["WARNING", "CRITICAL"],
  "role": "operator"
}
```

**2. Event Occurs**
```
Pod "api-pod" crashes in namespace "production" 
with label "team=backend"
Severity: CRITICAL
```

**3. Filtering**
```
For each subscriber:
  ✓ Severity CRITICAL in {WARNING, CRITICAL}? YES
  ✓ Namespace empty (= all namespaces)? YES
  ✓ Teams {backend} overlap with {platform-ops}? NO

Result: Alice is NOT notified (different team)
```

**4. Delivery**
Events matching subscription → JSON via WebSocket → Dashboard

### Subscriber Scenarios:

**Platform Ops Lead** (alice):
- Receives: All CRITICAL/WARNING from platform-ops team
- Across: All namespaces

**Backend Team Lead** (bob):
- Receives: All severity from backend team
- In: Production namespace only

**Admin** (charlie):
- Receives: Everything (all teams, all namespaces, all severities)

---

## 🎨 Architecture Components

| Component | Role | Key Method |
|-----------|------|-----------|
| **KubernetesWatcher** | Detects Events/Pods/Namespaces | `.start()` (watches cluster) |
| **EventProcessor** | Normalizes & enriches events | `.from_k8s_event()`, `.from_pod_object()` |
| **NamespaceTeamCache** | Dynamic namespace→team mapping | `.teams_for(ns)`, `.refresh()` |
| **SubscriptionRegistry** | Maps WebSocket → subscriptions | `.get_subscribers(event)` |
| **NotificationDispatcher** | Routes to WebSocket targets | `.dispatch(event)` |
| **Severity Classifier** | K8s type + reason → severity | `_classify_severity()` |

---

## 🔧 Configuration

```bash
# Critical Settings:
TEAM_LABEL_KEYS="team,owner,app.kubernetes.io/team"  # Which labels to check
FALLBACK_TEAM="ops-team"                              # Default team
NS_CACHE_TTL_SECONDS=120                              # Refresh namespace cache every 120s
DEDUP_WINDOW_SECONDS=60                               # Deduplicate for 60 seconds
MAX_EVENT_HISTORY=500                                 # Keep last 500 events in memory

# Label your namespaces/resources:
kubectl label namespace prod team=platform-ops
kubectl label pod api-pod team=backend
```

---

## 📊 Documentation Files

Created comprehensive documentation:

1. **`docs/MONITORING_GUIDE.md`** ← Start here! Quick start guide
2. **`docs/MONITORING_SYSTEM.md`** ← Detailed technical documentation
3. **`docs/MONITORING_ARCHITECTURE.puml`** ← System diagram
4. **`docs/MONITORING_EVENT_FLOW.puml`** ← Event sequence diagram
5. **`docs/MONITORING_TEAM_RESOLUTION_FLOW.puml`** ← Team resolution logic
6. **`docs/MONITORING_SUBSCRIPTION_FILTER.puml`** ← Subscriber filtering logic

---

## ✅ Does It Exist? – Team/Namespace Features

| Feature | Status | Notes |
|---------|--------|-------|
| **Team Resolution** | ✅ YES | Multi-level strategy, fully implemented |
| **Namespace Discovery** | ✅ YES | Dynamic from Kubernetes, cached with TTL |
| **User Subscriptions** | ✅ YES | WebSocket-based, per-connection |
| **Notification Routing** | ✅ YES | Based on severity/namespace/teams |
| **Team-Specific Alerts** | ✅ YES | Via subscription filtering |
| **Namespace Isolation** | ✅ YES | Subscribers can filter by namespace |
| **Fallback Handling** | ✅ YES | Graceful degradation if teams not found |

**All features exist and are production-ready!**

---

## 🚀 Next Steps

1. **Read Full Documentation**: `docs/MONITORING_GUIDE.md`
2. **Label Your Namespaces**: Add `team=` labels to namespaces
3. **Label Your Resources**: Add `team=` labels to Pods/Deployments
4. **Configure Subscriptions**: Set up WebSocket subscriptions in dashboard
5. **Test Event Flow**: Create a pod and watch alerts appear

---

## 📞 Troubleshooting

**Q: Users not receiving notifications?**
A: Check subscription filters (severity, namespace, team affiliation)

**Q: Teams not being resolved?**
A: Verify resource/namespace labels, check `TEAM_LABEL_KEYS` env var

**Q: Events not deduplicating?**
A: Adjust `DEDUP_WINDOW_SECONDS` or check fingerprint logic

**Q: Memory growing too fast?**
A: Reduce `MAX_EVENT_HISTORY` in-memory event storage

---

**Last Updated**: 2024  
**Status**: ✅ Production Ready  
**All features**: ✅ Implemented and functional
