CREATE TABLE IF NOT EXISTS concepts (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT,
    status TEXT,
    trust_tier TEXT NOT NULL,
    generated_at TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    domain TEXT
);

CREATE INDEX IF NOT EXISTS idx_concepts_type ON concepts(type);
CREATE INDEX IF NOT EXISTS idx_concepts_domain ON concepts(domain);

CREATE TABLE IF NOT EXISTS links (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    PRIMARY KEY (from_id, to_id)
);

CREATE INDEX IF NOT EXISTS idx_links_from ON links(from_id);

CREATE TABLE IF NOT EXISTS intake_items (
    id TEXT PRIMARY KEY,
    path TEXT,
    content TEXT,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    parent_id TEXT,
    error_message TEXT,
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intake_state ON intake_items(state);
CREATE INDEX IF NOT EXISTS idx_intake_kind ON intake_items(kind);
CREATE INDEX IF NOT EXISTS idx_intake_parent ON intake_items(parent_id);
CREATE INDEX IF NOT EXISTS idx_intake_path ON intake_items(path);

CREATE TABLE IF NOT EXISTS intake_item_concepts (
    intake_item_id TEXT NOT NULL,
    concept_id TEXT NOT NULL,
    PRIMARY KEY (intake_item_id, concept_id)
);
