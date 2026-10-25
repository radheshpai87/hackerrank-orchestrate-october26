"""
Data models and constants for Ghost Data Still Exists deletion audit agent.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
import json

# Phase order defined in problem statement
PHASE_ORDER = {
    'FINDING': 1,
    'REMEDIATION': 2,
    'VERIFICATION': 3
}

# Operation order defined in problem statement
OP_ORDER = {
    'FINDING': {
        'REPORT_REMAINING_RECORD': 1,
        'REPORT_EXPOSED_PII': 2,
        'REPORT_ACTIVE_DATA_FLOW': 3,
        'REPORT_RESTORE_RISK': 4
    },
    'REMEDIATION': {
        'DISABLE_DATA_FLOW': 1,
        'BLOCK_RESTORE': 2,
        'DELETE_RECORD': 3,
        'REDACT_RECORD': 4,
        'ANONYMIZE_RECORD': 5
    },
    'VERIFICATION': {
        'VERIFY_RECORD_ABSENT': 1,
        'VERIFY_RECORD_PRESENT': 2,
        'VERIFY_RECORD_REDACTED': 3,
        'VERIFY_RECORD_ANONYMIZED': 4,
        'VERIFY_DATA_FLOW_DISABLED': 5,
        'VERIFY_RESTORE_BLOCKED': 6
    }
}

# Operation to expected state mapping
OP_TO_STATE = {
    'REPORT_REMAINING_RECORD': 'PRESENT',
    'REPORT_EXPOSED_PII': 'PRESENT',
    'REPORT_ACTIVE_DATA_FLOW': 'ACTIVE',
    'REPORT_RESTORE_RISK': 'ACTIVE',
    'DISABLE_DATA_FLOW': 'DISABLED',
    'BLOCK_RESTORE': 'BLOCKED',
    'DELETE_RECORD': 'ABSENT',
    'REDACT_RECORD': 'REDACTED',
    'ANONYMIZE_RECORD': 'ANONYMIZED',
    'VERIFY_RECORD_ABSENT': 'ABSENT',
    'VERIFY_RECORD_PRESENT': 'PRESENT',
    'VERIFY_RECORD_REDACTED': 'REDACTED',
    'VERIFY_RECORD_ANONYMIZED': 'ANONYMIZED',
    'VERIFY_DATA_FLOW_DISABLED': 'DISABLED',
    'VERIFY_RESTORE_BLOCKED': 'BLOCKED'
}

# Standard system IDs
SYSTEM_ACCOUNT = 'account_service'
SYSTEM_SEARCH = 'search_service'
SYSTEM_SUPPORT = 'support_platform'
SYSTEM_ANALYTICS = 'analytics_platform'
SYSTEM_INTEGRATION = 'integration_service'
SYSTEM_BACKUP = 'backup_service'
SYSTEM_SECURITY = 'security_service'
SYSTEM_EXPORT = 'export_service'
SYSTEM_IDENTITY = 'identity_service'


@dataclass
class Step:
    step_no: int
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_no": self.step_no,
            "phase": self.phase,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id
        }

    def sort_key(self):
        return (
            PHASE_ORDER.get(self.phase, 99),
            OP_ORDER.get(self.phase, {}).get(self.operation, 99),
            self.system_id,
            self.resource_id
        )


@dataclass
class CaseAuditResult:
    case_id: str
    deletion_status: str
    steps: List[Step] = field(default_factory=list)

    def to_csv_row(self) -> Dict[str, str]:
        # Steps must be numbered 1..N after final sort
        serialized_steps = [s.to_dict() for s in self.steps]
        return {
            "case_id": self.case_id,
            "deletion_status": self.deletion_status,
            "steps_json": json.dumps(serialized_steps, separators=(',', ':'))
        }
