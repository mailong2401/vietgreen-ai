from fastapi.testclient import TestClient
from pipeline import app

client = TestClient(app)


def test_health_check():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "qdrant_collection" in data


def test_metric_not_found():
    r = client.get("/api/v1/metrics/999999")
    assert r.status_code == 404


def test_process_document_rejects_non_pdf():
    files = {"file": ("test.txt", b"hello", "text/plain")}
    r = client.post("/api/v1/process-document", files=files)
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]


def test_process_document_rejects_empty():
    files = {"file": ("test.pdf", b"", "application/pdf")}
    r = client.post("/api/v1/process-document", files=files)
    assert r.status_code == 400
    assert "rỗng" in r.json()["detail"]


def test_process_document_rejects_html_disguised_as_pdf():
    files = {"file": ("fake.pdf", b"<!DOCTYPE html><html></html>", "application/pdf")}
    r = client.post("/api/v1/process-document", files=files)
    assert r.status_code == 400
    assert "HTML" in r.json()["detail"]
