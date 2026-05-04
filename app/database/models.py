from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, JSON, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    profile_picture = Column(String, nullable=True) # Optional URL/Path
    permissions = Column(String, default='{"global": [], "namespaces": {}}')
    is_god_mode = Column(Boolean, default=False) 

    # Relationship for later, so you can fetch all conversations for a user
    conversations = relationship("Conversation", back_populates="owner")


class PermissionCatalog(Base):
    __tablename__ = "permission_catalog"

    permission_key = Column(String, primary_key=True, index=True)
    label = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_dangerous = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    scope = Column(String, default="namespace")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="conversations")
    messages = relationship("ChatHistory", back_populates="conversation", cascade="all, delete")

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    sender = Column(String) # "user" or "agent"
    message = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class IncidentRecord(Base):
    """Incident records from automated monitoring and diagnosis."""

    __tablename__ = "incident_records"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String, unique=True, index=True)
    trace_id = Column(String, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)

    # Resource information
    resource_type = Column(String)  # Pod, Deployment, etc.
    resource_name = Column(String, index=True)
    namespace = Column(String, index=True)
    reason = Column(String)  # CrashLoopBackOff, OOMKilled, etc.

    # Severity and ownership
    severity = Column(String)  # INFO, WARNING, CRITICAL
    teams = Column(JSON, default=list)  # List of team names

    # Summaries
    summary = Column(String)
    detailed_summary = Column(Text, nullable=True)

    # Investigation data
    collected_diagnostics = Column(JSON, default=dict)
    tools_called = Column(JSON, default=list)

    # LLM analysis
    llm_reasoning = Column(Text, nullable=True)
    root_cause_analysis = Column(JSON, nullable=True)  # RootCauseAnalysis dict
    suggested_actions = Column(JSON, default=list)  # List of SuggestedAction dicts

    # Lifecycle
    status = Column(String, default="OPEN")  # OPEN, INVESTIGATING, RESOLVED, CLOSED
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    # Audit trail
    audit_trail = Column(JSON, default=list)

    # Relationships
    conversation = relationship("Conversation", foreign_keys=[conversation_id])

