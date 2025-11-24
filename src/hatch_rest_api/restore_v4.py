"""
Hatch Restore V4 device class.

RestoreV4 is functionally identical to RestoreV5, so we inherit all behavior.
This separate class exists to provide accurate device identification in integrations.
"""

from .restore_v5 import RestoreV5


class RestoreV4(RestoreV5):
    """Hatch Restore V4 device - inherits all functionality from RestoreV5."""
    pass
