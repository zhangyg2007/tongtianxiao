-- M1 数据库初始化（仅首次建库时由 docker-entrypoint-initdb.d 自动执行）
-- M2 阶段的业务库(business)与数据集库(dataset)建表脚本另行提供

-- 启用 pgvector，为 RAG 集成的语料向量表(corpus_embeddings)做准备
CREATE EXTENSION IF NOT EXISTS vector;
