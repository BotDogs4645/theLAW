"""
Enums and constants for the LAW bot
"""

from enum import Enum

class SubTeam(Enum):
    """Enum for subteam values"""
    SOFTWARE_ELECTRONICS = "Software & Electronics"
    MECHANICAL_DESIGN = "Mechanical & Design"
    MEDIA_MARKETING = "Media & Marketing"
    STRATEGY_SCOUTING = "Strategy & Scouting"
    FULL_TEAM = "Full Team"
    VARSITY = "Varsity"
    JV = "JV"
    VARSITY_JV = "Varsity + JV"
    TRAVEL_TEAM = "Travel Team"
    
    @classmethod
    def get_all_values(cls):
        """Get all subteam values as a list"""
        return [member.value for member in cls]
    
    @classmethod
    def is_valid(cls, value):
        """Check if a value is a valid subteam"""
        return value in cls.get_all_values()
    
    @classmethod
    def from_string(cls, value):
        """Get enum member from string value"""
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Invalid subteam: {value}")


