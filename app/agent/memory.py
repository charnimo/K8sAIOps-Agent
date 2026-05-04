"""Memory initialization helper and utilities."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class IncidentMemory:
    """In-memory storage for incident context during graph execution.

    Used by monitoring and user graphs to share incident data.
    """

    def __init__(self):
        """Initialize memory store."""
        self.incidents: Dict[str, Dict[str, Any]] = {}

    def store_incident(self, incident_id: str, data: Dict[str, Any]) -> None:
        """Store incident data in memory.

        Args:
            incident_id: Unique incident identifier
            data: Incident data dict
        """
        self.incidents[incident_id] = data
        logger.info(f"Stored incident {incident_id} in memory")

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve incident data from memory.

        Args:
            incident_id: Unique incident identifier

        Returns:
            Incident data dict or None if not found
        """
        return self.incidents.get(incident_id)

    def update_incident(self, incident_id: str, data: Dict[str, Any]) -> None:
        """Update existing incident data.

        Args:
            incident_id: Unique incident identifier
            data: New incident data
        """
        if incident_id in self.incidents:
            self.incidents[incident_id].update(data)
            logger.info(f"Updated incident {incident_id} in memory")
        else:
            logger.warning(f"Incident {incident_id} not found in memory")

    def delete_incident(self, incident_id: str) -> bool:
        """Delete incident from memory.

        Args:
            incident_id: Unique incident identifier

        Returns:
            True if deleted, False if not found
        """
        if incident_id in self.incidents:
            del self.incidents[incident_id]
            logger.info(f"Deleted incident {incident_id} from memory")
            return True
        return False

    def list_incidents(self) -> list:
        """Get list of all incident IDs in memory.

        Returns:
            List of incident IDs
        """
        return list(self.incidents.keys())


# Global memory instance
_incident_memory: Optional[IncidentMemory] = None


def get_incident_memory() -> IncidentMemory:
    """Get or create global incident memory instance.

    Returns:
        IncidentMemory instance
    """
    global _incident_memory
    if _incident_memory is None:
        _incident_memory = IncidentMemory()
    return _incident_memory
