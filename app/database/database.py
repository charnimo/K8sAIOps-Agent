from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"

# connect_args check_same_thread is needed only for SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


PERMISSION_CATALOG_SEED = [
    {"permission_key": "dashboard:read", "label": "View Dashboard", "description": "Access dashboard summary cards.", "is_dangerous": False},
    {"permission_key": "events:read", "label": "View Events", "description": "Read cluster and namespace events.", "is_dangerous": False},
    {"permission_key": "audit:read", "label": "View Audit Logs", "description": "Read audit trail entries.", "is_dangerous": False},
    {"permission_key": "audit:cleanup", "label": "Cleanup Audit Logs", "description": "Delete old audit entries.", "is_dangerous": True},

    {"permission_key": "pods:read", "label": "Read Pods", "description": "List and inspect pods.", "is_dangerous": False},
    {"permission_key": "pods:logs", "label": "Read Pod Logs", "description": "View pod logs.", "is_dangerous": False},
    {"permission_key": "pods:exec", "label": "Exec Into Pods", "description": "Run commands in containers.", "is_dangerous": True},
    {"permission_key": "pods:delete", "label": "Delete Pods", "description": "Delete pods.", "is_dangerous": True},

    {"permission_key": "deployments:read", "label": "Read Deployments", "description": "List and inspect deployments.", "is_dangerous": False},
    {"permission_key": "deployments:scale", "label": "Scale Deployments", "description": "Change replica counts.", "is_dangerous": True},
    {"permission_key": "deployments:restart", "label": "Restart Deployments", "description": "Trigger rollout restart.", "is_dangerous": True},
    {"permission_key": "deployments:rollback", "label": "Rollback Deployments", "description": "Rollback to previous revision.", "is_dangerous": True},
    {"permission_key": "deployments:patch", "label": "Patch Deployments", "description": "Patch deployment settings.", "is_dangerous": True},

    {"permission_key": "services:read", "label": "Read Services", "description": "List and inspect services.", "is_dangerous": False},
    {"permission_key": "services:create", "label": "Create Services", "description": "Create services.", "is_dangerous": True},
    {"permission_key": "services:patch", "label": "Patch Services", "description": "Patch service definitions.", "is_dangerous": True},
    {"permission_key": "services:delete", "label": "Delete Services", "description": "Delete services.", "is_dangerous": True},

    {"permission_key": "workloads:statefulsets:read", "label": "Read StatefulSets", "description": "List and inspect StatefulSets.", "is_dangerous": False},
    {"permission_key": "workloads:statefulsets:scale", "label": "Scale StatefulSets", "description": "Change StatefulSet replicas.", "is_dangerous": True},
    {"permission_key": "workloads:statefulsets:restart", "label": "Restart StatefulSets", "description": "Trigger StatefulSet restart.", "is_dangerous": True},
    {"permission_key": "workloads:daemonsets:read", "label": "Read DaemonSets", "description": "List and inspect DaemonSets.", "is_dangerous": False},
    {"permission_key": "workloads:daemonsets:restart", "label": "Restart DaemonSets", "description": "Trigger DaemonSet restart.", "is_dangerous": True},
    {"permission_key": "workloads:daemonsets:update_image", "label": "Update DaemonSet Image", "description": "Change DaemonSet container images.", "is_dangerous": True},
    {"permission_key": "workloads:jobs:read", "label": "Read Jobs", "description": "List and inspect Jobs.", "is_dangerous": False},
    {"permission_key": "workloads:jobs:delete", "label": "Delete Jobs", "description": "Delete Jobs.", "is_dangerous": True},
    {"permission_key": "workloads:jobs:suspend", "label": "Suspend Jobs", "description": "Suspend Jobs.", "is_dangerous": True},
    {"permission_key": "workloads:jobs:resume", "label": "Resume Jobs", "description": "Resume Jobs.", "is_dangerous": True},
    {"permission_key": "workloads:cronjobs:read", "label": "Read CronJobs", "description": "List and inspect CronJobs.", "is_dangerous": False},
    {"permission_key": "workloads:cronjobs:suspend", "label": "Suspend CronJobs", "description": "Suspend CronJobs.", "is_dangerous": True},
    {"permission_key": "workloads:cronjobs:resume", "label": "Resume CronJobs", "description": "Resume CronJobs.", "is_dangerous": True},

    {"permission_key": "configmaps:read", "label": "Read ConfigMaps", "description": "List and inspect ConfigMaps.", "is_dangerous": False},
    {"permission_key": "configmaps:create", "label": "Create ConfigMaps", "description": "Create ConfigMaps.", "is_dangerous": True},
    {"permission_key": "configmaps:patch", "label": "Patch ConfigMaps", "description": "Patch ConfigMap data.", "is_dangerous": True},
    {"permission_key": "configmaps:delete", "label": "Delete ConfigMaps", "description": "Delete ConfigMaps.", "is_dangerous": True},

    {"permission_key": "secrets:read", "label": "Read Secret Metadata", "description": "Read secret existence and metadata.", "is_dangerous": False},
    {"permission_key": "secrets:read_plaintext", "label": "Read Secret Values", "description": "Read plaintext secret values.", "is_dangerous": True},
    {"permission_key": "secrets:create", "label": "Create Secrets", "description": "Create Secrets.", "is_dangerous": True},
    {"permission_key": "secrets:update", "label": "Update Secrets", "description": "Update Secret data.", "is_dangerous": True},
    {"permission_key": "secrets:delete", "label": "Delete Secrets", "description": "Delete Secrets.", "is_dangerous": True},

    {"permission_key": "ingresses:read", "label": "Read Ingresses", "description": "List and inspect Ingresses.", "is_dangerous": False},
    {"permission_key": "ingresses:create", "label": "Create Ingresses", "description": "Create Ingress resources.", "is_dangerous": True},
    {"permission_key": "ingresses:patch", "label": "Patch Ingresses", "description": "Patch Ingress resources.", "is_dangerous": True},
    {"permission_key": "ingresses:delete", "label": "Delete Ingresses", "description": "Delete Ingress resources.", "is_dangerous": True},
    {"permission_key": "network_policies:read", "label": "Read Network Policies", "description": "Inspect network policies and issues.", "is_dangerous": False},

    {"permission_key": "rbac:read", "label": "Read RBAC", "description": "Read service accounts, roles, and bindings.", "is_dangerous": False},
    {"permission_key": "hpa:read", "label": "Read HPAs", "description": "List and inspect HPAs.", "is_dangerous": False},
    {"permission_key": "hpa:create", "label": "Create HPAs", "description": "Create HPAs.", "is_dangerous": True},
    {"permission_key": "hpa:patch", "label": "Patch HPAs", "description": "Patch HPA settings.", "is_dangerous": True},
    {"permission_key": "hpa:delete", "label": "Delete HPAs", "description": "Delete HPAs.", "is_dangerous": True},
    {"permission_key": "resource_quotas:read", "label": "Read Quotas", "description": "Read resource quotas and limit ranges.", "is_dangerous": False},

    {"permission_key": "cluster:nodes:read", "label": "Read Nodes", "description": "View nodes and node details.", "is_dangerous": False},
    {"permission_key": "cluster:nodes:cordon", "label": "Cordon Nodes", "description": "Mark nodes unschedulable.", "is_dangerous": True},
    {"permission_key": "cluster:nodes:uncordon", "label": "Uncordon Nodes", "description": "Mark nodes schedulable.", "is_dangerous": True},
    {"permission_key": "cluster:nodes:drain", "label": "Drain Nodes", "description": "Evict workloads from nodes.", "is_dangerous": True},
    {"permission_key": "cluster:namespaces:read", "label": "Read Namespaces", "description": "List and inspect namespaces.", "is_dangerous": False},
    {"permission_key": "cluster:namespaces:create", "label": "Create Namespaces", "description": "Create namespaces.", "is_dangerous": True},
    {"permission_key": "cluster:namespaces:delete", "label": "Delete Namespaces", "description": "Delete namespaces.", "is_dangerous": True},

    {"permission_key": "storage:pvs:read", "label": "Read Persistent Volumes", "description": "List and inspect PVs.", "is_dangerous": False},
    {"permission_key": "storage:pvcs:read", "label": "Read Persistent Volume Claims", "description": "List and inspect PVCs.", "is_dangerous": False},
    {"permission_key": "storage:pvcs:create", "label": "Create PVCs", "description": "Create PVCs.", "is_dangerous": True},
    {"permission_key": "storage:pvcs:patch", "label": "Patch PVCs", "description": "Patch PVC labels.", "is_dangerous": True},
    {"permission_key": "storage:pvcs:delete", "label": "Delete PVCs", "description": "Delete PVCs.", "is_dangerous": True},
    {"permission_key": "storage:classes:read", "label": "Read Storage Classes", "description": "List and inspect storage classes.", "is_dangerous": False},

    {"permission_key": "observability:read", "label": "Read Observability Metrics", "description": "View pod/node metrics and pressure analysis.", "is_dangerous": False},
    {"permission_key": "diagnostics:run", "label": "Run Diagnostics", "description": "Run pod, deployment, service, and cluster diagnostics.", "is_dangerous": False},

    {"permission_key": "terminal:kubectl:readonly", "label": "Cluster Terminal", "description": "Use read-only cluster terminal.", "is_dangerous": False},
]


def seed_permission_catalog():
    from app.database.models import PermissionCatalog

    db = SessionLocal()
    try:
        for item in PERMISSION_CATALOG_SEED:
            existing = db.query(PermissionCatalog).filter(PermissionCatalog.permission_key == item["permission_key"]).first()
            if existing:
                existing.label = item["label"]
                existing.description = item["description"]
                existing.is_dangerous = item["is_dangerous"]
                if existing.enabled is None:
                    existing.enabled = True
            else:
                db.add(PermissionCatalog(
                    permission_key=item["permission_key"],
                    label=item["label"],
                    description=item["description"],
                    is_dangerous=item["is_dangerous"],
                    enabled=True,
                ))
        db.commit()
    finally:
        db.close()


def seed_mock_chat_history():
    from app.database.models import ChatHistory, Conversation, User

    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            return

        seed_templates = [
            {
                "title": "Cluster Incident Triage (Mock)",
                "messages": [
                    ("agent", "Welcome back. I can help triage cluster incidents by collecting symptoms and narrowing root causes."),
                    ("user", "Pods in namespace payments are restarting every few minutes."),
                    ("agent", "Start by checking recent events and pod restart reasons; then correlate with rollout or config changes."),
                ],
            },
            {
                "title": "Capacity Planning Review (Mock)",
                "messages": [
                    ("agent", "Ready to review capacity trends. Which namespace or workload do you want to analyze?"),
                    ("user", "Show me where CPU pressure is highest this week."),
                    ("agent", "Use resource pressure and top pod CPU metrics to identify hotspots before increasing limits."),
                ],
            },
        ]

        for user in users:
            for template in seed_templates:
                existing = (
                    db.query(Conversation)
                    .filter(Conversation.user_id == user.id, Conversation.title == template["title"])
                    .first()
                )
                if existing:
                    continue

                conversation = Conversation(user_id=user.id, title=template["title"])
                db.add(conversation)
                db.flush()

                for sender, message in template["messages"]:
                    sender_name = user.username if sender == "user" else sender
                    db.add(
                        ChatHistory(
                            conversation_id=conversation.id,
                            sender=sender_name,
                            message=message,
                        )
                    )

        db.commit()
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
