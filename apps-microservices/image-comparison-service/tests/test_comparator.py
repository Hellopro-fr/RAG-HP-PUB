from datetime import datetime

from app.schemas.comparator import JobInput, JobStatus, ComparisonResult


def test_jobinput_defaults_source_pending():
    ji = JobInput(id="x", url="https://e.com/a.jpg")
    assert ji.source == "pending"
    assert JobInput(id="y").url is None  # base64 input: no url


def test_jobstatus_accepts_inputs_and_defaults_none():
    js = JobStatus(job_id="j", status="processing", progress=10.0,
                   inputs=[JobInput(id="x", url="https://e.com/a.jpg", source="cached")])
    assert js.inputs[0].source == "cached"
    assert JobStatus(job_id="j", status="queued", progress=0.0).inputs is None


def test_comparisonresult_accepts_inputs():
    cr = ComparisonResult(job_id="j", status="finished", created_at=datetime.utcnow(),
                          completed_at=datetime.utcnow(), total_images=1, matches_found=0,
                          similar_pairs=[], failed_images=[],
                          inputs=[JobInput(id="x", source="fresh")])
    assert cr.inputs[0].source == "fresh"
