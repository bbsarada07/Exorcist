"""Deletion audit engine for "Ghost Data Still Exists".

Pipeline (each stage is a small, separately testable "agent"):
  parsers   -> unified fact table from every evidence format
  identity  -> who is the subject (current + historical identifiers)
  linker    -> which resources/activity belong to which case
  timeline  -> resource state at audit_at
  policy    -> required treatment per resource (deletion_rules.csv)
  planner   -> ordered FINDING / REMEDIATION / VERIFICATION steps
  simulator -> proof that the plan reaches a compliant state
  validator -> strict output.csv contract checks
"""
