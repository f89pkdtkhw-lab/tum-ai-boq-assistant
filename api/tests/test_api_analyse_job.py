"""#165 (package F): background analysis job with progress. Offline, mock model, synthetic example only."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import analyse_job, main
from app.analyse_job import Job
from app.fortschritt import OHNE_FORTSCHRITT, AnalyseAbgebrochen, Aufzeichnung, teilschritt

client = TestClient(main.app)
LV = main.load_examples()[0].lv.model_dump(mode="json")


def warte(job_id, sekunden=30.0):
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        body = client.get(f"/api/lv/analyse/status/{job_id}").json()
        if body["status"] != "laeuft":
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_start_answers_at_once_and_the_job_reports_eight_steps_like_the_sync_route():
    antwort = client.post("/api/lv/analyse/start", json={"lv": LV})
    assert antwort.status_code == 202 and set(antwort.json()) == {"job_id"}
    stand = warte(antwort.json()["job_id"])
    assert stand["status"] == "fertig" and stand["prozent"] == 100 and stand["fehler"] == []
    assert stand["schritt"] == stand["schritte_gesamt"] == 8
    assert [s["schritt"] for s in stand["fertige_schritte"]] == list(range(1, 9))
    assert stand["fertige_schritte"][0]["meldung"].startswith("Fixed rules:")
    assert stand["ergebnis"] == client.post("/api/lv/analyse", json={"lv": LV}).json()


def test_nur_pruefen_runs_the_pruefen_pipeline_in_seven_steps():
    stand = warte(client.post("/api/lv/analyse/start", json={"lv": LV, "nur_pruefen": True}).json()["job_id"])
    assert stand["status"] == "fertig" and stand["schritte_gesamt"] == 7 and len(stand["fertige_schritte"]) == 7
    assert stand["ergebnis"] == client.post("/api/lv/pruefen", json=LV).json()


def test_unknown_job_is_404_and_invalid_body_is_422():
    assert client.get("/api/lv/analyse/status/nope").status_code == 404
    assert client.post("/api/lv/analyse/start", json={"lv": {"name": "x"}}).status_code == 422


def test_request_does_not_wait_for_a_long_step_and_status_shows_the_running_step():
    frei = threading.Event()

    def arbeit(fortschritt):
        fortschritt(3, 8, "Researching standards for item 01.02.0030 …", 0.5)
        frei.wait(10)
        return main._pruefbericht(main.LV.model_validate(LV))

    start = time.monotonic()
    job_id = analyse_job.starte(arbeit, 8)
    assert time.monotonic() - start < 1.0
    for _ in range(200):
        stand = client.get(f"/api/lv/analyse/status/{job_id}").json()
        if stand["schritt"] == 3:
            break
        time.sleep(0.01)
    assert stand["status"] == "laeuft" and stand["ergebnis"] is None
    assert stand["meldung"] == "Step 3/8: Researching standards for item 01.02.0030 …"
    assert stand["prozent"] == 31  # (2 + 0.5) / 8
    frei.set()
    assert warte(job_id)["status"] == "fertig"


def test_a_failing_pipeline_marks_the_job_failed_with_a_readable_error():
    def arbeit(fortschritt):
        fortschritt(1, 2, "Starting …")
        raise ValueError("broken input")

    stand = warte(analyse_job.starte(arbeit, 2))
    assert stand["status"] == "fehler" and stand["ergebnis"] is None
    assert stand["fehler"] == ["The analysis failed: ValueError: broken input"]


def test_too_many_running_jobs_answer_429(monkeypatch):
    monkeypatch.setattr(analyse_job, "MAX_PARALLEL", 0)
    antwort = client.post("/api/lv/analyse/start", json={"lv": LV})
    assert antwort.status_code == 429 and "already running" in antwort.json()["detail"]


def test_job_progress_closes_steps_keeps_percent_monotonic_and_dedups_errors():
    job = Job(4, timeout=60)
    assert job.bericht().prozent == 0 and job.bericht().meldung == "Waiting to start …"
    job(1, 4, "a")
    job(1, 4, "a done", 1.0)
    job(2, 4, "b", 0.5)
    job(2, 4, "b again", 0.2)  # share never goes back
    stand = job.bericht()
    assert stand.prozent == 37 and [s.meldung for s in stand.fertige_schritte] == ["a done"]
    job.fehler("model timeout")
    job.fehler("model timeout")
    assert job.bericht().fehler == ["model timeout"]


def test_job_timeout_stops_the_pipeline_and_discards_a_late_result():
    job = Job(2, timeout=0.01)
    time.sleep(0.03)
    with pytest.raises(AnalyseAbgebrochen):
        job(1, 2, "late")
    stand = job.bericht()
    assert stand.status == "fehler" and "ANALYSE_JOB_TIMEOUT" in stand.fehler[0]
    job.beenden(main._pruefbericht(main.LV.model_validate(LV)))
    assert job.bericht().status == "fehler" and job.bericht().ergebnis is None


def test_progress_helpers_for_pipeline_steps():
    OHNE_FORTSCHRITT(1, 2, "ignored")
    OHNE_FORTSCHRITT.fehler("ignored")
    aufzeichnung = Aufzeichnung()
    melde = teilschritt(aufzeichnung, 5, 8)
    melde("Researching DIN 1045-2 …", 0.25)
    aufzeichnung.fehler("web search unavailable")
    assert aufzeichnung.meldungen == [(5, 8, "Researching DIN 1045-2 …", 0.25)]
    assert aufzeichnung.fehlerliste == ["web search unavailable"]
    teilschritt(None, 1, 1)("no-op without a job")


def test_sync_pipeline_reports_every_step_to_a_recorder():
    aufzeichnung = Aufzeichnung()
    main._pruefbericht(main.LV.model_validate(LV), fortschritt=aufzeichnung)
    assert sorted({m[0] for m in aufzeichnung.meldungen}) == list(range(1, 8))
    assert all(m[1] == 7 for m in aufzeichnung.meldungen) and aufzeichnung.fehlerliste == []
