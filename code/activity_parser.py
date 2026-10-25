"""
System Activity Parser for Ghost Data Still Exists.
Parses system_activity.csv to index operational workflows, deletion worker executions,
connector syncs, and restore events.
"""

import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


@dataclass
class ActivityEvent:
    activity_id: str
    event_time: str
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


class ActivityParser:
    """Parses and indexes system_activity.csv."""

    def __init__(self, activity_csv_path: str):
        self.path = activity_csv_path
        self.activities: List[ActivityEvent] = []
        self.by_resource: Dict[str, List[ActivityEvent]] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return

        with open(self.path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                event = ActivityEvent(
                    activity_id=row['activity_id'],
                    event_time=row['event_time'],
                    event_type=row['event_type'],
                    source_system=row['source_system'],
                    target_system=row['target_system'],
                    resource_id=row['resource_id'],
                    reported_result=row['reported_result'],
                    details=row['details']
                )
                self.activities.append(event)
                self.by_resource.setdefault(event.resource_id, []).append(event)

    def get_events_for_resource(self, resource_id: str) -> List[ActivityEvent]:
        return self.by_resource.get(resource_id, [])

    def get_deletion_worker_events_in_range(self, start_time: str, end_time: str) -> List[ActivityEvent]:
        return [
            a for a in self.activities
            if a.source_system == 'deletion_worker' and start_time <= a.event_time <= end_time
        ]
