from enum import Enum


class FeedbackReactionType(str, Enum):
    HELPFUL = "helpful"
    APPRECIATED = "appreciated"
    NOT_HELPFUL = "not_helpful"