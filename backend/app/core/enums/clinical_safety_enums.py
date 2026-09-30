from enum import Enum


class ClinicalRuleScope(str, Enum):
    GLOBAL = "global"
    CLINIC = "clinic"
    DEPARTMENT = "department"


class ClinicalRuleType(str, Enum):
    DRUG_INTERACTION = "drug_interaction"
    ALLERGY_CONFLICT = "allergy_conflict"
    CONTRAINDICATION = "contraindication"
    MAX_DOSE = "max_dose"
    MIN_DOSE = "min_dose"
    AGE_RESTRICTION = "age_restriction"
    WEIGHT_RESTRICTION = "weight_restriction"
    PREGNANCY_RESTRICTION = "pregnancy_restriction"
    DUPLICATE_THERAPY = "duplicate_therapy"
    THERAPEUTIC_DUPLICATION = "therapeutic_duplication"
    LAB_CONFLICT = "lab_conflict"
    RENAL_FUNCTION = "renal_function"
    HEPATIC_FUNCTION = "hepatic_function"
    DIAGNOSIS_CONFLICT = "diagnosis_conflict"
    FREQUENCY_LIMIT = "frequency_limit"
    DURATION_LIMIT = "duration_limit"
    PATIENT_SPECIFIC_RESTRICTION = (
        "patient_specific_restriction"
    )


class ClinicalRuleSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ClinicalRuleAction(str, Enum):
    INFORM = "inform"
    ALERT = "alert"
    REQUIRE_ACKNOWLEDGEMENT = (
        "require_acknowledgement"
    )
    REQUIRE_JUSTIFICATION = (
        "require_justification"
    )
    BLOCK = "block"


class ClinicalAlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    OVERRIDDEN = "overridden"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class AlertAcknowledgementType(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    OVERRIDDEN = "overridden"