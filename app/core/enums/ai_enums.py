from enum import Enum


class AIFeature(str, Enum):
    DRUG_INTERACTION_CHECK = "drug_interaction_check"
    TRIAGE_ASSISTANT = "triage_assistant"
    LAB_RESULT_INTERPRETER = "lab_result_interpreter"