"""Static vocabulary: no case ids, labels, emails or file names live here, only domain mappings."""
from __future__ import annotations

from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = CODE_DIR.parent
DATASET_DIR = REPO_ROOT / "dataset"
OUT_DIR = CODE_DIR / "out"
CACHE_DIR = CODE_DIR / "cache"

# Resource-id prefix -> owning system. Every resource family in the data is prefixed consistently.
PREFIX_SYSTEM = {
    "account": "account_service",
    "search": "search_service",
    "analytics": "analytics_platform",
    "support": "support_platform",
    "export": "export_service",
    "data_flow": "integration_service",
    "backup": "backup_service",
    "audit_record": "security_service",
    "tombstone": "identity_service",
    "legal_hold": "legal_service",
    "marketing": "marketing_platform",
    "object": "object_storage",
    "cache": "cache_service",
    "email_delivery": "email_delivery_service",
}

# Default policy category per system when no stronger signal exists.
SYSTEM_DEFAULT_CATEGORY = {
    "account_service": "USER_PROFILE",
    "search_service": "SEARCH_INDEX_ENTRY",
    "analytics_platform": "ANALYTICS_PROFILE",
    "support_platform": "SUPPORT_MESSAGE",
    "export_service": "USER_EXPORT",
    "integration_service": "DATA_FLOW",
    "backup_service": "BACKUP_ARCHIVE",
    "security_service": "SECURITY_AUDIT_LOG",
    "identity_service": "ACCOUNT_TOMBSTONE",
    "legal_service": "LEGAL_HOLD_RECORD",
    "marketing_platform": "MARKETING_PROFILE",
    "object_storage": "SUPPORT_ATTACHMENT",
    "cache_service": "CACHE_ENTRY",
    "email_delivery_service": "EMAIL_DELIVERY_LOG",
}

# Collection / table names that state the category explicitly.
COLLECTION_CATEGORY = {
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
    "retained_order_records": "LEGAL_HOLD_RECORD",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "security_audit_records": "SECURITY_AUDIT_LOG",
    "backup_catalog": "BACKUP_ARCHIVE",
    "backup_restore_entries": "BACKUP_ARCHIVE",
    "connector_configurations": "DATA_FLOW",
    "connector_subscriptions": "DATA_FLOW",
    "customer_export_jobs": "USER_EXPORT",
    "customer_exports": "USER_EXPORT",
}

# What treatment the deletion worker's attempted operation implies (Phase 0: matches gold on every sample).
WORKER_OP_TREATMENT = {
    "DELETE_RECORD": "DELETE",
    "REDACT_RECORD": "REDACT",
    "ANONYMIZE_RECORD": "ANONYMIZE",
    "DISABLE_DATA_FLOW": "DISABLE",
    "CHECK_DATA_FLOW": "DISABLE",
    "BLOCK_RESTORE": "BLOCK",
    "CHECK_RESTORE_ACCESS": "BLOCK",
    "RETAIN_RECORD": "RETAIN",
}

# Category a worker DELETE implies on systems whose default is not a DELETE category.
DELETE_OVERRIDE_CATEGORY = {
    "analytics_platform": "SECONDARY_IDENTIFIER",
    "support_platform": "SUPPORT_ATTACHMENT",
}

# Reported workflow status -> the worker result it normally mirrors (soft signal for the linker).
CLAIM_RESULT = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}

# Allowed step vocabulary, in the exact order of the problem statement.
PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
OPERATION_ORDER = {
    "FINDING": ["REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK"],
    "REMEDIATION": ["DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD"],
    "VERIFICATION": ["VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
                     "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED"],
}
OPERATION_STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE", "REPORT_RESTORE_RISK": "ACTIVE",
    "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED", "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT", "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}

# USP 6 exposure heuristic (not a financial estimate).
RISK_WEIGHTS = {
    "category_sensitivity": {
        "USER_PROFILE": 5, "SUPPORT_ATTACHMENT": 5, "USER_EXPORT": 5, "ACCOUNT_TOMBSTONE": 4,
        "SUPPORT_MESSAGE": 3, "SEARCH_INDEX_ENTRY": 3, "ANALYTICS_PROFILE": 2, "SECONDARY_IDENTIFIER": 3,
        "MARKETING_PROFILE": 3, "EMAIL_DELIVERY_LOG": 2, "CACHE_ENTRY": 1, "PRODUCT_TELEMETRY": 2,
    },
    "active_flow": 4,
    "restore_path": 3,
    "per_extra_system": 1.5,
}
REVIEW_CONFIDENCE_THRESHOLD = 0.6
