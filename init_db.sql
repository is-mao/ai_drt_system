-- DRT System MySQL Schema
-- Run: mysql -u root -p < init_db.sql

CREATE DATABASE IF NOT EXISTS drt_system DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE drt_system;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login DATETIME NULL,
    INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Defect reports table
CREATE TABLE IF NOT EXISTS defect_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bu VARCHAR(10) NOT NULL,
    week_number VARCHAR(20) NULL,
    pcap_n VARCHAR(100) NULL,
    station VARCHAR(100) NULL,
    server VARCHAR(100) NULL,
    sn VARCHAR(100) NULL,
    record_time DATETIME NULL,
    failure TEXT NULL,
    defect_class VARCHAR(50) NULL,
    defect_value VARCHAR(255) NULL,
    root_cause TEXT NULL,
    action TEXT NULL,
    pn VARCHAR(100) NULL,
    component_sn VARCHAR(100) NULL,
    log_content LONGTEXT NULL,
    ai_root_cause TEXT NULL,
    created_by VARCHAR(64) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_bu (bu),
    INDEX idx_defect_class (defect_class),
    INDEX idx_station (station),
    INDEX idx_record_time (record_time),
    INDEX idx_week (week_number),
    INDEX idx_sn (sn),
    FULLTEXT INDEX ft_failure (failure),
    FULLTEXT INDEX ft_log (log_content)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- System config table
CREATE TABLE IF NOT EXISTS system_config (
    config_key VARCHAR(100) PRIMARY KEY,
    config_value TEXT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO system_config (config_key, config_value) VALUES ('gemini_api_key', '');
