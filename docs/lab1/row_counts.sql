-- Row counts of the seeded database p06_handshake (Pair 06, SEED 6).
-- Read-only: only SELECT statements. Run from the repo root (see the command in the report/README).
USE p06_handshake;

SELECT 'Companies'           AS `table`, COUNT(*) AS `rows` FROM companies
UNION ALL SELECT 'Students',            COUNT(*) FROM students
UNION ALL SELECT 'Job postings',        COUNT(*) FROM jobs
UNION ALL SELECT 'Applications',        COUNT(*) FROM applications
UNION ALL SELECT 'Events',              COUNT(*) FROM events
UNION ALL SELECT 'Event registrations', COUNT(*) FROM event_registrations
UNION ALL SELECT 'Saved preferences',   COUNT(*) FROM student_preferences
UNION ALL SELECT 'Saved items',         COUNT(*) FROM saved_items
UNION ALL SELECT 'Student skills',      COUNT(*) FROM student_skills
UNION ALL SELECT 'Job skills',          COUNT(*) FROM job_skills;
