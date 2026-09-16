from enum import Enum


class ConversationType(str, Enum):
    DIRECT = "direct"
    GROUP = "group"
    PATIENT = "patient"
    DEPARTMENT = "department"
    TEAM = "team"


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


class ParticipantStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    LEFT = "left"
    REMOVED = "removed"


class ParticipantRole(str, Enum):
    MEMBER = "member"
    ADMIN = "admin"


class MessageType(str, Enum):
    """
    Defines the logical type of a chat message.

    AttachmentType describes the actual attached file/media,
    while MessageType describes how the message itself is represented.
    """

    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    EDITED = "edited"
    DELETED = "deleted"


class MessagePriority(str, Enum):
    NORMAL = "normal"
    URGENT = "urgent"
    STAT = "stat"


class AttachmentType(str, Enum):
    FILE = "file"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class MentionType(str, Enum):
    USER = "user"
    STAFF = "staff"
    PATIENT = "patient"
    GROUP = "group"


class ReadReceiptStatus(str, Enum):
    DELIVERED = "delivered"
    READ = "read"


class PinStatus(str, Enum):
    PINNED = "pinned"
    UNPINNED = "unpinned"