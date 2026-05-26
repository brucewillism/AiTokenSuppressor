-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create indexes after tables are created by SQLAlchemy
-- IVFFlat indexes require data; created via init script
