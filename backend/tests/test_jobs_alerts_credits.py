"""Job lifecycle, expiry, job alerts, credits/unlock, admin approval, registration and the role matrix."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.accounts import AuditLog, Notification
from app.models.company import Company, ContactUnlock, CreditLog
from app.models.enums import AlertFrequency, CompanyStatus, JobStatus, UserRole, Visibility
from app.models.jobs import Job, JobAlert
from app.models.profile import HiddenCompany, JobSeekerProfile
from app.services.alerts import dispatch_alerts, match_alerts
from app.services.jobs_lifecycle import expire_jobs, notify_expiring_soon
from tests.helpers import assert_error, assert_ok, assert_paged

API = "/api/v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def notifs(db, user, category: str | None = None) -> list[Notification]:
    db.expire_all()
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if category:
        q = q.filter(Notification.category == category)
    return q.all()


def job_body(**overrides) -> dict:
    body = {"title": "Backend Engineer", "description": "Build and run APIs.", "requiredSkills": ["Python"],
            "locations": ["Pune"], "publish": True}
    body.update(overrides)
    return body


# =========================================================================== publish / quota


def test_publish_by_approved_company_is_active_and_searchable(client, db, make_company, make_recruiter, auth_headers,
                                                              reload):
    company = make_company()
    recruiter = make_recruiter(company)
    data = assert_ok(client.post(f"{API}/recruiter/jobs", json=job_body(), headers=auth_headers(recruiter)), 201)[
        "data"]
    assert data["status"] == "ACTIVE" and data["postedAt"] and data["expiresAt"]
    posted = datetime.fromisoformat(data["postedAt"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(data["expiresAt"].replace("Z", "+00:00"))
    assert 29 <= (expires - posted).days <= 30
    assert reload(company).jobs_posted == 1

    found = assert_paged(client.get(f"{API}/jobs/search", params={"q": "backend"}))
    assert [j["id"] for j in found["data"]] == [data["id"]]


def test_publish_by_pending_company_goes_to_review_and_is_not_public(client, make_company, make_recruiter,
                                                                     auth_headers, reload):
    company = make_company(status=CompanyStatus.PENDING)
    recruiter = make_recruiter(company)
    data = assert_ok(client.post(f"{API}/recruiter/jobs", json=job_body(), headers=auth_headers(recruiter)), 201)[
        "data"]
    assert data["status"] == "PENDING_REVIEW"
    assert reload(company).jobs_posted == 1  # counted at first publish
    assert assert_paged(client.get(f"{API}/jobs/search"))["meta"]["total"] == 0
    assert_error(client.get(f"{API}/jobs/{data['id']}"), 404, "NOT_FOUND")


def test_draft_does_not_consume_quota_and_can_be_published_later(client, make_company, make_recruiter, auth_headers,
                                                                 reload):
    company = make_company(job_quota=1)
    recruiter = make_recruiter(company)
    headers = auth_headers(recruiter)
    draft = assert_ok(client.post(f"{API}/recruiter/jobs", json=job_body(publish=False), headers=headers), 201)["data"]
    assert draft["status"] == "DRAFT" and draft["postedAt"] is None
    assert reload(company).jobs_posted == 0
    live = assert_ok(client.patch(f"{API}/recruiter/jobs/{draft['id']}/status", json={"status": "ACTIVE"},
                                  headers=headers))["data"]
    assert live["status"] == "ACTIVE"
    assert reload(company).jobs_posted == 1


def test_quota_exceeded_is_403_and_rolls_back(client, db, make_company, make_recruiter, auth_headers, reload):
    company = make_company(job_quota=2)
    recruiter = make_recruiter(company)
    headers = auth_headers(recruiter)
    for i in range(2):
        assert_ok(client.post(f"{API}/recruiter/jobs", json=job_body(title=f"Job {i}"), headers=headers), 201)
    err = assert_error(client.post(f"{API}/recruiter/jobs", json=job_body(title="Third"), headers=headers), 403,
                       "QUOTA_EXCEEDED")
    assert "quota" in err["message"].lower()
    db.expire_all()
    assert db.query(Job).filter_by(company_id=company.id).count() == 2  # atomic: the third create was rolled back
    assert reload(company).jobs_posted == 2

    # a draft can still be saved, but not published
    draft = assert_ok(client.post(f"{API}/recruiter/jobs", json=job_body(title="Draft", publish=False),
                                  headers=headers), 201)["data"]
    assert_error(client.patch(f"{API}/recruiter/jobs/{draft['id']}/status", json={"status": "ACTIVE"},
                              headers=headers), 403, "QUOTA_EXCEEDED")


def test_pause_resume_and_close_do_not_consume_quota(client, make_company, make_recruiter, auth_headers, reload):
    company = make_company(job_quota=1)
    recruiter = make_recruiter(company)
    headers = auth_headers(recruiter)
    job_id = assert_ok(client.post(f"{API}/recruiter/jobs", json=job_body(), headers=headers), 201)["data"]["id"]
    url = f"{API}/recruiter/jobs/{job_id}/status"
    assert assert_ok(client.patch(url, json={"status": "PAUSED"}, headers=headers))["data"]["status"] == "PAUSED"
    assert assert_ok(client.patch(url, json={"status": "ACTIVE"}, headers=headers))["data"]["status"] == "ACTIVE"
    assert assert_ok(client.patch(url, json={"status": "CLOSED"}, headers=headers))["data"]["status"] == "CLOSED"
    assert assert_ok(client.patch(url, json={"status": "ACTIVE"}, headers=headers))["data"]["status"] == "ACTIVE"
    assert reload(company).jobs_posted == 1
    # illegal: ACTIVE -> DRAFT
    assert_error(client.patch(url, json={"status": "DRAFT"}, headers=headers), 409, "INVALID_TRANSITION")


@pytest.mark.parametrize("status", [CompanyStatus.REJECTED, CompanyStatus.BLOCKED])
def test_rejected_or_blocked_company_cannot_publish(client, make_company, make_recruiter, auth_headers, status):
    recruiter = make_recruiter(make_company(status=status))
    assert_error(client.post(f"{API}/recruiter/jobs", json=job_body(), headers=auth_headers(recruiter)), 403,
                 "COMPANY_NOT_APPROVED")


def test_job_create_validation(client, make_company, make_recruiter, auth_headers):
    headers = auth_headers(make_recruiter(make_company()))
    url = f"{API}/recruiter/jobs"
    assert_error(client.post(url, json={"description": "x"}, headers=headers), 422, "VALIDATION_ERROR")
    assert_error(client.post(url, json=job_body(salaryMin=10, salaryMax=5), headers=headers), 422, "VALIDATION_ERROR")
    assert_error(client.post(url, json=job_body(experienceMin=5, experienceMax=1), headers=headers), 422,
                 "VALIDATION_ERROR")
    yesterday = (utc_now() - timedelta(days=1)).date().isoformat()
    assert_error(client.post(url, json=job_body(deadline=yesterday), headers=headers), 422, "VALIDATION_ERROR")
    assert_error(client.post(url, json=job_body(workMode="TELEPORT"), headers=headers), 422, "VALIDATION_ERROR")


def test_job_ownership_and_listing(client, make_company, make_recruiter, make_job, auth_headers):
    c1, c2 = make_company(name="One"), make_company(name="Two")
    r1, r2 = make_recruiter(c1), make_recruiter(c2)
    j1 = make_job(c1, r1, title="Mine")
    make_job(c2, r2, title="Theirs")
    mine = assert_paged(client.get(f"{API}/recruiter/jobs", headers=auth_headers(r1)))
    assert [j["id"] for j in mine["data"]] == [str(j1.id)]
    assert_error(client.patch(f"{API}/recruiter/jobs/{j1.id}/status", json={"status": "CLOSED"},
                              headers=auth_headers(r2)), 403, "FORBIDDEN")
    assert_error(client.delete(f"{API}/recruiter/jobs/{j1.id}", headers=auth_headers(r2)), 403, "FORBIDDEN")
    assert_error(client.get(f"{API}/recruiter/jobs/{uuid.uuid4()}", headers=auth_headers(r1)), 404, "NOT_FOUND")


def test_soft_delete_hides_job(client, make_company, make_recruiter, make_job, auth_headers):
    company = make_company()
    recruiter = make_recruiter(company)
    job = make_job(company, recruiter)
    assert_ok(client.delete(f"{API}/recruiter/jobs/{job.id}", headers=auth_headers(recruiter)))
    assert_error(client.get(f"{API}/recruiter/jobs/{job.id}", headers=auth_headers(recruiter)), 404, "NOT_FOUND")
    assert_error(client.get(f"{API}/jobs/{job.id}"), 404, "NOT_FOUND")
    assert assert_paged(client.get(f"{API}/jobs/search"))["meta"]["total"] == 0


def test_duplicate_job_is_draft_copy(client, make_company, make_recruiter, make_job, make_question, auth_headers):
    company = make_company()
    recruiter = make_recruiter(company)
    job = make_job(company, recruiter, title="Original")
    make_question(job, "Relocate?")
    data = assert_ok(client.post(f"{API}/recruiter/jobs/{job.id}/duplicate", headers=auth_headers(recruiter)), 201)[
        "data"]
    assert data["status"] == "DRAFT" and data["id"] != str(job.id) and data["postedAt"] is None
    assert len(data["questions"]) == 1


def test_publishing_notifies_company_followers(client, db, make_company, make_recruiter, make_user, auth_headers):
    company = make_company()
    recruiter = make_recruiter(company)
    follower = make_user()
    assert_ok(client.post(f"{API}/companies/{company.id}/follow", headers=auth_headers(follower)), 201)
    assert_ok(client.post(f"{API}/recruiter/jobs", json=job_body(), headers=auth_headers(recruiter)), 201)
    assert len(notifs(db, follower, "NEW_JOB_FROM_COMPANY")) == 1


# =========================================================================== expiry


def test_expire_jobs_only_past_expiry_active_jobs(db, make_company, make_recruiter, make_job, reload):
    company = make_company()
    recruiter = make_recruiter(company)
    past = make_job(company, recruiter, title="past", expires_at=utc_now() - timedelta(hours=1))
    future = make_job(company, recruiter, title="future", expires_at=utc_now() + timedelta(days=5))
    paused_past = make_job(company, recruiter, title="paused", status=JobStatus.PAUSED,
                           expires_at=utc_now() - timedelta(days=1))
    draft_past = make_job(company, recruiter, title="draft", status=JobStatus.DRAFT,
                          expires_at=utc_now() - timedelta(days=1))
    closed_past = make_job(company, recruiter, title="closed", status=JobStatus.CLOSED,
                           expires_at=utc_now() - timedelta(days=1))
    deleted_past = make_job(company, recruiter, title="deleted", deleted_at=utc_now(),
                            expires_at=utc_now() - timedelta(days=1))

    assert expire_jobs(db) == 1
    assert reload(past).status == JobStatus.EXPIRED
    assert reload(future).status == JobStatus.ACTIVE
    assert reload(paused_past).status == JobStatus.PAUSED
    assert reload(draft_past).status == JobStatus.DRAFT
    assert reload(closed_past).status == JobStatus.CLOSED
    assert reload(deleted_past).status == JobStatus.ACTIVE
    assert expire_jobs(db) == 0  # idempotent


def test_expire_jobs_honours_explicit_now_and_deadline(db, make_company, make_recruiter, make_job, reload):
    company = make_company()
    recruiter = make_recruiter(company)
    soon = make_job(company, recruiter, title="soon", expires_at=utc_now() + timedelta(days=2))
    by_deadline = make_job(company, recruiter, title="deadline", deadline=(utc_now() - timedelta(days=1)).date())
    assert expire_jobs(db) == 1
    assert reload(by_deadline).status == JobStatus.EXPIRED and reload(soon).status == JobStatus.ACTIVE
    assert expire_jobs(db, now=utc_now() + timedelta(days=3)) == 1
    assert reload(soon).status == JobStatus.EXPIRED


def test_expired_job_leaves_search_and_blocks_apply(client, db, make_company, make_recruiter, make_job, make_user,
                                                   auth_headers):
    company = make_company()
    recruiter = make_recruiter(company)
    job = make_job(company, recruiter, expires_at=utc_now() - timedelta(minutes=5))
    expire_jobs(db)
    assert assert_paged(client.get(f"{API}/jobs/search"))["meta"]["total"] == 0
    assert_error(client.post(f"{API}/jobs/{job.id}/apply", json={}, headers=auth_headers(make_user())), 400,
                 "JOB_CLOSED")


def test_notify_expiring_soon(db, make_company, make_recruiter, make_job):
    company = make_company()
    recruiter = make_recruiter(company)
    other = make_recruiter(company, admin=False)
    soon = make_job(company, recruiter, title="soon", expires_at=utc_now() + timedelta(days=2))
    make_job(company, other, title="later", expires_at=utc_now() + timedelta(days=20))
    make_job(company, other, title="already expired", expires_at=utc_now() - timedelta(days=1))
    make_job(company, other, title="paused soon", status=JobStatus.PAUSED, expires_at=utc_now() + timedelta(days=1))

    assert notify_expiring_soon(db) == 1
    found = notifs(db, recruiter, "JOB_EXPIRING")
    assert len(found) == 1 and found[0].data["jobId"] == str(soon.id) and "soon" in found[0].title
    assert notifs(db, other, "JOB_EXPIRING") == []
    assert notify_expiring_soon(db) == 0  # once per posting cycle
    assert notify_expiring_soon(db, days=30) == 1  # the "later" job now falls in the wider horizon
    assert len(notifs(db, other, "JOB_EXPIRING")) == 1


# =========================================================================== job alerts


@pytest.fixture
def make_alert(db):
    def _make(user, **kw) -> JobAlert:
        kw.setdefault("name", "My alert")
        kw.setdefault("frequency", AlertFrequency.daily)
        alert = JobAlert(user_id=user.id, **kw)
        db.add(alert)
        db.commit()
        return alert

    return _make


@pytest.fixture
def alert_env(make_company, make_recruiter, make_user):
    company = make_company(name="Initech")
    return company, make_recruiter(company), make_user()


def matched(db, since=None, frequency=AlertFrequency.daily):
    db.expire_all()
    result = match_alerts(db, since or utc_now() - timedelta(hours=1), frequency)
    return {str(a.id): {str(j.id) for j in jobs} for a, jobs in result}


def test_alert_keywords_match_title_skills_and_description(db, alert_env, make_job, make_alert):
    company, recruiter, seeker = alert_env
    by_title = make_job(company, recruiter, title="Python Developer", required_skills=["Go"])
    by_skill = make_job(company, recruiter, title="Backend Dev", required_skills=["Django", "Python"])
    by_desc = make_job(company, recruiter, title="Engineer", required_skills=["Go"], description="we love PYTHON")
    other = make_job(company, recruiter, title="Chef", required_skills=["Cooking"], description="kitchen")
    alert = make_alert(seeker, keywords="python")
    result = matched(db)
    assert result[str(alert.id)] == {str(by_title.id), str(by_skill.id), str(by_desc.id)}
    assert str(other.id) not in result[str(alert.id)]


def test_alert_without_keywords_matches_everything_recent(db, alert_env, make_job, make_alert):
    company, recruiter, seeker = alert_env
    job = make_job(company, recruiter)
    alert = make_alert(seeker)
    assert matched(db) == {str(alert.id): {str(job.id)}}


def test_alert_location_filter(db, alert_env, make_job, make_alert):
    company, recruiter, seeker = alert_env
    pune = make_job(company, recruiter, title="A", locations=["Pune"])
    make_job(company, recruiter, title="B", locations=["Delhi"])
    alert = make_alert(seeker, locations=["pune", "Mumbai"])
    assert matched(db) == {str(alert.id): {str(pune.id)}}


def test_alert_experience_filter(db, alert_env, make_job, make_alert):
    company, recruiter, seeker = alert_env
    fits = make_job(company, recruiter, title="Fits", experience_min=3, experience_max=6)
    make_job(company, recruiter, title="Too senior", experience_min=7, experience_max=10)
    make_job(company, recruiter, title="Too junior", experience_min=0, experience_max=2)
    alert = make_alert(seeker, experience=5)
    assert matched(db) == {str(alert.id): {str(fits.id)}}


def test_alert_salary_filter(db, alert_env, make_job, make_alert):
    company, recruiter, seeker = alert_env
    rich = make_job(company, recruiter, title="Rich", salary_min=1500000, salary_max=2500000)
    make_job(company, recruiter, title="Poor", salary_min=300000, salary_max=600000)
    alert = make_alert(seeker, salary_min=1000000)
    assert matched(db) == {str(alert.id): {str(rich.id)}}


def test_alert_ignores_non_public_and_old_jobs(db, alert_env, make_company, make_recruiter, make_job, make_alert):
    company, recruiter, seeker = alert_env
    pending = make_company(status=CompanyStatus.PENDING)
    make_job(pending, make_recruiter(pending), title="pending co")
    make_job(company, recruiter, title="draft", status=JobStatus.DRAFT)
    make_job(company, recruiter, title="expired", expires_at=utc_now() - timedelta(days=1))
    make_job(company, recruiter, title="old", posted_at=utc_now() - timedelta(days=3))
    make_alert(seeker)
    assert matched(db) == {}


def test_paused_alert_is_skipped_and_other_frequency_ignored(db, alert_env, make_job, make_alert):
    company, recruiter, seeker = alert_env
    make_job(company, recruiter)
    paused = make_alert(seeker, is_paused=True)
    weekly = make_alert(seeker, frequency=AlertFrequency.weekly, name="weekly")
    assert matched(db) == {}
    assert matched(db, frequency=AlertFrequency.weekly) == {str(weekly.id): {str(job.id) for job in db.query(Job)}}
    assert dispatch_alerts(db, AlertFrequency.daily) == 0
    assert notifs(db, seeker) == []
    db.expire_all()
    assert db.get(JobAlert, paused.id).last_sent_at is None


def test_dispatch_alerts_creates_notification_and_does_not_resend(db, alert_env, make_job, make_alert):
    company, recruiter, seeker = alert_env
    job = make_job(company, recruiter, title="Python Developer")
    alert = make_alert(seeker, keywords="python", name="Python jobs")
    assert dispatch_alerts(db, AlertFrequency.daily) == 1
    found = notifs(db, seeker, "JOB_ALERT")
    assert len(found) == 1
    assert "Python jobs" in found[0].title and "Python Developer" in found[0].body
    assert found[0].data["jobIds"] == [str(job.id)] and found[0].data["alertId"] == str(alert.id)
    assert db.get(JobAlert, alert.id).last_sent_at is not None
    assert dispatch_alerts(db, AlertFrequency.daily) == 0
    assert len(notifs(db, seeker, "JOB_ALERT")) == 1

    new_job = make_job(company, recruiter, title="Senior Python Developer")
    assert dispatch_alerts(db, AlertFrequency.daily) == 1
    latest = max(notifs(db, seeker, "JOB_ALERT"), key=lambda n: n.created_at)
    assert latest.data["jobIds"] == [str(new_job.id)]


def test_dispatch_instant_alerts(db, alert_env, make_job, make_alert):
    company, recruiter, seeker = alert_env
    make_job(company, recruiter)
    make_alert(seeker, frequency=AlertFrequency.instant)
    assert dispatch_alerts(db, AlertFrequency.instant) == 1
    assert dispatch_alerts(db, AlertFrequency.instant) == 0


def test_dispatch_respects_disabled_notification_category(db, alert_env, make_job, make_alert):
    from app.models.accounts import NotificationPreference

    company, recruiter, seeker = alert_env
    make_job(company, recruiter)
    make_alert(seeker)
    pref = db.get(NotificationPreference, seeker.id)
    pref.categories = {"JOB_ALERT": False}
    db.commit()
    assert dispatch_alerts(db, AlertFrequency.daily) == 0
    assert notifs(db, seeker) == []


def test_job_alert_api_crud(client, make_user, auth_headers, make_admin):
    seeker, other = make_user(), make_user()
    headers = auth_headers(seeker)
    created = assert_ok(client.post(f"{API}/job-alerts", headers=headers, json={
        "name": "Pune python", "keywords": "python", "locations": ["Pune"], "experience": 3, "salaryMin": 500000,
        "frequency": "daily"}), 201)["data"]
    assert created["frequency"] == "daily" and created["isPaused"] is False and created["locations"] == ["Pune"]
    aid = created["id"]
    assert assert_ok(client.post(f"{API}/job-alerts/{aid}/pause", headers=headers))["data"]["isPaused"] is True
    assert assert_ok(client.post(f"{API}/job-alerts/{aid}/resume", headers=headers))["data"]["isPaused"] is False
    patched = assert_ok(client.patch(f"{API}/job-alerts/{aid}", json={"frequency": "weekly"}, headers=headers))
    assert patched["data"]["frequency"] == "weekly" and patched["data"]["keywords"] == "python"
    assert_error(client.post(f"{API}/job-alerts", json={"frequency": "hourly"}, headers=headers), 422,
                 "VALIDATION_ERROR")
    assert assert_paged(client.get(f"{API}/job-alerts", headers=headers))["meta"]["total"] == 1
    # other users cannot touch it
    assert_error(client.get(f"{API}/job-alerts/{aid}", headers=auth_headers(other)), 404, "NOT_FOUND")
    assert_error(client.delete(f"{API}/job-alerts/{aid}", headers=auth_headers(other)), 404, "NOT_FOUND")
    assert_ok(client.delete(f"{API}/job-alerts/{aid}", headers=headers))
    assert_error(client.get(f"{API}/job-alerts/{aid}", headers=headers), 404, "NOT_FOUND")


def test_job_alert_limit_is_10(client, make_user, auth_headers):
    headers = auth_headers(make_user())
    for i in range(10):
        assert_ok(client.post(f"{API}/job-alerts", json={"name": f"a{i}"}, headers=headers), 201)
    assert_error(client.post(f"{API}/job-alerts", json={"name": "one too many"}, headers=headers), 409, "CONFLICT")


# =========================================================================== credits / candidate unlock


@pytest.fixture
def talent(make_company, make_recruiter, make_user):
    company = make_company(name="Hooli", credits=5)
    recruiter = make_recruiter(company)
    candidate = make_user(name="Rahul Sharma", mobile="9123456780", email="rahul@example.com")
    return company, recruiter, candidate


def credit_logs(db, company):
    db.expire_all()
    return db.query(CreditLog).filter_by(company_id=company.id).order_by(CreditLog.created_at).all()


def test_candidate_results_are_masked_until_unlock(client, db, talent, auth_headers):
    company, recruiter, candidate = talent
    headers = auth_headers(recruiter)
    item = assert_paged(client.get(f"{API}/recruiter/candidates/search", headers=headers))["data"][0]
    assert item["id"] == str(candidate.id)
    assert item["name"] == "Rahul S****" and item["isUnlocked"] is False
    assert "email" not in item and "mobile" not in item and "photoUrl" not in item
    detail = assert_ok(client.get(f"{API}/recruiter/candidates/{candidate.id}", headers=headers))["data"]
    assert detail["isUnlocked"] is False and "email" not in detail and "mobile" not in detail
    assert detail["name"] == "Rahul S****"

    assert_ok(client.post(f"{API}/recruiter/candidates/{candidate.id}/unlock", headers=headers), 201)
    after = assert_paged(client.get(f"{API}/recruiter/candidates/search", headers=headers))["data"][0]
    assert after["isUnlocked"] is True and after["name"] == "Rahul Sharma"
    assert after["email"] == "rahul@example.com" and after["mobile"] == "9123456780"


def test_unlock_charges_exactly_one_credit_and_second_unlock_is_free(client, db, talent, make_recruiter,
                                                                    auth_headers, reload):
    company, recruiter, candidate = talent
    headers = auth_headers(recruiter)
    url = f"{API}/recruiter/candidates/{candidate.id}/unlock"

    first = assert_ok(client.post(url, headers=headers), 201)["data"]
    assert first["charged"] is True and first["balance"] == 4
    assert first["candidate"]["email"] == "rahul@example.com"
    assert reload(company).credits == 4
    logs = credit_logs(db, company)
    assert len(logs) == 1
    assert logs[0].delta == -1 and logs[0].balance_after == 4 and logs[0].ref_id == str(candidate.id)
    assert logs[0].user_id == recruiter.id
    assert db.query(ContactUnlock).filter_by(company_id=company.id, candidate_id=candidate.id).count() == 1

    second = assert_ok(client.post(url, headers=headers), 200)["data"]
    assert second["charged"] is False and second["balance"] == 4
    # unlocking is per company: a colleague does not pay again either
    colleague = make_recruiter(company, admin=False)
    third = assert_ok(client.post(url, headers=auth_headers(colleague)), 200)["data"]
    assert third["charged"] is False
    assert reload(company).credits == 4 and len(credit_logs(db, company)) == 1

    summary = assert_ok(client.get(f"{API}/recruiter/credits", headers=headers))["data"]
    assert summary["balance"] == 4 and len(summary["log"]) == 1
    log = assert_paged(client.get(f"{API}/recruiter/credits/log", headers=headers))
    assert log["meta"]["total"] == 1 and log["data"][0]["delta"] == -1


def test_unlock_with_insufficient_credits_is_402_and_balance_unchanged(client, db, make_company, make_recruiter,
                                                                       make_user, auth_headers, reload):
    company = make_company(credits=0)
    recruiter = make_recruiter(company)
    candidate = make_user(name="Poor Chance")
    err = assert_error(client.post(f"{API}/recruiter/candidates/{candidate.id}/unlock",
                                   headers=auth_headers(recruiter)), 402, "INSUFFICIENT_CREDITS")
    assert err["details"]
    assert reload(company).credits == 0
    assert db.query(ContactUnlock).count() == 0 and credit_logs(db, company) == []
    item = assert_paged(client.get(f"{API}/recruiter/candidates/search", headers=auth_headers(recruiter)))["data"][0]
    assert item["isUnlocked"] is False


def test_balance_never_goes_negative_across_candidates(client, db, make_company, make_recruiter, make_user,
                                                       auth_headers, reload):
    company = make_company(credits=1)
    recruiter = make_recruiter(company)
    c1, c2 = make_user(), make_user()
    headers = auth_headers(recruiter)
    assert_ok(client.post(f"{API}/recruiter/candidates/{c1.id}/unlock", headers=headers), 201)
    assert_error(client.post(f"{API}/recruiter/candidates/{c2.id}/unlock", headers=headers), 402,
                 "INSUFFICIENT_CREDITS")
    assert reload(company).credits == 0 and len(credit_logs(db, company)) == 1


def test_hidden_candidates_are_excluded(client, db, talent, auth_headers, reload):
    company, recruiter, candidate = talent
    headers = auth_headers(recruiter)
    profile = db.get(JobSeekerProfile, candidate.id)
    profile.visibility = Visibility.HIDDEN
    db.commit()
    assert assert_paged(client.get(f"{API}/recruiter/candidates/search", headers=headers))["meta"]["total"] == 0
    assert_error(client.get(f"{API}/recruiter/candidates/{candidate.id}", headers=headers), 404, "NOT_FOUND")
    assert_error(client.post(f"{API}/recruiter/candidates/{candidate.id}/unlock", headers=headers), 404, "NOT_FOUND")
    assert reload(company).credits == 5 and credit_logs(db, company) == []


def test_applied_only_and_hidden_company_visibility(client, db, talent, make_job, make_application, auth_headers):
    company, recruiter, candidate = talent
    headers = auth_headers(recruiter)
    profile = db.get(JobSeekerProfile, candidate.id)
    profile.visibility = Visibility.APPLIED_ONLY
    db.commit()
    assert assert_paged(client.get(f"{API}/recruiter/candidates/search", headers=headers))["meta"]["total"] == 0
    make_application(make_job(company, recruiter), candidate)
    assert assert_paged(client.get(f"{API}/recruiter/candidates/search", headers=headers))["meta"]["total"] == 1

    db.add(HiddenCompany(user_id=candidate.id, company_id=company.id))
    db.commit()
    assert assert_paged(client.get(f"{API}/recruiter/candidates/search", headers=headers))["meta"]["total"] == 0


def test_candidate_search_requires_approved_company(client, make_company, make_recruiter, auth_headers):
    pending = make_recruiter(make_company(status=CompanyStatus.PENDING))
    assert_error(client.get(f"{API}/recruiter/candidates/search", headers=auth_headers(pending)), 403,
                 "COMPANY_NOT_APPROVED")


def test_candidate_search_filters_by_skill_and_boolean_query(client, make_company, make_recruiter,
                                                             make_seeker_with_skills, auth_headers):
    company = make_company()
    headers = auth_headers(make_recruiter(company))
    py = make_seeker_with_skills(["Python", "SQL"], name="Py Person")
    js = make_seeker_with_skills(["JavaScript"], name="Js Person")
    by_skill = assert_paged(client.get(f"{API}/recruiter/candidates/search", params={"skills": "python"},
                                       headers=headers))
    assert [c["id"] for c in by_skill["data"]] == [str(py.id)]
    boolean = assert_paged(client.get(f"{API}/recruiter/candidates/search",
                                      params={"q": "python OR javascript"}, headers=headers))
    assert {c["id"] for c in boolean["data"]} == {str(py.id), str(js.id)}
    negated = assert_paged(client.get(f"{API}/recruiter/candidates/search",
                                      params={"q": "sql NOT javascript"}, headers=headers))
    assert [c["id"] for c in negated["data"]] == [str(py.id)]
    assert_error(client.get(f"{API}/recruiter/candidates/search", params={"q": "(python"}, headers=headers), 422,
                 "VALIDATION_ERROR")


# =========================================================================== admin approval


def test_admin_company_approval_notifies_recruiters_and_writes_audit_log(client, db, make_company, make_recruiter,
                                                                         make_admin, auth_headers, reload):
    company = make_company(status=CompanyStatus.PENDING)
    founder = make_recruiter(company)
    colleague = make_recruiter(company, admin=False)
    admin = make_admin()
    data = assert_ok(client.patch(f"{API}/admin/companies/{company.id}/status", json={"status": "APPROVED"},
                                  headers=auth_headers(admin)))["data"]
    assert data["status"] == "APPROVED"
    assert reload(company).status == CompanyStatus.APPROVED
    for user in (founder, colleague):
        found = notifs(db, user, "RECRUITER_APPROVED")
        assert len(found) == 1 and "approved" in found[0].title.lower()
    db.expire_all()
    logs = db.query(AuditLog).filter_by(action="COMPANY_APPROVED").all()
    assert len(logs) == 1
    assert logs[0].actor_id == admin.id and logs[0].entity_id == str(company.id) and logs[0].entity_type == "Company"
    listing = assert_paged(client.get(f"{API}/admin/audit-logs", headers=auth_headers(admin)))
    assert listing["meta"]["total"] >= 1

    # after approval the company can publish live jobs
    live = assert_ok(client.post(f"{API}/recruiter/jobs", json=job_body(), headers=auth_headers(founder)), 201)["data"]
    assert live["status"] == "ACTIVE"


def test_admin_company_reject_requires_reason_and_block_closes_jobs(client, db, make_company, make_recruiter,
                                                                    make_admin, make_job, auth_headers, reload):
    company = make_company()
    recruiter = make_recruiter(company)
    job = make_job(company, recruiter)
    admin_headers = auth_headers(make_admin())
    url = f"{API}/admin/companies/{company.id}/status"
    assert_error(client.patch(url, json={"status": "REJECTED"}, headers=admin_headers), 422, "VALIDATION_ERROR")
    data = assert_ok(client.patch(url, json={"status": "BLOCKED", "reason": "Fraud suspected"},
                                  headers=admin_headers))["data"]
    assert data["status"] == "BLOCKED"
    assert reload(job).status == JobStatus.CLOSED
    assert len(notifs(db, recruiter, "RECRUITER_REJECTED")) == 1
    assert db.query(AuditLog).filter_by(action="COMPANY_BLOCKED").count() == 1
    assert_error(client.patch(f"{API}/admin/companies/{uuid.uuid4()}/status", json={"status": "APPROVED"},
                              headers=admin_headers), 404, "NOT_FOUND")


def test_admin_job_moderation(client, db, make_company, make_recruiter, make_admin, make_job, auth_headers, reload):
    company = make_company()
    recruiter = make_recruiter(company)
    job = make_job(company, recruiter, status=JobStatus.PENDING_REVIEW)
    headers = auth_headers(make_admin())
    url = f"{API}/admin/jobs/{job.id}/status"
    assert_error(client.patch(url, json={"status": "REJECTED"}, headers=headers), 422, "VALIDATION_ERROR")
    assert assert_ok(client.patch(url, json={"status": "ACTIVE"}, headers=headers))["data"]["status"] == "ACTIVE"
    assert len(notifs(db, recruiter, "JOB_APPROVED")) == 1
    assert db.query(AuditLog).filter_by(action="JOB_APPROVED", entity_id=str(job.id)).count() == 1
    assert_ok(client.patch(url, json={"status": "REJECTED", "reason": "Misleading"}, headers=headers))
    assert reload(job).status == JobStatus.REJECTED and reload(job).reject_reason == "Misleading"
    assert len(notifs(db, recruiter, "JOB_REJECTED")) == 1


# =========================================================================== registration


def register_body(**overrides) -> dict:
    body = {"name": "Founder One", "email": "founder@startup-inc.com", "mobile": "9876543210",
            "password": "Passw0rd1", "role": "RECRUITER", "companyName": "Startup Inc"}
    body.update(overrides)
    return body


@pytest.mark.parametrize("email", ["boss@gmail.com", "boss@GMAIL.com", "boss@yahoo.com", "boss@outlook.com"])
def test_recruiter_registration_with_free_email_is_rejected(client, db, email):
    err = assert_error(client.post(f"{API}/auth/register", json=register_body(email=email)), 422, "VALIDATION_ERROR")
    assert any(d["field"] == "email" for d in err["details"])
    db.expire_all()
    assert db.query(Company).count() == 0


def test_recruiter_registration_with_work_email_creates_pending_company(client, db):
    data = assert_ok(client.post(f"{API}/auth/register", json=register_body()), 201)["data"]
    assert data["user"]["role"] == "RECRUITER"
    assert data["user"]["company"]["status"] == "PENDING" and data["user"]["company"]["isCompanyAdmin"] is True
    db.expire_all()
    company = db.query(Company).one()
    assert company.name == "Startup Inc" and company.status == CompanyStatus.PENDING
    assert company.credits == 50 and company.job_quota == 10 and company.jobs_posted == 0
    from app.models.accounts import User
    user = db.query(User).filter_by(email="founder@startup-inc.com").one()
    assert user.company_id == company.id and user.is_company_admin is True and user.role == UserRole.RECRUITER


def test_recruiter_registration_requires_company_name(client):
    assert_error(client.post(f"{API}/auth/register", json=register_body(companyName=None)), 422, "VALIDATION_ERROR")


def test_seeker_registration_may_use_free_email(client, db):
    data = assert_ok(client.post(f"{API}/auth/register", json=register_body(
        email="seeker@gmail.com", role="JOB_SEEKER", companyName=None)), 201)["data"]
    assert data["user"]["role"] == "JOB_SEEKER" and data["user"]["company"] is None
    db.expire_all()
    assert db.query(JobSeekerProfile).count() == 1 and db.query(Company).count() == 0


def test_cannot_register_admin(client):
    assert_error(client.post(f"{API}/auth/register", json=register_body(role="ADMIN")), 422, "VALIDATION_ERROR")


# =========================================================================== role permission matrix

ID = "{id}"
SEEKER, RECRUITER, ADMIN, ANON = "JOB_SEEKER", "RECRUITER", "ADMIN", None

MATRIX: list[tuple[str, str, str | None, int]] = []


def _rows(method: str, path: str, expectations: dict[str | None, int]) -> None:
    for role, status in expectations.items():
        MATRIX.append((method, path, role, status))


_RECRUITER_ONLY = {ANON: 401, SEEKER: 403, ADMIN: 403}
for _m, _p in [
    ("GET", "/recruiter/dashboard"), ("GET", "/recruiter/jobs"), ("POST", "/recruiter/jobs"),
    ("GET", f"/recruiter/jobs/{ID}"), ("PUT", f"/recruiter/jobs/{ID}"), ("DELETE", f"/recruiter/jobs/{ID}"),
    ("PATCH", f"/recruiter/jobs/{ID}/status"), ("POST", f"/recruiter/jobs/{ID}/duplicate"),
    ("GET", f"/recruiter/jobs/{ID}/applicants"), ("GET", f"/recruiter/jobs/{ID}/applicants/export"),
    ("GET", f"/recruiter/applications/{ID}"), ("PATCH", f"/recruiter/applications/{ID}/status"),
    ("POST", "/recruiter/applications/bulk-status"), ("POST", f"/recruiter/applications/{ID}/interview"),
    ("GET", "/recruiter/candidates/search"), ("GET", f"/recruiter/candidates/{ID}"),
    ("POST", f"/recruiter/candidates/{ID}/unlock"), ("GET", "/recruiter/credits"), ("GET", "/recruiter/credits/log"),
    ("GET", "/recruiter/company"), ("PUT", "/recruiter/company"), ("GET", "/recruiter/folders"),
]:
    _rows(_m, _p, _RECRUITER_ONLY)

_ADMIN_ONLY = {ANON: 401, SEEKER: 403, RECRUITER: 403}
for _m, _p in [
    ("GET", "/admin/companies"), ("GET", f"/admin/companies/{ID}"), ("PATCH", f"/admin/companies/{ID}/status"),
    ("POST", f"/admin/companies/{ID}/credits"), ("GET", "/admin/jobs"), ("PATCH", f"/admin/jobs/{ID}/status"),
    ("GET", "/admin/users"), ("PATCH", f"/admin/users/{ID}/block"), ("GET", "/admin/analytics"),
    ("GET", "/admin/audit-logs"), ("GET", "/admin/master/skills"), ("POST", "/admin/master/skills"),
    ("GET", "/admin/reviews"), ("GET", "/admin/job-reports"),
]:
    _rows(_m, _p, _ADMIN_ONLY)

_SEEKER_ONLY = {ANON: 401, RECRUITER: 403, ADMIN: 403}
for _m, _p in [
    ("GET", "/applications/me"), ("GET", f"/applications/{ID}"), ("POST", f"/applications/{ID}/withdraw"),
    ("POST", f"/jobs/{ID}/apply"), ("POST", f"/jobs/{ID}/save"), ("DELETE", f"/jobs/{ID}/save"),
    ("GET", "/jobs/saved"), ("GET", "/jobs/recommended"), ("GET", "/job-alerts"), ("POST", "/job-alerts"),
    ("GET", "/profile/me"), ("PUT", "/profile/me"), ("GET", "/profile/skills"), ("GET", "/resumes"),
    ("POST", f"/companies/{ID}/follow"),
]:
    _rows(_m, _p, _SEEKER_ONLY)

_ANY_AUTH = {ANON: 401}
for _m, _p in [("GET", "/notifications"), ("GET", "/auth/me"), ("GET", "/notifications/unread-count"),
               ("GET", "/notification-preferences"), ("POST", "/auth/logout-all")]:
    _rows(_m, _p, _ANY_AUTH)

# positive controls: the right role gets through
for _m, _p, _role in [
    ("GET", "/recruiter/dashboard", RECRUITER), ("GET", "/recruiter/jobs", RECRUITER),
    ("GET", "/recruiter/credits", RECRUITER), ("GET", "/recruiter/company", RECRUITER),
    ("GET", "/applications/me", SEEKER), ("GET", "/job-alerts", SEEKER), ("GET", "/jobs/saved", SEEKER),
    ("GET", "/profile/me", SEEKER), ("GET", "/admin/companies", ADMIN), ("GET", "/admin/users", ADMIN),
    ("GET", "/admin/audit-logs", ADMIN), ("GET", "/notifications", SEEKER), ("GET", "/notifications", RECRUITER),
    ("GET", "/notifications", ADMIN), ("GET", "/auth/me", ADMIN), ("GET", "/jobs/search", ANON),
    ("GET", "/master/skills", ANON), ("GET", "/health", ANON),
]:
    MATRIX.append((_m, _p, _role, 200))


@pytest.fixture
def actors(make_company, make_recruiter, make_user, make_admin, auth_headers):
    company = make_company()
    return {
        None: {},
        SEEKER: auth_headers(make_user()),
        RECRUITER: auth_headers(make_recruiter(company)),
        ADMIN: auth_headers(make_admin()),
    }


@pytest.mark.parametrize(
    "method,path,role,expected", MATRIX, ids=[f"{m} {p} as {r or 'anon'} -> {e}" for m, p, r, e in MATRIX]
)
def test_role_permission_matrix(client, actors, method, path, role, expected):
    url = API + path.replace(ID, str(uuid.uuid4()))
    kwargs = {"headers": actors[role]}
    if method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = {}
    resp = client.request(method, url, **kwargs)
    assert resp.status_code == expected, f"{method} {path} as {role}: {resp.status_code} {resp.text}"
    if expected in (401, 403):
        error = assert_error(resp, expected)
        assert error["code"] == ("UNAUTHORIZED" if expected == 401 else "FORBIDDEN")
    else:
        assert resp.json()["success"] is True
