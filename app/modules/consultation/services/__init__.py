from app.modules.consultation.services.consultation_service import (
	cancel_consultation,
	complete_consultation,
	create_consultation_template,
	get_active_templates,
	get_consultation,
	get_consultation_template,
	get_consultations_for_patient,
	get_consultations_for_staff,
	get_patients_seen_by_staff,
	start_consultation,
	update_consultation_note,
)

__all__ = [
	"cancel_consultation",
	"complete_consultation",
	"create_consultation_template",
	"get_active_templates",
	"get_consultation",
	"get_consultation_template",
	"get_consultations_for_patient",
	"get_consultations_for_staff",
	"get_patients_seen_by_staff",
	"start_consultation",
	"update_consultation_note",
]
