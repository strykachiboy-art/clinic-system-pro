from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from app.core.enums.audit_enums import AuditAction


class AuditLogCreateSchema(BaseModel):
    user_id: Optional[int] = Field(None, description="ID of the user performing the action")
    action: AuditAction = Field(..., description="The type of audit action performed")
    
    entity_type: str = Field(..., max_length=80, description="The model or entity being acted upon (e.g., 'Appointment')")
    entity_id: int = Field(..., description="Primary key ID of the entity")
    
    description: Optional[str] = Field(None, max_length=255, description="Human-readable description of the action")
    old_value: Optional[Dict[str, Any]] = Field(None, description="JSON dictionary of old values before change")
    new_value: Optional[Dict[str, Any]] = Field(None, description="JSON dictionary of new values after change")
    
    ip_address: Optional[str] = Field(None, max_length=45, description="IP address of the client")

    class Config:
        from_attributes = True


class AuditLogResponseSchema(AuditLogCreateSchema):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True