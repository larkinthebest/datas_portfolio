# Data model

Every business row carries `tenant_id`, timestamps and a stable UUID where applicable.

- Source: `data_sources`, `drive_folders`, `drive_files`, `sync_jobs`, `processing_jobs`.
- Documents: `documents`, `document_versions`, `document_pages`, `document_chunks`,
  `document_tables`, `document_sheets`, `extracted_fields`, `financial_documents`.
- Banking: `bank_accounts`, `bank_transactions`, `reconciliation_candidates`,
  `reconciliation_matches`.
- Decisions: `calculations`, `calculation_inputs`, `calculation_results`, `legal_rules`,
  `legal_rule_versions`, `declaration_fields`, `declaration_values`.
- Control: `tenants`, `users`, `user_roles`, `rag_queries`, `rag_answer_records`, `audit_events`.

Original extraction and manual overrides are separate fields. Approval state is never inferred from
model confidence. Monetary columns use fixed-precision `NUMERIC`, never floating point.

