ALTER TABLE run_events ADD COLUMN progress_current INTEGER;
ALTER TABLE run_events ADD COLUMN progress_total INTEGER;
ALTER TABLE run_events ADD COLUMN severity TEXT DEFAULT 'info';
