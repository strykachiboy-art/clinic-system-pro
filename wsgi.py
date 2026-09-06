import os
from app import create_app

app = create_app(os.environ.get("FLASK_ENV", "production"))

if __name__ == "__main__":
    app.run()
    

# $env:FLASK_APP = "wsgi.py"
# flask --app run.py db init

class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    __table_args__ = (
        db.CheckConstraint(
            "start_date <= end_date",
            name="ck_leave_requests_valid_period",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    staff_id = db.Column(
        db.Integer,
        db.ForeignKey("staff.id"),
        nullable=False,
        index=True,
    )

    leave_type = db.Column(
        db.Enum(LeaveType),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.Enum(LeaveStatus),
        default=LeaveStatus.PENDING,
        nullable=False,
        index=True,
    )

    start_date = db.Column(
        db.Date,
        nullable=False,
    )

    end_date = db.Column(
        db.Date,
        nullable=False,
    )

    reason = db.Column(
        db.Text,
        nullable=True,
    )

    reviewed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    reviewed_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        default=_utcnow,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    staff = db.relationship(
        "Staff",
        back_populates="leave_requests",
        foreign_keys=[staff_id],
    )

    reviewed_by_user = db.relationship(
        "User",
        foreign_keys=[reviewed_by_user_id],
    )

    def __repr__(self):
        return (
            f"<LeaveRequest Staff {self.staff_id} "
            f"({self.status.value})>"
        )