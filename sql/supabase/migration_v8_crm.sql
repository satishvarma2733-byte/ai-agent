-- ====================================================================
-- migration_v8_crm.sql
-- Upgrades aVn to support CRM Leads, Activities, Workflows and Roles
-- ====================================================================

-- 1. User Roles / Profiles Table
CREATE TABLE IF NOT EXISTS crm_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL DEFAULT 'Agent' CHECK (role IN ('Admin', 'Manager', 'Agent'))
);

-- Insert a default admin for demonstration
INSERT INTO crm_users (name, email, role)
VALUES ('Admin Demo', 'admin@ewings.com', 'Admin')
ON CONFLICT (email) DO NOTHING;

-- 2. CRM Leads Table
CREATE TABLE IF NOT EXISTS crm_leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    email TEXT,
    company TEXT DEFAULT 'eWings Abroad',
    status TEXT NOT NULL DEFAULT 'New' CHECK (status IN ('New', 'Contacted', 'Follow-up', 'Interested', 'Converted', 'Lost')),
    score TEXT NOT NULL DEFAULT 'Warm' CHECK (score IN ('Hot', 'Warm', 'Cold')),
    score_explanation TEXT,
    assigned_agent TEXT DEFAULT 'Unassigned',
    state TEXT,
    neet_score INT,
    rank INT,
    budget TEXT,
    parent_involved BOOLEAN DEFAULT FALSE,
    country_preference TEXT,
    follow_up_date DATE,
    objection TEXT,
    session_booked BOOLEAN DEFAULT FALSE,
    notes TEXT
);

-- Enable RLS and permissions if needed
ALTER TABLE crm_leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all public read/write for local console" ON crm_leads FOR ALL USING (true) WITH CHECK (true);

-- 3. Lead Activity Timeline Table
CREATE TABLE IF NOT EXISTS crm_lead_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES crm_leads(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    activity_type TEXT NOT NULL CHECK (activity_type IN ('call', 'note', 'whatsapp', 'crm_update', 'pipeline_change')),
    title TEXT NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

ALTER TABLE crm_lead_activity ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all timeline read/write for local console" ON crm_lead_activity FOR ALL USING (true) WITH CHECK (true);

-- 4. Workflow Automations Table
CREATE TABLE IF NOT EXISTS crm_workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    name TEXT NOT NULL,
    trigger_event TEXT NOT NULL,
    actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Insert default workflows for eWings demo
INSERT INTO crm_workflows (name, trigger_event, actions, is_active)
VALUES 
(
    'New Lead Automated AI Outbound Call', 
    'lead_created', 
    '[{"type": "ai_call", "config": {"delay_seconds": 5}}, {"type": "crm_update", "config": {"status": "Contacted"}}]'::jsonb,
    TRUE
),
(
    'Post-Call WhatsApp Follow-up', 
    'call_ended', 
    '[{"type": "whatsapp", "config": {"template": "day_0_intro"}}, {"type": "reminder", "config": {"title": "Follow up with parents", "delay_days": 1}}]'::jsonb,
    TRUE
)
ON CONFLICT DO NOTHING;

ALTER TABLE crm_workflows ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all workflow read/write for local console" ON crm_workflows FOR ALL USING (true) WITH CHECK (true);
