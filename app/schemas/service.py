"""Service taxonomy — individual (lawyer, etc.) vs group (ambulance, police) later."""

from enum import StrEnum


class ServiceKind(StrEnum):
    INDIVIDUAL = "individual"
    GROUP = "group"


class IndividualServiceType(StrEnum):
    LAWYER = "lawyer"
    # Future: DOCTOR = "doctor", etc.


class GroupServiceType(StrEnum):
    AMBULANCE = "ambulance"
    POLICE = "police"
    SAFETY_RELIEF = "safety_relief"
