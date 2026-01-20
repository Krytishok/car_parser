CREATE USER redash WITH PASSWORD 'redashpass';
CREATE DATABASE redash_metadata OWNER redash;
GRANT ALL PRIVILEGES ON DATABASE redash_metadata TO redash;