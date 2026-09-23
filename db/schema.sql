CREATE DATABASE IF NOT EXISTS pr_review_agent
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE pr_review_agent;

CREATE TABLE IF NOT EXISTS prs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pexgit_pr_id VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    author VARCHAR(128) NOT NULL,
    source_branch VARCHAR(255) NOT NULL,
    target_branch VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    reviewed_at DATETIME NULL,
    review_summary TEXT
);

CREATE TABLE IF NOT EXISTS pr_files (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pr_id INT NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    change_type VARCHAR(16) NOT NULL DEFAULT 'modified',
    diff_text MEDIUMTEXT NOT NULL,
    FOREIGN KEY (pr_id) REFERENCES prs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS merge_conflicts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pr_id INT NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    detail TEXT NOT NULL,
    FOREIGN KEY (pr_id) REFERENCES prs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_comments (
    id INT PRIMARY KEY AUTO_INCREMENT,
    pr_id INT NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    line_hint VARCHAR(64),
    severity VARCHAR(16) NOT NULL DEFAULT 'medium',
    category VARCHAR(32) NOT NULL DEFAULT 'bug',
    comment TEXT NOT NULL,
    suggested_fix TEXT,
    FOREIGN KEY (pr_id) REFERENCES prs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reasoning_steps (
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

CREATE TABLE IF NOT EXISTS code_chunks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    file_path VARCHAR(512) NOT NULL,
    chunk_index INT NOT NULL,
    content MEDIUMTEXT NOT NULL,
    embedding JSON NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_file_chunk (file_path, chunk_index)
);
