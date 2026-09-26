ALTER TABLE ai_tasks
    ADD COLUMN model_source VARCHAR(50) NULL AFTER result_payload;

UPDATE ai_tasks
SET model_source = JSON_UNQUOTE(JSON_EXTRACT(result_payload, '$.model_source'))
WHERE result_payload IS NOT NULL
  AND JSON_VALID(result_payload)
  AND JSON_EXTRACT(result_payload, '$.model_source') IS NOT NULL;
