from datetime import datetime
from app.extensions import db
from app.core.enums.audit_enums import AuditAction


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.Enum(AuditAction), nullable=False)

    entity_type = db.Column(db.String(80), nullable=False)  
    entity_id = db.Column(db.Integer, nullable=False)

    description = db.Column(db.String(255), nullable=True)   
    old_value = db.Column(db.JSON, nullable=True)
    new_value = db.Column(db.JSON, nullable=True)

    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action.value} {self.entity_type}#{self.entity_id}>"