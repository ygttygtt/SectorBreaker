UPDATE projects
SET status = 'archived', project_mode = 'domain_knowledge', updated_at = CURRENT_TIMESTAMP
WHERE project_mode = 'talent_demand';

DELETE FROM artifacts
WHERE artifact_type IN (
    'talent_demand_overview',
    'talent_role_profile',
    'talent_skill_matrix',
    'talent_company_distribution',
    'talent_salary_experience',
    'talent_capability_model',
    'talent_portfolio_requirements',
    'talent_unresolved_questions'
);

DELETE FROM evidence_fts
WHERE id IN (SELECT id FROM evidence WHERE source_channel = 'boss_job');

DELETE FROM evidence
WHERE source_channel = 'boss_job';
