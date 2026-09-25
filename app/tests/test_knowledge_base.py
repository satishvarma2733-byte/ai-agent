"""Knowledge base on the application database: ingestion, multilingual search, isolation, jobs.

Embeddings are faked deterministically (words for the same concept in any language share a vector
direction) so the pipeline is tested offline. Real multilingual quality: scripts/kb_multilingual_eval.py.
"""
import unittest
import uuid
from datetime import timedelta
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

import kb
from app.core.database import SessionLocal
from app.main import app
from app.models.kb import KBIngestJob

CONCEPTS = {
    0: ["fee", "fees", "tuition", "ఫీజు", "ఫీజులు", "फीस", "शुल्क"],
    1: ["hostel", "accommodation", "హాస్టల్", "छात्रावास", "हॉस्टल"],
    2: ["weather", "rain", "వాతావరణం", "मौसम"],
}


def fake_vectors(texts, *, runtime=None, is_query=False):
    vectors = []
    for text in texts:
        tokens = set(kb._tokenize_keywords(text))
        vec = np.zeros(kb.KB_EMBEDDING_DIMENSIONS, dtype=np.float32)
        for axis, words in CONCEPTS.items():
            if tokens & set(words):
                vec[axis] = 1.0
        vec[-1] = 0.35  # shared background so unrelated texts aren't exactly orthogonal
        vectors.append((vec / np.linalg.norm(vec)).tolist())
    return vectors


class KnowledgeBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        for target in ("app.routers.auth.deliver", "app.routers.team.deliver"):
            patch(target, return_value="logged").start()
        patch.object(kb, "_embed_gemini", side_effect=fake_vectors).start()
        patch.dict("os.environ", {"KB_EMBEDDING_PROVIDER": "gemini", "KB_EMBEDDING_MODEL": "gemini-embedding-001"}).start()
        # Background processing is triggered explicitly in tests.
        patch("app.routers.kb._process_soon").start()
        self.addCleanup(patch.stopall)
        kb._QUERY_EMBED_CACHE.clear()
        self.tenant, self.headers = self._tenant()

    def _tenant(self):
        email = f"kb-{uuid.uuid4().hex[:10]}@example.com"
        res = self.client.post("/api/auth/signup", json={"email": email, "password": "correct-horse-1", "name": "K", "company_name": "KB Co"})
        token = self.client.post("/api/auth/login", json={"email": email, "password": "correct-horse-1"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        return self.client.get("/api/auth/me", headers=headers).json()["tenant_id"], headers

    def _add_text(self, title, text, headers=None):
        res = self.client.post("/api/kb/sources", json={"source_type": "text", "title": title, "raw_text": text},
                               headers=headers or self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        kb.process_pending_jobs({}, limit=10)
        return res.json()["source"]

    def _search(self, query, headers=None):
        res = self.client.post("/api/kb/search", json={"query": query}, headers=headers or self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    # ── Text processing ────────────────────────────────────────────
    def test_tokenizer_keeps_indic_words_whole(self):
        self.assertEqual(kb._tokenize_keywords("MBBS ఫీజు ఎంత?"), ["mbbs", "ఫీజు", "ఎంత"])
        self.assertEqual(kb._tokenize_keywords("हॉस्टल की फीस"), ["हॉस्टल", "की", "फीस"])
        self.assertEqual(kb.detect_language("The tuition fee is 5 lakh"), "en")
        self.assertEqual(kb.detect_language("ఫీజు ఎంత"), "te")
        self.assertEqual(kb.detect_language("हॉस्टल की फीस"), "hi")

    def test_query_gate(self):
        self.assertTrue(kb.is_kb_query("ఫీజు ఎంత?"))
        self.assertTrue(kb.is_kb_query("what is the fee"))
        self.assertFalse(kb.is_kb_query("hello there"))

    # ── Ingestion ──────────────────────────────────────────────────
    def test_text_source_is_ingested_and_tagged(self):
        src = self._add_text("Fees", "The annual tuition fee for MBBS in Georgia is 5 lakh rupees.")
        detail = [s for s in self.client.get("/api/kb/sources", headers=self.headers).json()["items"] if s["id"] == src["id"]][0]
        self.assertEqual(detail["status"], "ready")
        self.assertEqual(detail["language"], "en")
        self.assertEqual(detail["metadata"]["chunk_count"], 1)
        self.assertEqual(detail["metadata"]["embedding_model"], "gemini:gemini-embedding-001@768")
        status = self.client.get("/api/kb/status", headers=self.headers).json()
        self.assertEqual((status["counts"]["sources"], status["counts"]["chunks"], status["stale_vector_count"]), (1, 1, 0))

    # ── Multilingual search ────────────────────────────────────────
    def test_telugu_and_hindi_questions_find_english_content(self):
        self._add_text("Fees", "The annual tuition fee for MBBS in Georgia is 5 lakh rupees.")
        self._add_text("Stay", "Students live in a university hostel with shared accommodation.")
        telugu = self._search("ఫీజు ఎంత?")
        self.assertEqual([h["title"] for h in telugu["result"]["chunk_hits"]][:1], ["Fees"])
        self.assertIn("answer in the caller's language", telugu["grounding"]["grounding_text"])
        hindi = self._search("हॉस्टल कैसा है?")
        self.assertEqual([h["title"] for h in hindi["result"]["chunk_hits"]][:1], ["Stay"])

    def test_unrelated_non_english_question_gets_no_grounding(self):
        self._add_text("Fees", "The annual tuition fee for MBBS in Georgia is 5 lakh rupees.")
        result = self._search("వాతావరణం ఎలా ఉంది?")
        self.assertEqual(result["result"]["chunk_hits"], [])
        self.assertIsNone(result["grounding"])

    def test_keyword_search_works_without_embeddings(self):
        self._add_text("हिंदी", "कॉलेज की फीस पांच लाख रुपये है")
        with patch.object(kb, "_embed_gemini", side_effect=kb.EmbeddingUnavailableError("offline")), \
             patch.dict("os.environ", {"APP_ENV": "production"}):
            kb._QUERY_EMBED_CACHE.clear()
            hits = kb.search_chunks("फीस कितनी है", tenant_id=self.tenant)
        self.assertEqual([h["title"] for h in hits], ["हिंदी"])

    # ── Isolation ──────────────────────────────────────────────────
    def test_tenants_never_see_each_other(self):
        self._add_text("Secret", "Our secret discount fee is 1 rupee.")
        other_tenant, other_headers = self._tenant()
        self.assertEqual(self.client.get("/api/kb/sources", headers=other_headers).json()["items"], [])
        self.assertEqual(self.client.get("/api/kb/jobs", headers=other_headers).json()["items"], [])
        self.assertEqual(self._search("secret discount fee", headers=other_headers)["result"]["chunk_hits"], [])
        self.assertEqual(kb.search_chunks("secret discount fee", tenant_id=None), [])
        self.assertIsNone(kb.search_for_agent("what is the fee", tenant_id=None))
        mine = self.client.get("/api/kb/sources", headers=self.headers).json()["items"][0]
        self.assertEqual(self.client.delete(f"/api/kb/sources/{mine['id']}", headers=other_headers).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/kb/sources/{mine['id']}", json={"title": "x"}, headers=other_headers).status_code, 404)

    def test_disabled_sources_are_not_searched(self):
        src = self._add_text("Fees", "The annual tuition fee is 5 lakh rupees.")
        self.client.patch(f"/api/kb/sources/{src['id']}", json={"enabled": False}, headers=self.headers)
        self.assertEqual(self._search("what is the fee")["result"]["chunk_hits"], [])
        self.client.patch(f"/api/kb/sources/{src['id']}", json={"enabled": True}, headers=self.headers)
        self.assertEqual(len(self._search("what is the fee")["result"]["chunk_hits"]), 1)

    # ── Model changes and jobs ─────────────────────────────────────
    def test_changing_embedding_model_marks_chunks_stale_until_reindexed(self):
        self._add_text("Fees", "The annual tuition fee is 5 lakh rupees.")
        new_model = {"kb_embedding_provider": "gemini", "kb_embedding_model": "gemini-embedding-002"}
        kb._QUERY_EMBED_CACHE.clear()
        self.assertEqual(kb.get_status(new_model, tenant_id=self.tenant)["stale_vector_count"], 1)
        # Stale vectors are never compared with the new model's query vectors.
        self.assertEqual(kb.search_chunks("ఫీజు", config=new_model, tenant_id=self.tenant), [])
        self.assertEqual(len(kb.reindex_stale_sources(config=new_model, tenant_id=self.tenant)), 1)
        kb.process_pending_jobs(new_model, limit=5)
        self.assertEqual(kb.get_status(new_model, tenant_id=self.tenant)["stale_vector_count"], 0)
        self.assertEqual(len(kb.search_chunks("ఫీజు", config=new_model, tenant_id=self.tenant)), 1)

    def test_legacy_english_default_is_upgraded(self):
        runtime = kb.get_runtime_config({"kb_embedding_provider": "local", "kb_embedding_model": "BAAI/bge-small-en-v1.5"})
        self.assertEqual((runtime["kb_embedding_provider"], runtime["kb_embedding_model"]), ("gemini", "gemini-embedding-001"))
        custom = kb.get_runtime_config({"kb_embedding_provider": "local", "kb_embedding_model": "intfloat/multilingual-e5-base"})
        self.assertEqual(custom["kb_embedding_provider"], "local")

    def test_failed_jobs_back_off_and_stop_after_three_attempts(self):
        with patch.object(kb, "_embed_gemini", side_effect=kb.EmbeddingUnavailableError("quota")), \
             patch.dict("os.environ", {"APP_ENV": "production"}):
            res = self.client.post("/api/kb/sources", json={"source_type": "text", "title": "T", "raw_text": "fee info"}, headers=self.headers)
            source_id = res.json()["source"]["id"]
            self.assertEqual(kb.process_pending_jobs({})[0]["status"], "failed")
            self.assertEqual(kb.process_pending_jobs({}), [], "retry waits for its backoff")
            for _ in range(2):
                self._make_retry_due(source_id)
                kb.process_pending_jobs({})
            self._make_retry_due(source_id)
            self.assertEqual(kb.process_pending_jobs({}), [], "no more retries after 3 attempts")
        source = kb.get_source(source_id, tenant_id=self.tenant)
        self.assertEqual(source["status"], "error")
        self.assertIn("quota", source["sync_error"])

    def _make_retry_due(self, source_id):
        db = SessionLocal()
        try:
            for job in db.query(KBIngestJob).filter(KBIngestJob.source_id == source_id).all():
                if job.next_attempt_at:
                    job.next_attempt_at = job.next_attempt_at - timedelta(days=1)
            db.commit()
        finally:
            db.close()

    def test_a_job_is_claimed_only_once(self):
        self.client.post("/api/kb/sources", json={"source_type": "text", "title": "T", "raw_text": "fee"}, headers=self.headers)
        first, second = kb._claim_jobs(10), kb._claim_jobs(10)
        self.assertTrue(first)
        self.assertEqual(set(first) & set(second), set())

    def test_upload_validation(self):
        res = self.client.post("/api/kb/upload", files={"file": ("notes.exe", b"MZ", "application/octet-stream")}, headers=self.headers)
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/kb/upload", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}, headers=self.headers)
        self.assertEqual(res.status_code, 400)
        res = self.client.post("/api/kb/sources", json={"source_type": "web_url", "title": "x", "source_url": "http://127.0.0.1/admin"},
                               headers=self.headers)
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
