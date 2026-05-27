
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.database.models import IncidentRecord as IncidentRecordModel
from app.auth.dependencies import get_current_user

"""Event endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from Tools import events as cluster_events
from app.auth.dependencies import require_permission
from app.database.models import User


router = APIRouter()


@router.get("/events")
def list_events(
    namespace: Optional[str] = Query(default="default"),
    severity: str = Query(default="warning"),
    limit: int = Query(default=20, ge=1, le=500),
    user: User = Depends(require_permission("events:read")),
) -> list[dict]:
    """Return recent cluster or namespace events."""
    try:
        if severity == "warning":
            return cluster_events.list_warning_events(namespace=namespace, limit=limit)
        if namespace:
            return cluster_events.list_events(namespace=namespace, limit=limit)
        return cluster_events.list_all_events(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/events/summary")
def get_warning_summary(
    namespace: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=500),
    user: User = Depends(require_permission("events:read")),
) -> list[dict]:
    """Return a compact warning summary for UI and agent context."""
    try:
        return cluster_events.get_recent_warning_summary(namespace=namespace, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/events/resources/{kind}/{name}")
def get_resource_events(
    kind: str,
    name: str,
    namespace: str = Query(default="default"),
    user: User = Depends(require_permission("events:read")),
) -> list[dict]:
    """Return events for a specific resource."""
    try:
        return cluster_events.get_events_for_resource(name=name, kind=kind, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc




from sqlalchemy.orm import Session
from app.database.database import get_db
from app.database.models import IncidentRecord as IncidentRecordModel
from app.auth.dependencies import get_current_user

@router.get("/events/incidents")
def list_incidents(
    namespace: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List incidents, excluding ones the user has dismissed."""
    query = db.query(IncidentRecordModel)
    if namespace:
        query = query.filter(IncidentRecordModel.namespace == namespace)
        
    records = query.order_by(IncidentRecordModel.created_at.desc()).limit(limit).all()
    
    out = []
    for r in records:
        dismissed_list = r.dismissed_by if r.dismissed_by else []
        if user.username in dismissed_list:
            continue  # Skip dismissed incidents
            
        viewed_list = r.viewed_by if r.viewed_by else []
        is_viewed = user.username in viewed_list

        out.append({
            "incident_id": r.incident_id,
            "resource_type": r.resource_type,
            "resource_name": r.resource_name,
            "namespace": r.namespace,
            "reason": r.reason,
            "severity": r.severity,
            "summary": r.summary,
            "detailed_summary": r.detailed_summary,
            "collected_diagnostics": r.collected_diagnostics,
            "root_cause_analysis": r.root_cause_analysis,
            "remediation_plan": r.suggested_actions, # Map to suggested or remediation
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "_is_viewed": is_viewed
        })
    return out

@router.get("/events/incidents/{incident_id}")
def get_incident_detail(
    incident_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    record = db.query(IncidentRecordModel).filter(IncidentRecordModel.incident_id == incident_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Incident not found")

    viewed_list = record.viewed_by if record.viewed_by else []
    
    return {
        "incident_id": record.incident_id,
        "resource_type": record.resource_type,
        "resource_name": record.resource_name,
        "namespace": record.namespace,
        "reason": record.reason,
        "severity": record.severity,
        "summary": record.summary,
        "detailed_summary": record.detailed_summary,
        "log_snapshot": record.log_snapshot,
        "collected_diagnostics": record.collected_diagnostics,
        "root_cause_analysis": record.root_cause_analysis,
        "remediation_plan": record.suggested_actions,
        "status": record.status,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "_is_viewed": user.username in viewed_list
    }

@router.post("/events/incidents/{incident_id}/view")
def mark_incident_viewed(
    incident_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    record = db.query(IncidentRecordModel).filter(IncidentRecordModel.incident_id == incident_id).first()
    if record:
        viewed_list = list(record.viewed_by) if record.viewed_by else []
        if user.username not in viewed_list:
            viewed_list.append(user.username)
            record.viewed_by = viewed_list
            db.commit()
    return {"success": True}

@router.post("/events/incidents/{incident_id}/dismiss")
def dismiss_incident(
    incident_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    record = db.query(IncidentRecordModel).filter(IncidentRecordModel.incident_id == incident_id).first()
    if record:
        dismiss_list = list(record.dismissed_by) if record.dismissed_by else []
        if user.username not in dismiss_list:
            dismiss_list.append(user.username)
            record.dismissed_by = dismiss_list
            db.commit()
    return {"success": True}

@router.post("/events/incidents/dismiss-all")
def dismiss_all_incidents(
    namespace: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    query = db.query(IncidentRecordModel)
    if namespace:
        query = query.filter(IncidentRecordModel.namespace == namespace)
    records = query.all()
    
    for record in records:
        dismiss_list = list(record.dismissed_by) if record.dismissed_by else []
        if user.username not in dismiss_list:
            dismiss_list.append(user.username)
            record.dismissed_by = dismiss_list
            
    db.commit()
    return {"success": True}
