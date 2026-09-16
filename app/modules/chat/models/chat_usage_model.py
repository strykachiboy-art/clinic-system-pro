from datetime import date

from app.extensions import db


class ChatUsage(db.Model):
    __tablename__ = "chat_usage"

    __table_args__ = (
        db.UniqueConstraint(
            "clinic_id",
            "user_id",
            "usage_date",
            name="uq_chat_usage_clinic_user_date",
        ),
        db.CheckConstraint(
            "direct_created >= 0",
            name="ck_chat_usage_direct_created_nonnegative",
        ),
        db.CheckConstraint(
            "group_created >= 0",
            name="ck_chat_usage_group_created_nonnegative",
        ),
        db.CheckConstraint(
            "department_created >= 0",
            name="ck_chat_usage_department_created_nonnegative",
        ),
        db.CheckConstraint(
            "team_created >= 0",
            name="ck_chat_usage_team_created_nonnegative",
        ),
        db.Index(
            "ix_chat_usage_clinic_date",
            "clinic_id",
            "usage_date",
        ),
        db.Index(
            "ix_chat_usage_user_date",
            "user_id",
            "usage_date",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    usage_date = db.Column(
        db.Date,
        nullable=False,
        default=date.today,
        index=True,
    )

    direct_created = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    group_created = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    department_created = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    team_created = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    def __repr__(self):
        return (
            f"<ChatUsage "
            f"id={self.id} "
            f"clinic_id={self.clinic_id} "
            f"user_id={self.user_id} "
            f"usage_date={self.usage_date}>"
        )