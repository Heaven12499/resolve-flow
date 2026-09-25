CREATE DATABASE IF NOT EXISTS resolveflow_business CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS resolveflow_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON resolveflow_business.* TO 'resolve_flow'@'%';
GRANT ALL PRIVILEGES ON resolveflow_ai.* TO 'resolve_flow'@'%';
FLUSH PRIVILEGES;
