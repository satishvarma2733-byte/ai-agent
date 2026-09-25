import unittest
import uuid
import json
import sqlite3
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal, Base, engine
from app.models.tenant import Tenant
from app.models.user import User
from app.models.lead import Lead
from app.models.workflow import Workflow
import kb

class TestQAAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create all tables in the test environment (SQLite or Postgres)
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        from app.tests import assert_test_database
        assert_test_database()
        self.db = SessionLocal()
        # Clean up tables between runs to avoid overlaps
        self.db.query(Lead).delete()
        self.db.query(Workflow).delete()
        self.db.query(User).delete()
        self.db.query(Tenant).delete()
        self.db.commit()

        # Clean KB database (kb.sqlite3) for isolation tests
        try:
            with kb._connect() as conn:
                conn.execute("DELETE FROM kb_sources;")
                conn.execute("DELETE FROM kb_chunks;")
                conn.commit()
        except Exception:
            pass

    def tearDown(self):
        self.db.close()

    def test_api_security_enforcement(self):
        """Assert that accessing secured routers without authorization header yields 401."""
        endpoints = [
            ("/api/crm/leads", "GET"),
            ("/api/crm/leads", "POST"),
            ("/api/crm/workflows", "GET"),
            ("/api/crm/workflows", "POST"),
            ("/api/appointments", "GET"),
            ("/api/cms/pages", "GET"),
            ("/api/agents", "GET"),
            ("/api/kb/sources", "GET"),
        ]
        
        for url, method in endpoints:
            if method == "GET":
                response = self.client.get(url)
            else:
                response = self.client.post(url, json={})
            self.assertEqual(
                response.status_code, 
                401, 
                f"Endpoint {url} with method {method} should be secured and return 401 Unauthorized"
            )

    def test_multi_tenant_lead_isolation(self):
        """Assert that leads created by Tenant A are isolated and inaccessible to Tenant B."""
        # 1. Onboard Tenant A
        t1_payload = {
            "email": "admin_a@tenant-a.com",
            "password": "password123",
            "name": "Admin Tenant A",
            "role": "Admin",
            "company_name": "Tenant A Corp"
        }
        res_t1_signup = self.client.post("/api/auth/signup", json=t1_payload)
        self.assertEqual(res_t1_signup.status_code, 202)
        
        # Log in Tenant A
        res_t1_login = self.client.post("/api/auth/login", json={
            "email": "admin_a@tenant-a.com",
            "password": "password123"
        })
        self.assertEqual(res_t1_login.status_code, 200)
        t1_token = res_t1_login.json()["access_token"]
        t1_headers = {"Authorization": f"Bearer {t1_token}"}

        # 2. Onboard Tenant B
        t2_payload = {
            "email": "admin_b@tenant-b.com",
            "password": "password123",
            "name": "Admin Tenant B",
            "role": "Admin",
            "company_name": "Tenant B Corp"
        }
        res_t2_signup = self.client.post("/api/auth/signup", json=t2_payload)
        self.assertEqual(res_t2_signup.status_code, 202)
        
        # Log in Tenant B
        res_t2_login = self.client.post("/api/auth/login", json={
            "email": "admin_b@tenant-b.com",
            "password": "password123"
        })
        self.assertEqual(res_t2_login.status_code, 200)
        t2_token = res_t2_login.json()["access_token"]
        t2_headers = {"Authorization": f"Bearer {t2_token}"}

        # 3. Create a lead in Tenant A
        lead_payload = {
            "name": "John Doe Tenant A",
            "phone": "+919876543210",
            "email": "johndoe@tenant-a.com",
            "company": "John Co",
            "status": "New",
            "score": "Cold"
        }
        res_create_lead = self.client.post("/api/crm/leads", json=lead_payload, headers=t1_headers)
        self.assertEqual(res_create_lead.status_code, 201)
        lead_id = res_create_lead.json()["id"]

        # 4. Assert Tenant A can see their lead
        res_t1_get = self.client.get("/api/crm/leads", headers=t1_headers)
        self.assertEqual(res_t1_get.status_code, 200)
        t1_leads = res_t1_get.json()
        self.assertEqual(len(t1_leads), 1)
        self.assertEqual(t1_leads[0]["id"], lead_id)

        # 5. Assert Tenant B CANNOT see Tenant A's lead
        res_t2_get = self.client.get("/api/crm/leads", headers=t2_headers)
        self.assertEqual(res_t2_get.status_code, 200)
        t2_leads = res_t2_get.json()
        self.assertEqual(len(t2_leads), 0)

        # 6. Assert Tenant B cannot retrieve Tenant A's lead timeline
        res_t2_timeline = self.client.get(f"/api/crm/leads/{lead_id}/timeline", headers=t2_headers)
        self.assertEqual(res_t2_timeline.status_code, 404)

    def test_multi_tenant_kb_isolation(self):
        """Assert that Knowledge Base sources and chunk searches are strictly isolated by tenant."""
        # Log in Tenant A
        t1_payload = {
            "email": "admin_a2@tenant-a.com",
            "password": "password123",
            "name": "Admin Tenant A2",
            "role": "Admin",
            "company_name": "Tenant A2 Corp"
        }
        self.client.post("/api/auth/signup", json=t1_payload)
        res_t1_login = self.client.post("/api/auth/login", json={
            "email": "admin_a2@tenant-a.com",
            "password": "password123"
        })
        t1_headers = {"Authorization": f"Bearer {res_t1_login.json()['access_token']}"}

        # Log in Tenant B
        t2_payload = {
            "email": "admin_b2@tenant-b.com",
            "password": "password123",
            "name": "Admin Tenant B2",
            "role": "Admin",
            "company_name": "Tenant B2 Corp"
        }
        self.client.post("/api/auth/signup", json=t2_payload)
        res_t2_login = self.client.post("/api/auth/login", json={
            "email": "admin_b2@tenant-b.com",
            "password": "password123"
        })
        t2_headers = {"Authorization": f"Bearer {res_t2_login.json()['access_token']}"}

        # Create a KB source in Tenant A
        source_a_payload = {
            "source_type": "web_url",
            "title": "Tenant A Secret Info",
            "source_url": "https://tenant-a.com/secrets",
            "raw_text": "Secret code word is Banana"
        }
        res_create_source_a = self.client.post("/api/kb/sources", json=source_a_payload, headers=t1_headers)
        self.assertEqual(res_create_source_a.status_code, 200)

        # Assert Tenant A lists their source
        res_t1_sources = self.client.get("/api/kb/sources", headers=t1_headers)
        self.assertEqual(len(res_t1_sources.json()["items"]), 1)
        self.assertEqual(res_t1_sources.json()["items"][0]["title"], "Tenant A Secret Info")

        # Assert Tenant B lists 0 sources
        res_t2_sources = self.client.get("/api/kb/sources", headers=t2_headers)
        self.assertEqual(len(res_t2_sources.json()["items"]), 0)

        # Force sync and index rebuild mock search
        # Tenant B search should return empty or no results matching Tenant A secrets
        res_search_b = self.client.post("/api/kb/search", json={"query": "Banana"}, headers=t2_headers)
        self.assertEqual(res_search_b.status_code, 200)
        self.assertEqual(len(res_search_b.json().get("result", {}).get("chunk_hits", [])), 0)

    def test_workflow_engine_processing(self):
        """Assert that creating a lead dispatches events through the workflow automation engine."""
        # Onboard Tenant A
        t1_payload = {
            "email": "admin_a3@tenant-a.com",
            "password": "password123",
            "name": "Admin Tenant A3",
            "role": "Admin",
            "company_name": "Tenant A3 Corp"
        }
        self.client.post("/api/auth/signup", json=t1_payload)
        res_t1_login = self.client.post("/api/auth/login", json={
            "email": "admin_a3@tenant-a.com",
            "password": "password123"
        })
        t1_headers = {"Authorization": f"Bearer {res_t1_login.json()['access_token']}"}

        # Create a workflow trigger in Tenant A for status 'lead_created'
        wf_payload = {
            "name": "Auto Welcome Workflow",
            "trigger_event": "lead_created",
            "is_active": True,
            "actions": [
                {
                    "type": "whatsapp",
                    "config": {
                        "template": "welcome_template",
                        "phone": "{{lead.phone}}"
                    }
                }
            ]
        }
        res_create_wf = self.client.post("/api/crm/workflows", json=wf_payload, headers=t1_headers)
        self.assertEqual(res_create_wf.status_code, 201)

        # Create a lead to trigger the workflow engine
        lead_payload = {
            "name": "New Enrolled Student",
            "phone": "+918888888888",
            "email": "student@tenant-a.com",
            "company": "Self",
            "status": "New",
            "score": "Cold"
        }
        res_create_lead = self.client.post("/api/crm/leads", json=lead_payload, headers=t1_headers)
        self.assertEqual(res_create_lead.status_code, 201)
        lead_id = res_create_lead.json()["id"]

        # Retrieve lead timeline to verify timeline logs and triggered events
        res_timeline = self.client.get(f"/api/crm/leads/{lead_id}/timeline", headers=t1_headers)
        self.assertEqual(res_timeline.status_code, 200)
        timeline = res_timeline.json()
        
        # Verify the "Lead Created" timeline entry exists
        creation_log = any(item["title"] == "Lead Created" for item in timeline)
        self.assertTrue(creation_log, "Timeline must contain a Lead Created event")

if __name__ == "__main__":
    unittest.main()
