CREATE DATABASE IF NOT EXISTS pr_review_agent
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE pr_review_agent;

-- This schema is dropped and recreated from scratch every time
-- scripts/init_db.py runs - it is not meant to be a migration.
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS reasoning_steps;
DROP TABLE IF EXISTS review_comments;
DROP TABLE IF EXISTS merge_conflicts;
DROP TABLE IF EXISTS commit_files;
DROP TABLE IF EXISTS commits;
DROP TABLE IF EXISTS prs;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE prs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pexgit_pr_id VARCHAR(64) NOT NULL UNIQUE,
    repository VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    author VARCHAR(128) NOT NULL,
    source_branch VARCHAR(255) NOT NULL,
    target_branch VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    -- pending | reviewed | needs_batching (commit history too large for the
    -- current single-shot context window, see agent/context_builder.py) | error
    review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    reviewed_at DATETIME NULL,
    review_summary TEXT
);

CREATE TABLE commits (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pr_id INT NOT NULL,
    commit_sha VARCHAR(64) NOT NULL,
    commit_order INT NOT NULL,
    author VARCHAR(128) NOT NULL,
    message TEXT NOT NULL,
    committed_at DATETIME NOT NULL,
    FOREIGN KEY (pr_id) REFERENCES prs(id) ON DELETE CASCADE,
    UNIQUE KEY uniq_pr_commit (pr_id, commit_sha)
);

CREATE TABLE commit_files (
    id INT PRIMARY KEY AUTO_INCREMENT,
    commit_id INT NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    change_type VARCHAR(16) NOT NULL DEFAULT 'modified',
    diff_text MEDIUMTEXT NOT NULL,
    FOREIGN KEY (commit_id) REFERENCES commits(id) ON DELETE CASCADE
);

CREATE TABLE merge_conflicts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pr_id INT NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    detail TEXT NOT NULL,
    FOREIGN KEY (pr_id) REFERENCES prs(id) ON DELETE CASCADE
);

CREATE TABLE review_comments (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pr_id INT NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    line_hint VARCHAR(64),
    severity VARCHAR(16) NOT NULL DEFAULT 'medium',
    category VARCHAR(32) NOT NULL DEFAULT 'bug',
    comment TEXT NOT NULL,
    suggested_fix TEXT,
    introduced_in_commit VARCHAR(64),
    FOREIGN KEY (pr_id) REFERENCES prs(id) ON DELETE CASCADE
);

CREATE TABLE reasoning_steps (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pr_id INT NOT NULL,
    step_number INT NOT NULL,
    thought TEXT,
    action VARCHAR(64) NOT NULL,
    action_input TEXT,
    observation MEDIUMTEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pr_id) REFERENCES prs(id) ON DELETE CASCADE
);
