-- ============================================================
-- 001_core_schema.sql
-- P0 统一数据模型建表（来源：.trae/documents/前端与产品形态升级设计.md §2.5）
--
-- 实体：
--   core.object            统一对象注册表（company/person/event → 稳定 object_id）
--   core.object_alias      对象别名
--   core.task / task_step  异步任务与步骤
--   core.evidence          证据（一等公民，含 fact/quote/置信度）
--   core.artifact*         产物（报告）+ 块 + 句级引用绑定 + 定位快照
--
-- 说明：
--   * 设计决策：只建 core.evidence，不建方案 A 的 kb.evidence（两者字段兼容，避免双写）
--   * 幂等：全部使用 IF NOT EXISTS，可重复执行
--   * gen_random_uuid() 为 PostgreSQL 13+ 内置，无需 pgcrypto
-- ============================================================

CREATE SCHEMA IF NOT EXISTS core;

-- ============================================================
-- 1. 统一对象注册表（对 kb.company / kb.person / kb.event 的抽象）
-- ============================================================
CREATE TABLE IF NOT EXISTS core.object (
    object_id     BIGSERIAL PRIMARY KEY,
    object_type   TEXT NOT NULL CHECK (object_type IN ('company','person','event')),
    ref_id        BIGINT,                       -- 指向 kb.company / kb.person / kb.event 的主键
    natural_key   TEXT,                         -- company: USCC；person: name_norm+company_id 哈希；event: cluster_key
    display_name  TEXT NOT NULL,                -- 展示名（公司全称 / 人名 / 事件标题）
    display_meta  TEXT,                         -- 消歧后缀：注册地+成立年（公司）、任职公司（人）
    scope_dept_id BIGINT,                       -- 归属部门（空=全部门可见）
    status        TEXT DEFAULT 'active',        -- active/merged/archived
    merged_into   BIGINT REFERENCES core.object,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (object_type, natural_key)
);

CREATE INDEX IF NOT EXISTS idx_obj_type_name ON core.object (object_type, display_name);
CREATE INDEX IF NOT EXISTS idx_obj_ref ON core.object (object_type, ref_id);

-- 对象别名（跨类型统一入口，便于搜索框一次查全）
CREATE TABLE IF NOT EXISTS core.object_alias (
    alias_id    BIGSERIAL PRIMARY KEY,
    object_id   BIGINT NOT NULL REFERENCES core.object ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    alias_norm  TEXT NOT NULL,
    source      TEXT,
    UNIQUE (object_id, alias_norm)
);
CREATE INDEX IF NOT EXISTS idx_obj_alias_norm ON core.object_alias (alias_norm);

-- ============================================================
-- 2. 任务（异步执行的基本单位）
-- ============================================================
CREATE TABLE IF NOT EXISTS core.task (
    task_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_line   TEXT NOT NULL CHECK (product_line IN ('dd','pr')),  -- dd=背调 pr=舆情
    task_type      TEXT NOT NULL,
                   -- dd: investment_dd / person_dd / partner_access
                   -- pr: event_trace / sentiment_watch / emergency_plan
    object_id      BIGINT REFERENCES core.object,
    parent_task_id UUID REFERENCES core.task,   -- 子任务（如背调里的"抓财报"）
    status         TEXT NOT NULL DEFAULT 'queued',
                   -- queued/running/waiting_input/succeeded/failed/canceled
    priority       SMALLINT NOT NULL DEFAULT 5, -- 0 最高
    progress       SMALLINT NOT NULL DEFAULT 0, -- 0-100
    stage          TEXT,                        -- 当前阶段（供前端显示中文）
    input          JSONB NOT NULL DEFAULT '{}', -- 模板参数、数据源开关、时间范围
    result         JSONB,                       -- 结构化结果摘要（评分卡分数等）
    error          JSONB,                       -- {code, message, trace_id}
    project_id     BIGINT,                      -- 所属项目（权限隔离）
    requested_by   BIGINT NOT NULL,
    idempotency_key TEXT UNIQUE,                -- 防重复提交
    worker_id      TEXT,
    heartbeat_at   TIMESTAMPTZ,                 -- 心跳，用于检测僵死任务
    created_at     TIMESTAMPTZ DEFAULT now(),
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_task_status ON core.task (status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_task_object ON core.task (object_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_project ON core.task (project_id, created_at DESC);

-- 任务步骤（细粒度进度与耗时归因）
CREATE TABLE IF NOT EXISTS core.task_step (
    step_id     BIGSERIAL PRIMARY KEY,
    task_id     UUID NOT NULL REFERENCES core.task ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    name        TEXT NOT NULL,              -- fetch_cninfo / parse_report / llm_chapter_3
    status      TEXT NOT NULL DEFAULT 'pending',
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    duration_ms INTEGER,
    detail      JSONB,                      -- 输入摘要、token 数、错误
    UNIQUE (task_id, seq)
);

-- ============================================================
-- 3. 证据（一等公民）
-- ============================================================
CREATE TABLE IF NOT EXISTS core.evidence (
    evidence_id   BIGSERIAL PRIMARY KEY,
    object_id     BIGINT NOT NULL REFERENCES core.object,
    task_id       UUID REFERENCES core.task ON DELETE SET NULL,   -- 可空=长期资产
    fact          TEXT NOT NULL,                 -- 归一化事实断言
    fact_type     TEXT NOT NULL,                 -- registration/penalty/litigation/finance/
                                                 -- bid/ip/sentiment/exec_change
    value_json    JSONB,                         -- {amount:2000000, currency:"CNY", date:"2024-03-12"}
    source_type   TEXT NOT NULL,                 -- gsxt/creditchina/court/cninfo/tianyancha/news/social
    source_name   TEXT,
    source_url    TEXT NOT NULL,
    doc_id        BIGINT,                        -- 指向 kb.kb_document（方案A §5.5）
    page_no       INTEGER,
    quote         TEXT,                          -- 原文片段，LLM 不可改写
    published_at  TIMESTAMPTZ,                   -- 内容发布时间
    captured_at   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- 抓取时间（与发布时间严格区分）
    confidence    SMALLINT NOT NULL DEFAULT 85 CHECK (confidence BETWEEN 0 AND 100),
    confidence_reason TEXT,
    verified_by   BIGINT,                        -- 人工复核人
    verified_at   TIMESTAMPTZ,
    verify_status TEXT DEFAULT 'auto',           -- auto/confirmed/rejected/needs_review
    content_hash  CHAR(64) NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (content_hash, source_url)
);

CREATE INDEX IF NOT EXISTS idx_ev_object ON core.evidence (object_id, fact_type, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_ev_task ON core.evidence (task_id);
CREATE INDEX IF NOT EXISTS idx_ev_verify ON core.evidence (verify_status) WHERE verify_status = 'needs_review';

-- ============================================================
-- 4. 产物（报告 / 简报 / 时间线）
-- ============================================================
CREATE TABLE IF NOT EXISTS core.artifact (
    artifact_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID NOT NULL REFERENCES core.task,
    object_id     BIGINT REFERENCES core.object,
    artifact_type TEXT NOT NULL,      -- report_html/report_pdf/report_md/brief/timeline/playbook_instance
    template_code TEXT,               -- investment_dd_v1 / person_dd_v1 / event_trace_v1
    version       INTEGER NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'draft',   -- draft/reviewing/final
    storage_path  TEXT,               -- 相对路径
    mime_type     TEXT,
    size_bytes    BIGINT,
    sha256        CHAR(64),
    title         TEXT,
    created_by    BIGINT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    finalized_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_art_task ON core.artifact (task_id);
CREATE INDEX IF NOT EXISTS idx_art_object ON core.artifact (object_id, created_at DESC);

CREATE TABLE IF NOT EXISTS core.artifact_block (
    block_id      BIGSERIAL PRIMARY KEY,
    artifact_id   UUID NOT NULL REFERENCES core.artifact ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    chapter_no    INTEGER,
    block_type    TEXT NOT NULL,      -- heading/paragraph/table/figure/list
    heading       TEXT,
    content_md    TEXT,               -- Markdown（编辑态）
    content_html  TEXT,               -- 渲染缓存
    updated_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (artifact_id, seq)
);

-- 句级引用绑定：报告里的哪一段、哪一句，引用了哪条证据
CREATE TABLE IF NOT EXISTS core.artifact_citation (
    citation_id   BIGSERIAL PRIMARY KEY,
    artifact_id   UUID NOT NULL REFERENCES core.artifact ON DELETE CASCADE,
    block_id      BIGINT NOT NULL REFERENCES core.artifact_block ON DELETE CASCADE,
    sentence_idx  INTEGER,            -- 段内第几句（从 0 起）
    marker        TEXT NOT NULL,      -- 正文中的角标文本，如 "E12"
    evidence_id   BIGINT NOT NULL REFERENCES core.evidence,
    checked       BOOLEAN DEFAULT FALSE,  -- 后校验是否通过（数字回查）
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE (artifact_id, block_id, marker)
);

CREATE INDEX IF NOT EXISTS idx_cit_evidence ON core.artifact_citation (evidence_id);

-- 定位快照（仅在 artifact 定稿时写入，用于 PDF 高亮）
CREATE TABLE IF NOT EXISTS core.artifact_anchor (
    anchor_id   BIGSERIAL PRIMARY KEY,
    citation_id BIGINT NOT NULL REFERENCES core.artifact_citation ON DELETE CASCADE,
    span_start  INTEGER,
    span_end    INTEGER,
    snapshot_hash CHAR(64)          -- 生成锚点时的 block 内容哈希，内容变了则锚点失效
);
