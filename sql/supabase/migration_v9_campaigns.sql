-- ====================================================================
-- migration_v9_campaigns.sql
-- Upgrades aVn with Campaigns, Queues and Encryption at Rest for Leads
-- ====================================================================

-- 1. Create Campaigns Table
CREATE TABLE IF NOT EXISTS public.crm_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'paused', 'completed', 'failed')),
    agent_id UUID, -- Optionally links to public.agents(id)
    concurrency_limit INTEGER DEFAULT 5,
    retry_limit INTEGER DEFAULT 2,
    retry_delay_seconds INTEGER DEFAULT 3600
);

-- Enable RLS and permissions for campaigns
ALTER TABLE public.crm_campaigns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all read/write for local campaigns" ON public.crm_campaigns FOR ALL USING (true) WITH CHECK (true);

-- 2. Modify crm_leads table to support campaigns and encryption at rest
-- Drop the phone UNIQUE constraint to allow importing same leads in different campaigns
ALTER TABLE public.crm_leads DROP CONSTRAINT IF EXISTS crm_leads_phone_key;

-- Add campaign references and outcome columns
ALTER TABLE public.crm_leads 
ADD COLUMN IF NOT EXISTS campaign_id UUID REFERENCES public.crm_campaigns(id) ON DELETE CASCADE,
ADD COLUMN IF NOT EXISTS campaign_status TEXT NOT NULL DEFAULT 'pending' CHECK (campaign_status IN ('pending', 'calling', 'completed', 'failed')),
ADD COLUMN IF NOT EXISTS campaign_outcome TEXT CHECK (campaign_outcome IN ('qualified', 'scheduled', 'no_answer', 'failed', 'validation_error')),
ADD COLUMN IF NOT EXISTS custom_fields JSONB DEFAULT '{}'::jsonb,
ADD COLUMN IF NOT EXISTS phone_encrypted TEXT;

-- Index for campaign lookup
CREATE INDEX IF NOT EXISTS idx_crm_leads_campaign_id ON public.crm_leads(campaign_id);
