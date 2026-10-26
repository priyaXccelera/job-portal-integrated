"""Applications: matching, apply/withdraw, knockout screening, state machine, permissions, interviews."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.accounts import Notification
from app.models.applications import Application, ApplicationNote, Interview, StatusHistory
from app.models.enums import ApplicationStatus as S
from app.models.enums import JobStatus, QuestionType
from app.models.jobs import Job
from app.services.matching import match_score
from tests.helpers import assert_error, assert_ok, assert_paged

API = "/api/v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def notifications(db, user, category: str | None = None) -> list[Notification]:
    db.expire_all()
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if category:
        q = q.filter(Notification.category == category)
    return q.all()


def app_status(db, application) -> S:
    db.expire_all()
    return S(db.get(Application, application.id).status)


# --------------------------------------------------------------------------- match_score (pure function)


def test_match_score_case_insensitive():
    result = match_score(["Python", "SQL"], ["python", "sql", "go"])
    assert result == {"percentage": 100, "matchingSkills": ["Python", "SQL"], "missingSkills": []}


def test_match_score_empty_required_is_100():
    assert match_score([], ["python"]) == {"percentage": 100, "matchingSkills": [], "missingSkills": []}
    assert match_score(None, None)["percentage"] == 100


def test_match_score_partial_and_none():
    partial = match_score(["Python", "Java", "Go"], ["PYTHON"])
    assert partial["percentage"] == 33
    assert partial["matchingSkills"] == ["Python"]
    assert partial["missingSkills"] == ["Java", "Go"]
    none = match_score(["Python"], [])
    assert none == {"percentage": 0, "matchingSkills": [], "missingSkills": ["Python"]}


def test_match_score_ignores_duplicates_and_blank_entries():
    result = match_score(["Python", "python", " ", "Java"], ["java"])
    assert result["percentage"] == 50
    assert result["matchingSkills"] == ["Java"]


# --------------------------------------------------------------------------- apply


def test_apply_happy_path(client, db, approved_setup, make_seeker_with_skills, auth_headers, reload):
    company, recruiter, job = approved_setup
    seeker = make_seeker_with_skills(["Python"])
    resp = client.post(f"{API}/jobs/{job.id}/apply", json={"coverNote": "Hello", "expectedCtc": 900000,
                                                            "noticePeriod": "30 days"},
                       headers=auth_headers(seeker))
    data = assert_ok(resp, 201)["data"]
    assert data["status"] == "APPLIED" and data["jobId"] == str(job.id)
    assert data["matchScore"] == 100
    assert data["coverNote"] == "Hello"
    assert data["timeline"][0]["status"] == "APPLIED"
    assert "screenedOut" not in data and "rating" not in data  # seeker view hides recruiter-side fields

    db.expire_all()
    stored = db.query(Application).filter_by(job_id=job.id, user_id=seeker.id).one()
    assert stored.match_score == 100 and not stored.screened_out
    assert reload(job).application_count == 1
    assert len(notifications(db, recruiter, "NEW_APPLICANT")) == 1


def test_apply_match_score_partial(client, approved_setup, make_job, make_seeker_with_skills, auth_headers):
    company, recruiter, _ = approved_setup
    job = make_job(company, recruiter, required_skills=["Python", "Java"])
    seeker = make_seeker_with_skills(["python"])
    data = assert_ok(client.post(f"{API}/jobs/{job.id}/apply", json={}, headers=auth_headers(seeker)), 201)["data"]
    assert data["matchScore"] == 50


def test_duplicate_apply_is_409_and_db_unique(client, db, approved_setup, make_user, auth_headers, reload):
    _, _, job = approved_setup
    seeker = make_user()
    headers = auth_headers(seeker)
    assert_ok(client.post(f"{API}/jobs/{job.id}/apply", json={}, headers=headers), 201)
    assert_error(client.post(f"{API}/jobs/{job.id}/apply", json={}, headers=headers), 409, "DUPLICATE_APPLICATION")
    assert reload(job).application_count == 1
    assert db.query(Application).filter_by(job_id=job.id, user_id=seeker.id).count() == 1

    db.add(Application(job_id=job.id, user_id=seeker.id, status=S.APPLIED))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": JobStatus.CLOSED},
        {"status": JobStatus.PAUSED},
        {"status": JobStatus.DRAFT},
        {"status": JobStatus.EXPIRED},
        {"expires_at": utc_now() - timedelta(days=1)},
        {"deadline": (utc_now() - timedelta(days=2)).date()},
    ],
    ids=["closed", "paused", "draft", "expired-status", "past-expiry", "past-deadline"],
)
def test_apply_to_closed_or_expired_job_is_400(client, approved_setup, make_job, make_user, auth_headers, overrides):
    company, recruiter, _ = approved_setup
    job = make_job(company, recruiter, **overrides)
    err = assert_error(client.post(f"{API}/jobs/{job.id}/apply", json={}, headers=auth_headers(make_user())), 400)
    assert err["code"] == "JOB_CLOSED"


def test_apply_unknown_job_404_and_requires_auth(client, approved_setup, make_user, auth_headers):
    _, _, job = approved_setup
    assert_error(client.post(f"{API}/jobs/{uuid.uuid4()}/apply", json={}, headers=auth_headers(make_user())), 404,
                 "NOT_FOUND")
    assert_error(client.post(f"{API}/jobs/{job.id}/apply", json={}), 401, "UNAUTHORIZED")


def test_apply_validation_errors(client, approved_setup, make_user, auth_headers, make_question):
    _, _, job = approved_setup
    q = make_question(job, "Years of Python?", QuestionType.MULTIPLE_CHOICE, options=["0-2", "3+"], is_required=True)
    headers = auth_headers(make_user())
    # required question unanswered
    assert_error(client.post(f"{API}/jobs/{job.id}/apply", json={}, headers=headers), 422, "VALIDATION_ERROR")
    # unknown question id
    bad = client.post(f"{API}/jobs/{job.id}/apply", headers=headers,
                      json={"answers": [{"questionId": str(uuid.uuid4()), "answer": "x"}]})
    assert_error(bad, 422, "VALIDATION_ERROR")
    # option not in list
    bad = client.post(f"{API}/jobs/{job.id}/apply", headers=headers,
                      json={"answers": [{"questionId": str(q.id), "answer": "10+"}]})
    assert_error(bad, 422, "VALIDATION_ERROR")
    # negative CTC
    assert_error(client.post(f"{API}/jobs/{job.id}/apply", json={"expectedCtc": -1, "answers": [
        {"questionId": str(q.id), "answer": "3+"}]}, headers=headers), 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------- knockout screening


def test_knockout_failure_is_screened_out_and_only_in_out_list(
    client, db, approved_setup, make_question, make_user, auth_headers
):
    company, recruiter, job = approved_setup
    q = make_question(job, "Can you relocate to Pune?", QuestionType.YES_NO, is_knockout=True, expected_answer="YES")
    failing, passing = make_user(name="Fail Candidate"), make_user(name="Pass Candidate")

    r_fail = client.post(f"{API}/jobs/{job.id}/apply", headers=auth_headers(failing),
                         json={"answers": [{"questionId": str(q.id), "answer": "no"}]})
    r_pass = client.post(f"{API}/jobs/{job.id}/apply", headers=auth_headers(passing),
                         json={"answers": [{"questionId": str(q.id), "answer": "Yes"}]})
    assert_ok(r_fail, 201)  # the candidate is not told about screening
    assert_ok(r_pass, 201)

    db.expire_all()
    out = db.query(Application).filter_by(user_id=failing.id).one()
    assert out.screened_out is True
    assert out.status == S.APPLIED  # status stays APPLIED
    assert "Can you relocate to Pune?" in out.screen_reason
    assert db.query(Application).filter_by(user_id=passing.id).one().screened_out is False

    headers = auth_headers(recruiter)
    base = f"{API}/recruiter/jobs/{job.id}/applicants"
    default = assert_paged(client.get(base, headers=headers))
    assert [a["candidate"]["name"] for a in default["data"]] == ["Pass Candidate"]
    screened = assert_paged(client.get(base, params={"screening": "out"}, headers=headers))
    assert [a["candidate"]["name"] for a in screened["data"]] == ["Fail Candidate"]
    assert screened["data"][0]["screenedOut"] is True
    assert "relocate" in screened["data"][0]["screenReason"]
    everyone = assert_paged(client.get(base, params={"screening": "all"}, headers=headers))
    assert everyone["meta"]["total"] == 2
    assert_error(client.get(base, params={"screening": "maybe"}, headers=headers), 422, "VALIDATION_ERROR")


def test_knockout_multiple_choice_and_non_knockout(client, db, approved_setup, make_question, make_user,
                                                   auth_headers):
    _, _, job = approved_setup
    mc = make_question(job, "Primary language?", QuestionType.MULTIPLE_CHOICE, options=["Python", "Go", "Rust"],
                       is_knockout=True, expected_answer='["Python","Go"]', position=0)
    soft = make_question(job, "Own a laptop?", QuestionType.YES_NO, is_knockout=False, expected_answer="YES",
                         position=1)
    ok_user, bad_user = make_user(), make_user()
    r1 = client.post(f"{API}/jobs/{job.id}/apply", headers=auth_headers(ok_user), json={"answers": [
        {"questionId": str(mc.id), "answer": "go"}, {"questionId": str(soft.id), "answer": "no"}]})
    r2 = client.post(f"{API}/jobs/{job.id}/apply", headers=auth_headers(bad_user), json={"answers": [
        {"questionId": str(mc.id), "answer": "Rust"}, {"questionId": str(soft.id), "answer": "yes"}]})
    assert_ok(r1, 201)
    assert_ok(r2, 201)
    db.expire_all()
    assert db.query(Application).filter_by(user_id=ok_user.id).one().screened_out is False
    assert db.query(Application).filter_by(user_id=bad_user.id).one().screened_out is True


# --------------------------------------------------------------------------- seeker views / withdraw


def test_my_applications_and_detail(client, approved_setup, make_job, make_user, auth_headers):
    company, recruiter, job = approved_setup
    job2 = make_job(company, recruiter, title="Second")
    seeker = make_user()
    headers = auth_headers(seeker)
    a1 = assert_ok(client.post(f"{API}/jobs/{job.id}/apply", json={}, headers=headers), 201)["data"]
    assert_ok(client.post(f"{API}/jobs/{job2.id}/apply", json={}, headers=headers), 201)
    assert_ok(client.post(f"{API}/applications/{a1['id']}/withdraw", headers=headers))

    all_apps = assert_paged(client.get(f"{API}/applications/me", headers=headers))
    assert all_apps["meta"]["total"] == 2
    withdrawn = assert_paged(client.get(f"{API}/applications/me", params={"status": "WITHDRAWN"}, headers=headers))
    assert [a["id"] for a in withdrawn["data"]] == [a1["id"]]
    assert_error(client.get(f"{API}/applications/me", params={"status": "NOPE"}, headers=headers), 422)
    detail = assert_ok(client.get(f"{API}/applications/{a1['id']}", headers=headers))["data"]
    assert [t["status"] for t in detail["timeline"]] == ["APPLIED", "WITHDRAWN"]
    assert detail["job"]["title"] == "Python Developer"


def test_withdraw_flow(client, db, approved_setup, make_user, auth_headers, reload):
    _, recruiter, job = approved_setup
    seeker = make_user()
    headers = auth_headers(seeker)
    app_id = assert_ok(client.post(f"{API}/jobs/{job.id}/apply", json={}, headers=headers), 201)["data"]["id"]
    assert reload(job).application_count == 1

    data = assert_ok(client.post(f"{API}/applications/{app_id}/withdraw", json={"reason": "Found another job"},
                                 headers=headers))["data"]
    assert data["status"] == "WITHDRAWN"
    assert reload(job).application_count == 0
    assert len(notifications(db, recruiter, "STATUS_CHANGE")) == 1
    assert_error(client.post(f"{API}/applications/{app_id}/withdraw", headers=headers), 409, "INVALID_TRANSITION")


# --------------------------------------------------------------------------- state machine

LEGAL: dict[S, set[S]] = {
    S.APPLIED: {S.VIEWED, S.SHORTLISTED, S.REJECTED, S.WITHDRAWN},
    S.VIEWED: {S.SHORTLISTED, S.REJECTED, S.WITHDRAWN},
    S.SHORTLISTED: {S.INTERVIEW_SCHEDULED, S.OFFERED, S.REJECTED, S.WITHDRAWN},
    S.INTERVIEW_SCHEDULED: {S.SHORTLISTED, S.OFFERED, S.REJECTED, S.WITHDRAWN},
    S.OFFERED: {S.HIRED, S.REJECTED, S.WITHDRAWN},
    S.HIRED: set(),
    S.REJECTED: set(),
    S.WITHDRAWN: set(),
}
ALL_PAIRS = [(a, b) for a in S for b in S]


@pytest.mark.parametrize("current,target", ALL_PAIRS, ids=[f"{a.value}->{b.value}" for a, b in ALL_PAIRS])
def test_recruiter_status_transition_table(
    client, db, approved_setup, make_user, make_application, auth_headers, current, target
):
    """Every (from, to) pair: legal -> 200 with new status + history; illegal -> 409 INVALID_TRANSITION.

    Recruiters can never set WITHDRAWN (candidate-only), so that target is always a conflict here."""
    _, recruiter, job = approved_setup
    application = make_application(job, make_user(), status=current)
    history_before = db.query(StatusHistory).filter_by(application_id=application.id).count()

    resp = client.patch(f"{API}/recruiter/applications/{application.id}/status", json={"status": target.value},
                        headers=auth_headers(recruiter))
    legal = target in LEGAL[current] and target != S.WITHDRAWN
    if legal:
        data = assert_ok(resp)["data"]
        assert data["status"] == target.value
        assert app_status(db, application) == target
        assert db.query(StatusHistory).filter_by(application_id=application.id).count() == history_before + 1
    else:
        assert_error(resp, 409, "INVALID_TRANSITION")
        assert app_status(db, application) == current
        assert db.query(StatusHistory).filter_by(application_id=application.id).count() == history_before


@pytest.mark.parametrize("current", list(S), ids=[s.value for s in S])
def test_seeker_withdraw_transition_table(client, db, approved_setup, make_user, make_application, auth_headers,
                                          current):
    _, _, job = approved_setup
    seeker = make_user()
    application = make_application(job, seeker, status=current)
    resp = client.post(f"{API}/applications/{application.id}/withdraw", headers=auth_headers(seeker))
    if S.WITHDRAWN in LEGAL[current]:
        assert assert_ok(resp)["data"]["status"] == "WITHDRAWN"
    else:
        assert_error(resp, 409, "INVALID_TRANSITION")
        assert app_status(db, application) == current


def test_status_change_notifies_candidate_with_category(client, db, approved_setup, make_user, make_application,
                                                        auth_headers):
    _, recruiter, job = approved_setup
    seeker = make_user()
    application = make_application(job, seeker)
    headers = auth_headers(recruiter)
    url = f"{API}/recruiter/applications/{application.id}/status"
    assert_ok(client.patch(url, json={"status": "SHORTLISTED", "message": "Great profile"}, headers=headers))
    assert len(notifications(db, seeker, "APPLICATION_SHORTLISTED")) == 1
    assert_ok(client.patch(url, json={"status": "REJECTED"}, headers=headers))
    assert len(notifications(db, seeker, "STATUS_CHANGE")) == 1
    assert_error(client.patch(url, json={"status": "BOGUS"}, headers=headers), 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------- opening an application


def test_opening_application_marks_viewed_once_and_notifies(client, db, approved_setup, make_user, make_application,
                                                            auth_headers):
    _, recruiter, job = approved_setup
    seeker = make_user()
    application = make_application(job, seeker)
    headers = auth_headers(recruiter)
    url = f"{API}/recruiter/applications/{application.id}"

    first = assert_ok(client.get(url, headers=headers))["data"]
    assert first["status"] == "VIEWED" and first["viewedAt"]
    assert first["candidate"]["name"] == seeker.name
    assert len(notifications(db, seeker, "APPLICATION_VIEWED")) == 1

    again = assert_ok(client.get(url, headers=headers))["data"]
    assert again["status"] == "VIEWED"
    assert len(notifications(db, seeker, "APPLICATION_VIEWED")) == 1
    assert db.query(StatusHistory).filter_by(application_id=application.id, status=S.VIEWED).count() == 1


@pytest.mark.parametrize("status", [S.SHORTLISTED, S.REJECTED, S.OFFERED, S.INTERVIEW_SCHEDULED])
def test_opening_application_does_not_change_non_applied_status(
    client, db, approved_setup, make_user, make_application, auth_headers, status
):
    _, recruiter, job = approved_setup
    seeker = make_user()
    application = make_application(job, seeker, status=status)
    data = assert_ok(client.get(f"{API}/recruiter/applications/{application.id}", headers=auth_headers(recruiter)))[
        "data"]
    assert data["status"] == status.value
    assert app_status(db, application) == status
    assert notifications(db, seeker, "APPLICATION_VIEWED") == []


# --------------------------------------------------------------------------- permissions


def test_recruiter_of_another_company_is_forbidden(client, db, approved_setup, make_company, make_recruiter,
                                                   make_user, make_application, auth_headers):
    _, _, job = approved_setup
    seeker = make_user()
    application = make_application(job, seeker)
    intruder = make_recruiter(make_company(name="Rival Inc"))
    headers = auth_headers(intruder)

    assert_error(client.get(f"{API}/recruiter/jobs/{job.id}/applicants", headers=headers), 403, "FORBIDDEN")
    assert_error(client.get(f"{API}/recruiter/applications/{application.id}", headers=headers), 403, "FORBIDDEN")
    assert_error(client.patch(f"{API}/recruiter/applications/{application.id}/status", json={"status": "REJECTED"},
                              headers=headers), 403, "FORBIDDEN")
    assert_error(client.post(f"{API}/recruiter/applications/{application.id}/notes", json={"note": "x"},
                             headers=headers), 403, "FORBIDDEN")
    assert_error(client.get(f"{API}/recruiter/jobs/{job.id}", headers=headers), 403, "FORBIDDEN")
    assert app_status(db, application) == S.APPLIED  # untouched, not even VIEWED
    assert notifications(db, seeker) == []


def test_unknown_application_is_404_for_recruiter(client, approved_setup, auth_headers):
    _, recruiter, _ = approved_setup
    assert_error(client.get(f"{API}/recruiter/applications/{uuid.uuid4()}", headers=auth_headers(recruiter)), 404,
                 "NOT_FOUND")


def test_seeker_cannot_see_another_seekers_application(client, approved_setup, make_user, make_application,
                                                       auth_headers):
    _, _, job = approved_setup
    owner, other = make_user(), make_user()
    application = make_application(job, owner)
    headers = auth_headers(other)
    assert_error(client.get(f"{API}/applications/{application.id}", headers=headers), 404, "NOT_FOUND")
    assert_error(client.post(f"{API}/applications/{application.id}/withdraw", headers=headers), 404, "NOT_FOUND")
    assert_error(client.post(f"{API}/applications/{application.id}/interview-response", json={"response": "CONFIRM"},
                             headers=headers), 404, "NOT_FOUND")
    assert assert_paged(client.get(f"{API}/applications/me", headers=headers))["meta"]["total"] == 0


def test_role_boundaries_on_recruiter_and_admin_routes(client, approved_setup, make_user, make_admin, make_application,
                                                       auth_headers):
    _, recruiter, job = approved_setup
    seeker = make_user()
    application = make_application(job, seeker)
    sh, rh, ah = auth_headers(seeker), auth_headers(recruiter), auth_headers(make_admin())

    assert_error(client.get(f"{API}/recruiter/jobs/{job.id}/applicants", headers=sh), 403, "FORBIDDEN")
    assert_error(client.patch(f"{API}/recruiter/applications/{application.id}/status", json={"status": "VIEWED"},
                              headers=sh), 403, "FORBIDDEN")
    assert_error(client.get(f"{API}/recruiter/dashboard", headers=ah), 403, "FORBIDDEN")  # admin has no company
    assert_error(client.get(f"{API}/admin/companies", headers=rh), 403, "FORBIDDEN")
    assert_error(client.get(f"{API}/admin/companies", headers=sh), 403, "FORBIDDEN")
    assert_error(client.post(f"{API}/jobs/{job.id}/apply", json={}, headers=rh), 403, "FORBIDDEN")
    assert_error(client.get(f"{API}/recruiter/jobs/{job.id}/applicants"), 401, "UNAUTHORIZED")
    assert_error(client.get(f"{API}/admin/companies"), 401, "UNAUTHORIZED")


# --------------------------------------------------------------------------- bulk status


def test_bulk_status_partial_failures(client, db, approved_setup, make_company, make_recruiter, make_job, make_user,
                                      make_application, auth_headers):
    company, recruiter, job = approved_setup
    ok_app = make_application(job, make_user())
    ok_app2 = make_application(job, make_user(), status=S.VIEWED)
    terminal = make_application(job, make_user(), status=S.REJECTED)
    foreign_company = make_company(name="Other Co")
    foreign_job = make_job(foreign_company, make_recruiter(foreign_company))
    foreign = make_application(foreign_job, make_user())
    missing = uuid.uuid4()

    resp = client.post(f"{API}/recruiter/applications/bulk-status", headers=auth_headers(recruiter), json={
        "applicationIds": [str(ok_app.id), str(ok_app2.id), str(terminal.id), str(foreign.id), str(missing)],
        "status": "SHORTLISTED", "message": "Moving on"})
    data = assert_ok(resp)["data"]
    assert set(data["updated"]) == {str(ok_app.id), str(ok_app2.id)}
    failed = {f["id"]: f["code"] for f in data["failed"]}
    assert failed == {str(terminal.id): "INVALID_TRANSITION", str(foreign.id): "FORBIDDEN",
                      str(missing): "NOT_FOUND"}
    assert app_status(db, ok_app) == S.SHORTLISTED and app_status(db, ok_app2) == S.SHORTLISTED
    assert app_status(db, terminal) == S.REJECTED
    assert app_status(db, foreign) == S.APPLIED


def test_bulk_reject_and_validation(client, db, approved_setup, make_user, make_application, auth_headers):
    _, recruiter, job = approved_setup
    a1, a2 = make_application(job, make_user()), make_application(job, make_user(), status=S.SHORTLISTED)
    headers = auth_headers(recruiter)
    data = assert_ok(client.post(f"{API}/recruiter/applications/bulk-reject", json={
        "applicationIds": [str(a1.id), str(a2.id)], "message": "Not a fit"}, headers=headers))["data"]
    assert len(data["updated"]) == 2 and data["failed"] == []
    assert app_status(db, a1) == S.REJECTED and app_status(db, a2) == S.REJECTED
    assert_error(client.post(f"{API}/recruiter/applications/bulk-status", json={"applicationIds": [],
                                                                               "status": "VIEWED"}, headers=headers),
                 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------- applicants list, notes, rating


def test_applicants_sorted_by_match_and_paged(client, approved_setup, make_user, make_application, auth_headers):
    _, recruiter, job = approved_setup
    low = make_application(job, make_user(name="Low"), match_score=20)
    high = make_application(job, make_user(name="High"), match_score=90)
    mid = make_application(job, make_user(name="Mid"), match_score=55)
    headers = auth_headers(recruiter)
    url = f"{API}/recruiter/jobs/{job.id}/applicants"
    body = assert_paged(client.get(url, headers=headers))
    assert [a["applicationId"] for a in body["data"]] == [str(high.id), str(mid.id), str(low.id)]
    page = assert_paged(client.get(url, params={"pageSize": 2, "page": 2}, headers=headers))
    assert [a["applicationId"] for a in page["data"]] == [str(low.id)] and page["meta"]["total"] == 3
    only = assert_paged(client.get(url, params={"q": "mid"}, headers=headers))
    assert [a["applicationId"] for a in only["data"]] == [str(mid.id)]
    shortlisted = assert_paged(client.get(url, params={"status": "SHORTLISTED"}, headers=headers))
    assert shortlisted["data"] == []


def test_applicants_csv_export(client, approved_setup, make_user, make_application, auth_headers):
    _, recruiter, job = approved_setup
    make_application(job, make_user(name="Csv Person"))
    resp = client.get(f"{API}/recruiter/jobs/{job.id}/applicants/export", headers=auth_headers(recruiter))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.text.splitlines()[0].startswith("Application ID")
    assert "Csv Person" in resp.text


def test_notes_and_rating(client, db, approved_setup, make_user, make_application, auth_headers):
    _, recruiter, job = approved_setup
    application = make_application(job, make_user())
    headers = auth_headers(recruiter)
    base = f"{API}/recruiter/applications/{application.id}"
    note = assert_ok(client.post(f"{base}/notes", json={"note": "Strong communicator"}, headers=headers), 201)["data"]
    assert note["note"] == "Strong communicator" and note["authorId"] == str(recruiter.id)
    listing = assert_paged(client.get(f"{base}/notes", headers=headers))
    assert listing["meta"]["total"] == 1
    assert db.query(ApplicationNote).filter_by(application_id=application.id).count() == 1
    assert_error(client.post(f"{base}/notes", json={"note": "  "}, headers=headers), 422, "VALIDATION_ERROR")

    assert assert_ok(client.put(f"{base}/rating", json={"rating": 4}, headers=headers))["data"]["rating"] == 4
    assert_error(client.put(f"{base}/rating", json={"rating": 6}, headers=headers), 422, "VALIDATION_ERROR")
    assert_error(client.put(f"{base}/rating", json={"rating": "five"}, headers=headers), 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------- interviews


def interview_body(**overrides):
    body = {"dateTime": (utc_now() + timedelta(days=2)).isoformat(), "mode": "VIDEO",
            "locationOrLink": "https://meet.example.com/abc", "notes": "Bring your portfolio"}
    body.update(overrides)
    return body


def test_schedule_interview_chains_status_and_notifies(client, db, approved_setup, make_user, make_application,
                                                       auth_headers):
    _, recruiter, job = approved_setup
    seeker = make_user()
    application = make_application(job, seeker)  # APPLIED -> SHORTLISTED -> INTERVIEW_SCHEDULED
    data = assert_ok(client.post(f"{API}/recruiter/applications/{application.id}/interview",
                                 json=interview_body(), headers=auth_headers(recruiter)), 201)["data"]
    assert data["mode"] == "VIDEO" and data["applicationStatus"] == "INTERVIEW_SCHEDULED"
    assert data["locationOrLink"] == "https://meet.example.com/abc"
    assert app_status(db, application) == S.INTERVIEW_SCHEDULED
    statuses = [h.status for h in db.query(StatusHistory).filter_by(application_id=application.id)
                .order_by(StatusHistory.created_at).all()]
    assert S.SHORTLISTED in statuses and statuses[-1] == S.INTERVIEW_SCHEDULED
    assert db.query(Interview).filter_by(application_id=application.id).count() == 1
    assert len(notifications(db, seeker, "INTERVIEW_SCHEDULED")) == 1

    seen = assert_ok(client.get(f"{API}/applications/{application.id}", headers=auth_headers(seeker)))["data"]
    assert seen["interview"]["mode"] == "VIDEO"


def test_schedule_interview_from_shortlisted_and_reschedule(client, db, approved_setup, make_user, make_application,
                                                            auth_headers):
    _, recruiter, job = approved_setup
    application = make_application(job, make_user(), status=S.SHORTLISTED)
    headers = auth_headers(recruiter)
    url = f"{API}/recruiter/applications/{application.id}/interview"
    assert_ok(client.post(url, json=interview_body(mode="PHONE", locationOrLink="+911234567890"), headers=headers), 201)
    assert_ok(client.post(url, json=interview_body(mode="IN_PERSON", locationOrLink="HQ, Pune"), headers=headers),
              201)
    assert db.query(Interview).filter_by(application_id=application.id).count() == 2
    assert app_status(db, application) == S.INTERVIEW_SCHEDULED


def test_schedule_interview_validation_and_invalid_states(client, db, approved_setup, make_user, make_application,
                                                          auth_headers):
    _, recruiter, job = approved_setup
    headers = auth_headers(recruiter)
    application = make_application(job, make_user())
    url = f"{API}/recruiter/applications/{application.id}/interview"
    past = (utc_now() - timedelta(hours=1)).isoformat()
    assert_error(client.post(url, json=interview_body(dateTime=past), headers=headers), 422, "VALIDATION_ERROR")
    naive = (datetime.now() + timedelta(days=1)).replace(tzinfo=None).isoformat()
    assert_error(client.post(url, json=interview_body(dateTime=naive), headers=headers), 422, "VALIDATION_ERROR")
    assert_error(client.post(url, json=interview_body(mode="TELEPATHY"), headers=headers), 422, "VALIDATION_ERROR")
    assert_error(client.post(url, json=interview_body(locationOrLink=" "), headers=headers), 422, "VALIDATION_ERROR")
    assert db.query(Interview).count() == 0

    for terminal in (S.REJECTED, S.HIRED, S.WITHDRAWN):
        done = make_application(job, make_user(), status=terminal)
        assert_error(client.post(f"{API}/recruiter/applications/{done.id}/interview", json=interview_body(),
                                 headers=headers), 409, "INVALID_TRANSITION")
        assert app_status(db, done) == terminal


def test_schedule_interview_other_company_forbidden(client, approved_setup, make_company, make_recruiter, make_user,
                                                    make_application, auth_headers):
    _, _, job = approved_setup
    application = make_application(job, make_user())
    intruder = make_recruiter(make_company(name="Rival"))
    assert_error(client.post(f"{API}/recruiter/applications/{application.id}/interview", json=interview_body(),
                             headers=auth_headers(intruder)), 403, "FORBIDDEN")


def test_candidate_responds_to_interview(client, db, approved_setup, make_user, make_application, auth_headers):
    _, recruiter, job = approved_setup
    seeker = make_user()
    application = make_application(job, seeker)
    assert_ok(client.post(f"{API}/recruiter/applications/{application.id}/interview", json=interview_body(),
                          headers=auth_headers(recruiter)), 201)
    resp = client.post(f"{API}/applications/{application.id}/interview-response", headers=auth_headers(seeker),
                       json={"response": "RESCHEDULE", "note": "Can we do Friday?"})
    data = assert_ok(resp)["data"]
    assert data["interview"]["candidateResponse"] == "RESCHEDULE"
    assert len(notifications(db, recruiter, "INTERVIEW_RESPONSE")) == 1
    assert_error(client.post(f"{API}/applications/{application.id}/interview-response", headers=auth_headers(seeker),
                             json={"response": "MAYBE"}), 422, "VALIDATION_ERROR")

    # an application without any interview cannot be answered
    other_seeker = make_user()
    other = make_application(job, other_seeker)
    assert_error(client.post(f"{API}/applications/{other.id}/interview-response", headers=auth_headers(other_seeker),
                             json={"response": "CONFIRM"}), 409, "CONFLICT")
