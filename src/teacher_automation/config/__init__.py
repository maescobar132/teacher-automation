"""
Configuration module.

Handles loading and validation of course configurations, credentials,
and system settings.
"""

from .loader import ConfigLoader
from .models import CourseConfig, GradingConfig

__all__ = ["ConfigLoader", "CourseConfig", "GradingConfig"]
