from datetime import datetime, timezone
from app.extensions import db
from app.core.enums.staff_enums import StaffRole, StaffStatus, LeaveType, LeaveStatus


def _utcnow():
    return datetime.now(timezone.utc)

class Staff(db.Model):
    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)
    user_id = db.Column(db.Integer, nullable=True)

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    role = db.Column(db.Enum(StaffRole), nullable=False)
    specialty = db.Column(db.String(100), nullable=True)

    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)

    status = db.Column(db.Enum(StaffStatus), default=StaffStatus.ACTIVE, nullable=False)
    hired_at = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    clinic = db.relationship("Clinic", back_populates="staff")

    appointments = db.relationship("Appointment", back_populates="staff")
    consultations = db.relationship("Consultation", back_populates="staff")
    lab_orders = db.relationship("LabOrder", back_populates="ordered_by")
    prescriptions = db.relationship("Prescription", back_populates="prescribed_by")
    dispense_records = db.relationship("DispenseRecord", back_populates="dispensed_by")
    stock_movements = db.relationship("StockMovement", back_populates="performed_by")
    generated_reports = db.relationship("GeneratedReport", back_populates="generated_by")

    payroll_records = db.relationship("PayrollRecord", back_populates="staff", cascade="all, delete-orphan")
    leave_requests = db.relationship("LeaveRequest", back_populates="staff", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Staff {self.first_name} {self.last_name} ({self.role.value})>"


class PayrollRecord(db.Model):
    __tablename__ = "payroll_records"

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)

    pay_period_start = db.Column(db.Date, nullable=False)
    pay_period_end = db.Column(db.Date, nullable=False)

    base_salary = db.Column(db.Numeric(10, 2), nullable=False)
    bonuses = db.Column(db.Numeric(10, 2), default=0)
    deductions = db.Column(db.Numeric(10, 2), default=0)
    net_pay = db.Column(db.Numeric(10, 2), nullable=False)

    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    staff = db.relationship("Staff", back_populates="payroll_records")

    def __repr__(self):
        return f"<PayrollRecord Staff {self.staff_id} ({self.pay_period_start} - {self.pay_period_end})>"


class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)

    leave_type = db.Column(db.Enum(LeaveType), nullable=False)
    status = db.Column(db.Enum(LeaveStatus), default=LeaveStatus.PENDING, nullable=False)

    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, nullable=True)

    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)

    staff = db.relationship("Staff", back_populates="leave_requests", foreign_keys=[staff_id])
    reviewed_by = db.relationship("Staff", foreign_keys=[reviewed_by_id])

    def __repr__(self):
        return f"<LeaveRequest Staff {self.staff_id} ({self.status.value})>"