-- Add grading fields to exam_scores table
-- Run this migration to add support for manual grading and result publishing

ALTER TABLE exam_scores 
ADD COLUMN IF NOT EXISTS is_graded BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS results_published BOOLEAN DEFAULT FALSE;

-- Update existing records to have results published by default (for backward compatibility)
UPDATE exam_scores 
SET is_graded = FALSE, 
    results_published = TRUE 
WHERE is_graded IS NULL OR results_published IS NULL;

-- Add indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_exam_scores_is_graded ON exam_scores(is_graded);
CREATE INDEX IF NOT EXISTS idx_exam_scores_results_published ON exam_scores(results_published);

COMMENT ON COLUMN exam_scores.is_graded IS 'Whether manual grading is complete for essay questions';
COMMENT ON COLUMN exam_scores.results_published IS 'Whether results are visible to the student';
