"""Public job search, job detail, suggestions and master data (real PostgreSQL full-text + trigram)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.company import Company
from app.models.enums import (
    ApplicationStatus,
    CompanyStatus,
    CompanyType,
    EmploymentType,
    JobStatus,
    JobType,
    WorkMode,
)
from app.models.jobs import Job, JobView
from tests.helpers import assert_error, assert_ok, assert_paged

SEARCH = "/api/v1/jobs/search"


def now() -> datetime:
    return datetime.now(timezone.utc)


def search(client, headers=None, **params):
    return client.get(SEARCH, params=params, headers=headers or {})


def ids(resp) -> list[str]:
    return [item["id"] for item in assert_paged(resp)["data"]]


@pytest.fixture
def company(make_company):
    return make_company(name="Globex")


@pytest.fixture
def recruiter(company, make_recruiter):
    return make_recruiter(company)


# --------------------------------------------------------------------------- relevance / synonyms / typos


def test_title_match_outranks_description_only_match(client, master_skills, company, recruiter, make_job):
    # the description-only job is NEWER, so date ordering alone would put it first
    desc_only = make_job(
        company, recruiter, title="Office Manager", required_skills=["Excel"],
        description="You will also use python daily for small reports.",
        posted_at=now() - timedelta(hours=1),
    )
    title_match = make_job(
        company, recruiter, title="Python Developer", required_skills=["Python"],
        description="Backend services.", posted_at=now() - timedelta(days=3),
    )
    result = ids(search(client, q="python"))
    assert result[0] == str(title_match.id)
    assert str(desc_only.id) in result
    assert result.index(str(title_match.id)) < result.index(str(desc_only.id))


def test_search_envelope_and_list_object_shape(client, master_skills, company, recruiter, make_job):
    make_job(company, recruiter, title="Python Developer", salary_min=500000, salary_max=900000,
             description="<p>Build <b>python</b> services for our platform.</p>")
    body = assert_paged(search(client, q="python"))
    assert body["success"] is True
    item = body["data"][0]
    for key in ("id", "title", "company", "locations", "skills", "postedAt", "isSaved", "isApplied", "snippet",
                "salaryMin", "salaryMax", "experienceMin", "experienceMax"):
        assert key in item, key
    assert item["company"]["name"] == "Globex"
    assert "<" not in item["snippet"]
    assert item["isSaved"] is False and item["isApplied"] is False


def test_synonym_js_finds_javascript_jobs(client, master_skills, company, recruiter, make_job):
    js_job = make_job(company, recruiter, title="JavaScript Engineer", required_skills=["JavaScript"])
    other = make_job(company, recruiter, title="Pastry Cook", required_skills=["Baking"])
    result = ids(search(client, q="js"))
    assert str(js_job.id) in result
    assert str(other.id) not in result


def test_synonym_expansion_works_in_both_directions(client, master_skills, company, recruiter, make_job):
    job = make_job(company, recruiter, title="Frontend Developer", required_skills=["js"],
                   description="Work on the web client.")
    assert str(job.id) in ids(search(client, q="javascript"))


def test_typo_pythn_finds_python(client, master_skills, company, recruiter, make_job):
    python_job = make_job(company, recruiter, title="Python Developer")
    cook = make_job(company, recruiter, title="Pastry Cook", required_skills=["Baking"])
    result = ids(search(client, q="pythn"))
    assert str(python_job.id) in result
    assert str(cook.id) not in result


def test_multiple_keywords_rank_best_overlap_first(client, master_skills, company, recruiter, make_job):
    both = make_job(company, recruiter, title="Python Django Developer", required_skills=["Python", "Django"])
    only_python = make_job(company, recruiter, title="Python Developer", required_skills=["Python"])
    only_django = make_job(company, recruiter, title="Django Developer", required_skills=["Django"])
    chef = make_job(company, recruiter, title="Head Chef", required_skills=["Cooking"])
    result = ids(search(client, q="python django"))
    assert result[0] == str(both.id)
    assert {str(only_python.id), str(only_django.id)} <= set(result)
    assert str(chef.id) not in result


def test_no_query_lists_all_visible_newest_first(client, company, recruiter, make_job):
    old = make_job(company, recruiter, title="Old", posted_at=now() - timedelta(days=5))
    new = make_job(company, recruiter, title="New", posted_at=now() - timedelta(hours=1))
    assert ids(search(client)) == [str(new.id), str(old.id)]


def test_sql_injection_like_query_is_harmless(client, company, recruiter, make_job):
    make_job(company, recruiter)
    resp = search(client, q="'; DROP TABLE jobs; --")
    assert_paged(resp)
    assert len(ids(search(client))) == 1


# --------------------------------------------------------------------------- filters


def test_filter_location_csv_multi_and_case_insensitive(client, company, recruiter, make_job):
    pune = make_job(company, recruiter, title="A", locations=["Pune"])
    mumbai = make_job(company, recruiter, title="B", locations=["Mumbai", "Thane"])
    delhi = make_job(company, recruiter, title="C", locations=["Delhi"])
    result = ids(search(client, location="PUNE,mumbai"))
    assert set(result) == {str(pune.id), str(mumbai.id)}
    assert str(delhi.id) not in result
    assert ids(search(client, location="thane")) == [str(mumbai.id)]


def test_filter_experience(client, company, recruiter, make_job):
    junior = make_job(company, recruiter, title="Junior", experience_min=0, experience_max=3)
    mid = make_job(company, recruiter, title="Mid", experience_min=2, experience_max=6)
    senior = make_job(company, recruiter, title="Senior", experience_min=7, experience_max=12)
    assert set(ids(search(client, experience=2.5))) == {str(junior.id), str(mid.id)}
    assert ids(search(client, experience=9)) == [str(senior.id)]


def test_filter_salary_min_and_max(client, company, recruiter, make_job):
    high = make_job(company, recruiter, title="High", salary_min=1000000, salary_max=2000000)
    low = make_job(company, recruiter, title="Low", salary_min=300000, salary_max=500000)
    hidden = make_job(company, recruiter, title="Hidden", salary_min=1000000, salary_max=2000000, hide_salary=True)
    assert ids(search(client, salaryMin=1500000)) == [str(high.id)]
    assert ids(search(client, salaryMax=600000)) == [str(low.id)]
    both = set(ids(search(client, salaryMin=400000, salaryMax=1200000)))
    assert both == {str(high.id), str(low.id)}
    assert str(hidden.id) not in both


def test_filter_salary_range_inverted_is_validation_error(client):
    assert_error(search(client, salaryMin=900, salaryMax=100), 422, "VALIDATION_ERROR")


def test_filter_department_role_category_industry(client, company, recruiter, make_job):
    a = make_job(company, recruiter, title="A", department="Engineering", role_category="Backend", industry="IT")
    b = make_job(company, recruiter, title="B", department="Sales", role_category="Inside Sales", industry="Retail")
    assert ids(search(client, department="engineering")) == [str(a.id)]
    assert ids(search(client, roleCategory="Inside Sales")) == [str(b.id)]
    assert ids(search(client, industry="IT,Retail")) and set(ids(search(client, industry="IT,Retail"))) == {
        str(a.id), str(b.id)}
    assert ids(search(client, department="Legal")) == []


def test_filter_company_type_company_and_posted_by(client, make_company, make_recruiter, make_job):
    consult = make_company(name="Hire Wise", company_type=CompanyType.CONSULTANCY)
    startup = make_company(name="Spark Labs", company_type=CompanyType.STARTUP)
    j_consult = make_job(consult, make_recruiter(consult), title="Consult Job")
    j_startup = make_job(startup, make_recruiter(startup), title="Startup Job")

    assert ids(search(client, companyType="CONSULTANCY")) == [str(j_consult.id)]
    assert ids(search(client, companyType="startup")) == [str(j_startup.id)]
    assert ids(search(client, postedBy="consultancy")) == [str(j_consult.id)]
    assert ids(search(client, postedBy="company")) == [str(j_startup.id)]
    # company: by id and by name, csv
    assert ids(search(client, company=str(consult.id))) == [str(j_consult.id)]
    assert ids(search(client, company="spark labs")) == [str(j_startup.id)]
    assert set(ids(search(client, company=f"{consult.id},Spark Labs"))) == {str(j_consult.id), str(j_startup.id)}
    assert_error(search(client, postedBy="agency"), 422, "VALIDATION_ERROR")


def test_filter_job_type_employment_type_work_mode(client, company, recruiter, make_job):
    a = make_job(company, recruiter, title="A", job_type=JobType.CONTRACT, employment_type=EmploymentType.PART_TIME,
                 work_mode=WorkMode.REMOTE)
    b = make_job(company, recruiter, title="B", job_type=JobType.PERMANENT, employment_type=EmploymentType.FULL_TIME,
                 work_mode=WorkMode.ONSITE)
    assert ids(search(client, jobType="CONTRACT")) == [str(a.id)]
    assert ids(search(client, jobType="permanent")) == [str(b.id)]
    assert ids(search(client, employmentType="PART_TIME")) == [str(a.id)]
    assert ids(search(client, employmentType="full_time")) == [str(b.id)]
    assert ids(search(client, workMode="REMOTE")) == [str(a.id)]
    assert set(ids(search(client, workMode="REMOTE,ONSITE"))) == {str(a.id), str(b.id)}
    assert ids(search(client, workMode="HYBRID")) == []


def test_filter_education(client, company, recruiter, make_job):
    a = make_job(company, recruiter, title="A", education="B.Tech")
    make_job(company, recruiter, title="B", education="MBA")
    assert ids(search(client, education="b.tech")) == [str(a.id)]


def test_filter_freshness(client, company, recruiter, make_job):
    fresh = make_job(company, recruiter, title="Fresh", posted_at=now() - timedelta(hours=5))
    week = make_job(company, recruiter, title="Week", posted_at=now() - timedelta(days=5))
    stale = make_job(company, recruiter, title="Stale", posted_at=now() - timedelta(days=20))
    assert ids(search(client, freshness=1)) == [str(fresh.id)]
    assert set(ids(search(client, freshness=7))) == {str(fresh.id), str(week.id)}
    assert set(ids(search(client, freshness=30))) == {str(fresh.id), str(week.id), str(stale.id)}
    assert_error(search(client, freshness=5), 422, "VALIDATION_ERROR")


def test_filter_walk_in(client, company, recruiter, make_job):
    walk = make_job(company, recruiter, title="Walk", is_walk_in=True,
                    walk_in_details={"venue": "Office 1", "time": "10:00"})
    make_job(company, recruiter, title="Regular")
    assert ids(search(client, walkIn="true")) == [str(walk.id)]
    assert len(ids(search(client, walkIn="false"))) == 2


def test_filters_combine_with_query(client, master_skills, company, recruiter, make_job):
    match = make_job(company, recruiter, title="Python Developer", locations=["Pune"], work_mode=WorkMode.REMOTE)
    make_job(company, recruiter, title="Python Developer", locations=["Delhi"], work_mode=WorkMode.REMOTE)
    make_job(company, recruiter, title="Python Developer", locations=["Pune"], work_mode=WorkMode.ONSITE)
    assert ids(search(client, q="python", location="Pune", workMode="REMOTE")) == [str(match.id)]


# --------------------------------------------------------------------------- sort / pagination / facets


def test_sort_relevance_vs_date(client, master_skills, company, recruiter, make_job):
    newer_desc_only = make_job(company, recruiter, title="Office Manager", required_skills=["Excel"],
                               description="python is nice to have", posted_at=now() - timedelta(hours=1))
    older_title = make_job(company, recruiter, title="Python Developer", posted_at=now() - timedelta(days=4))
    assert ids(search(client, q="python", sort="relevance")) == [str(older_title.id), str(newer_desc_only.id)]
    assert ids(search(client, q="python", sort="date")) == [str(newer_desc_only.id), str(older_title.id)]
    assert ids(search(client, q="python")) == [str(older_title.id), str(newer_desc_only.id)]  # default = relevance
    assert_error(search(client, sort="popularity"), 422, "VALIDATION_ERROR")


def test_pagination_meta_and_totals(client, company, recruiter, make_job):
    for i in range(5):
        make_job(company, recruiter, title=f"Job {i}", posted_at=now() - timedelta(hours=i))
    p1 = assert_paged(search(client, page=1, pageSize=2))
    p2 = assert_paged(search(client, page=2, pageSize=2))
    p3 = assert_paged(search(client, page=3, pageSize=2))
    assert [len(p["data"]) for p in (p1, p2, p3)] == [2, 2, 1]
    assert p1["meta"]["page"] == 1 and p1["meta"]["pageSize"] == 2 and p1["meta"]["total"] == 5
    assert p3["meta"]["total"] == 5
    all_ids = [i["id"] for p in (p1, p2, p3) for i in p["data"]]
    assert len(set(all_ids)) == 5
    beyond = assert_paged(search(client, page=9, pageSize=2))
    assert beyond["data"] == [] and beyond["meta"]["total"] == 5


def test_page_size_is_capped_and_invalid_page_rejected(client, company, recruiter, make_job):
    make_job(company, recruiter)
    body = assert_paged(search(client, pageSize=1000))
    assert body["meta"]["pageSize"] == 100
    assert_error(search(client, page=0), 422, "VALIDATION_ERROR")
    assert_error(search(client, pageSize=0), 422, "VALIDATION_ERROR")
    default = assert_paged(search(client))
    assert default["meta"]["page"] == 1 and default["meta"]["pageSize"] == 20


def test_facets_only_in_search_meta(client, make_company, make_recruiter, make_job, master_skills):
    c1 = make_company(name="Alpha", company_type=CompanyType.STARTUP)
    c2 = make_company(name="Beta", company_type=CompanyType.MNC)
    r1, r2 = make_recruiter(c1), make_recruiter(c2)
    j1 = make_job(c1, r1, title="One", locations=["Pune"], industry="IT", work_mode=WorkMode.REMOTE)
    make_job(c1, r1, title="Two", locations=["Pune", "Delhi"], industry="IT", work_mode=WorkMode.ONSITE)
    make_job(c2, r2, title="Three", locations=["Delhi"], industry="Retail", work_mode=WorkMode.ONSITE)

    body = assert_paged(search(client))
    facets = body["meta"]["facets"]
    for key in ("location", "industry", "department", "roleCategory", "jobType", "employmentType", "workMode",
                "companyType", "company", "education"):
        assert key in facets, key
    loc = {f["value"]: f["count"] for f in facets["location"]}
    assert loc == {"Pune": 2, "Delhi": 2}
    ind = {f["value"]: f["count"] for f in facets["industry"]}
    assert ind == {"IT": 2, "Retail": 1}
    assert {f["value"]: f["count"] for f in facets["company"]} == {"Alpha": 2, "Beta": 1}
    assert {f["value"]: f["count"] for f in facets["workMode"]} == {"ONSITE": 2, "REMOTE": 1}
    # a facet ignores its own filter: selecting Pune still shows Delhi counts for the location facet
    filtered = assert_paged(search(client, location="Pune"))
    assert {f["value"] for f in filtered["meta"]["facets"]["location"]} == {"Pune", "Delhi"}
    assert filtered["meta"]["total"] == 2

    # other paged endpoints carry no facets
    skills = assert_paged(client.get("/api/v1/master/skills"))
    assert "facets" not in skills["meta"]
    company_jobs = assert_paged(client.get(f"/api/v1/jobs/{j1.id}/company-jobs"))
    assert "facets" not in company_jobs["meta"]
    assert_paged(client.get(f"/api/v1/companies/{c1.id}/jobs"))


# --------------------------------------------------------------------------- visibility


def test_only_active_non_deleted_jobs_of_approved_companies_are_listed(
    client, make_company, make_recruiter, make_job
):
    approved = make_company(name="Good Co")
    pending = make_company(name="Pending Co", status=CompanyStatus.PENDING)
    blocked = make_company(name="Blocked Co", status=CompanyStatus.BLOCKED)
    rec = make_recruiter(approved)
    visible = make_job(approved, rec, title="Visible Python")
    make_job(approved, rec, title="Draft Python", status=JobStatus.DRAFT, posted_at=None, expires_at=None)
    make_job(approved, rec, title="Review Python", status=JobStatus.PENDING_REVIEW)
    make_job(approved, rec, title="Paused Python", status=JobStatus.PAUSED)
    make_job(approved, rec, title="Closed Python", status=JobStatus.CLOSED)
    make_job(approved, rec, title="Rejected Python", status=JobStatus.REJECTED)
    make_job(approved, rec, title="Expired status Python", status=JobStatus.EXPIRED)
    make_job(approved, rec, title="Past expiry Python", expires_at=now() - timedelta(days=1))
    make_job(approved, rec, title="Deleted Python", deleted_at=now())
    make_job(pending, make_recruiter(pending), title="Pending company Python")
    make_job(blocked, make_recruiter(blocked), title="Blocked company Python")

    for params in ({}, {"q": "python"}):
        body = assert_paged(search(client, **params))
        assert [i["id"] for i in body["data"]] == [str(visible.id)]
        assert body["meta"]["total"] == 1


def test_soft_deleted_company_jobs_are_hidden(client, db, make_company, make_recruiter, make_job):
    company = make_company()
    make_job(company, make_recruiter(company))
    assert len(ids(search(client))) == 1
    company.deleted_at = now()
    db.commit()
    assert ids(search(client)) == []


# --------------------------------------------------------------------------- job detail


def test_job_detail_for_seeker_has_flags_and_match_score(
    client, db, master_skills, company, recruiter, make_job, make_seeker_with_skills, auth_headers
):
    job = make_job(company, recruiter, title="Backend Engineer", required_skills=["Python", "Java"])
    seeker = make_seeker_with_skills(["python"])
    headers = auth_headers(seeker)

    data = assert_ok(client.get(f"/api/v1/jobs/{job.id}", headers=headers))["data"]
    assert data["id"] == str(job.id)
    assert data["isApplied"] is False and data["isSaved"] is False
    ms = data["matchScore"]
    assert ms == {"percentage": 50, "matchingSkills": ["Python"], "missingSkills": ["Java"]}
    assert data["company"]["name"] == "Globex"
    assert "screeningQuestions" in data

    assert_ok(client.post(f"/api/v1/jobs/{job.id}/save", headers=headers), 201)
    from app.models.applications import Application
    db.add(Application(job_id=job.id, user_id=seeker.id, status=ApplicationStatus.APPLIED))
    db.commit()
    data = assert_ok(client.get(f"/api/v1/jobs/{job.id}", headers=headers))["data"]
    assert data["isSaved"] is True and data["isApplied"] is True


def test_job_detail_anonymous_has_no_personal_flags(client, company, recruiter, make_job):
    job = make_job(company, recruiter)
    data = assert_ok(client.get(f"/api/v1/jobs/{job.id}"))["data"]
    assert data["isApplied"] is False and data["isSaved"] is False
    assert data["matchScore"] is None


def test_job_detail_full_match_when_no_required_skills(client, company, recruiter, make_job, make_seeker_with_skills,
                                                       auth_headers):
    job = make_job(company, recruiter, required_skills=[])
    seeker = make_seeker_with_skills([])
    data = assert_ok(client.get(f"/api/v1/jobs/{job.id}", headers=auth_headers(seeker)))["data"]
    assert data["matchScore"]["percentage"] == 100


def test_view_count_increments_once_per_user_per_day(client, db, company, recruiter, make_job, make_user, auth_headers,
                                                     reload):
    job = make_job(company, recruiter)
    u1, u2 = make_user(), make_user()
    h1, h2 = auth_headers(u1), auth_headers(u2)

    first = assert_ok(client.get(f"/api/v1/jobs/{job.id}", headers=h1))["data"]
    assert first["viewCount"] == 1
    assert assert_ok(client.get(f"/api/v1/jobs/{job.id}", headers=h1))["data"]["viewCount"] == 1
    assert assert_ok(client.get(f"/api/v1/jobs/{job.id}", headers=h2))["data"]["viewCount"] == 2
    # anonymous views are not attributable to a user and are not counted
    assert assert_ok(client.get(f"/api/v1/jobs/{job.id}"))["data"]["viewCount"] == 2
    assert reload(job).view_count == 2

    # the same user the next day counts again
    db.query(JobView).filter(JobView.user_id == u1.id).update({"view_date": date.today() - timedelta(days=1)})
    db.commit()
    assert assert_ok(client.get(f"/api/v1/jobs/{job.id}", headers=h1))["data"]["viewCount"] == 3
    assert db.query(JobView).filter(JobView.job_id == job.id).count() == 3


def test_unknown_job_is_404(client):
    err = assert_error(client.get(f"/api/v1/jobs/{uuid.uuid4()}"), 404, "NOT_FOUND")
    assert err["message"]
    assert_error(client.get("/api/v1/jobs/not-a-uuid"), 422, "VALIDATION_ERROR")


def test_non_public_jobs_are_404_for_public_but_visible_to_owner(
    client, make_company, make_recruiter, make_job, auth_headers
):
    pending = make_company(status=CompanyStatus.PENDING)
    rec = make_recruiter(pending)
    other_rec = make_recruiter(make_company())
    draft = make_job(make_company(), None, status=JobStatus.DRAFT)
    pending_job = make_job(pending, rec, title="Pending co job")
    assert_error(client.get(f"/api/v1/jobs/{draft.id}"), 404, "NOT_FOUND")
    assert_error(client.get(f"/api/v1/jobs/{pending_job.id}"), 404, "NOT_FOUND")
    assert_error(client.get(f"/api/v1/jobs/{pending_job.id}", headers=auth_headers(other_rec)), 404, "NOT_FOUND")
    assert_ok(client.get(f"/api/v1/jobs/{pending_job.id}", headers=auth_headers(rec)))


def test_expired_job_detail_is_404(client, company, recruiter, make_job):
    job = make_job(company, recruiter, expires_at=now() - timedelta(hours=1))
    assert_error(client.get(f"/api/v1/jobs/{job.id}"), 404, "NOT_FOUND")


def test_similar_and_company_jobs(client, master_skills, company, recruiter, make_job):
    a = make_job(company, recruiter, title="Python Developer")
    b = make_job(company, recruiter, title="Senior Python Developer")
    resp = assert_ok(client.get(f"/api/v1/jobs/{a.id}/similar"))
    assert isinstance(resp["data"], list)
    comp = assert_paged(client.get(f"/api/v1/jobs/{a.id}/company-jobs"))
    assert [i["id"] for i in comp["data"]] == [str(b.id)]


# --------------------------------------------------------------------------- suggestions / master data


def test_suggestions_by_type(client, master_skills, company, recruiter, make_job):
    make_job(company, recruiter, title="Python Developer")
    skills = assert_ok(client.get("/api/v1/suggestions", params={"q": "pyth", "type": "skill"}))["data"]
    assert "Python" in skills
    jobs = assert_ok(client.get("/api/v1/suggestions", params={"q": "python", "type": "job"}))["data"]
    assert jobs == ["Python Developer"]
    companies = assert_ok(client.get("/api/v1/suggestions", params={"q": "glob", "type": "company"}))["data"]
    assert companies[0]["name"] == "Globex"
    # synonym prefix
    assert "JavaScript" in assert_ok(client.get("/api/v1/suggestions", params={"q": "ecma", "type": "skill"}))["data"]
    # typo tolerant
    assert "Python" in assert_ok(client.get("/api/v1/suggestions", params={"q": "pythn", "type": "skill"}))["data"]


def test_suggestions_grouped_without_type_and_limit(client, master_skills, company, recruiter, make_job):
    make_job(company, recruiter, title="Python Developer")
    data = assert_ok(client.get("/api/v1/suggestions", params={"q": "py"}))["data"]
    assert set(data) == {"jobs", "skills", "companies", "locations"}
    limited = assert_ok(client.get("/api/v1/suggestions", params={"q": "j", "type": "skill", "limit": 1}))["data"]
    assert len(limited) == 1


def test_suggestions_requires_q(client):
    assert_error(client.get("/api/v1/suggestions"), 422, "VALIDATION_ERROR")


def test_master_skills_list_search_and_pagination(client, master_skills):
    body = assert_paged(client.get("/api/v1/master/skills"))
    names = [i["name"] for i in body["data"]]
    assert names == ["Java", "JavaScript", "Python", "React", "SQL"]
    assert body["meta"]["total"] == 5
    js = next(i for i in body["data"] if i["name"] == "JavaScript")
    assert js["synonyms"] == ["js", "ecmascript"] and uuid.UUID(js["id"])

    q = assert_paged(client.get("/api/v1/master/skills", params={"q": "java"}))
    assert [i["name"] for i in q["data"]] == ["Java", "JavaScript"]
    page = assert_paged(client.get("/api/v1/master/skills", params={"pageSize": 2, "page": 2}))
    assert [i["name"] for i in page["data"]] == ["Python", "React"]
    assert page["meta"]["total"] == 5


def test_master_unknown_type_404(client):
    assert_error(client.get("/api/v1/master/unicorns"), 404, "NOT_FOUND")


def test_master_other_types_exposed(client, db):
    from app.models.master import Industry, Location

    db.add_all([Industry(name="Banking"), Location(name="Pune", state="MH", country="India")])
    db.commit()
    ind = assert_paged(client.get("/api/v1/master/industries"))["data"]
    assert [i["name"] for i in ind] == ["Banking"]
    loc = assert_paged(client.get("/api/v1/master/locations"))["data"]
    assert loc[0]["name"] == "Pune" and loc[0]["state"] == "MH"


def test_public_company_page(client, company, recruiter, make_job):
    make_job(company, recruiter)
    data = assert_ok(client.get(f"/api/v1/companies/{company.id}"))["data"]
    assert data["name"] == "Globex" and data["activeJobsCount"] == 1
    assert_error(client.get(f"/api/v1/companies/{uuid.uuid4()}"), 404, "NOT_FOUND")


def test_company_model_default_is_not_leaked(client, make_company):
    pending = make_company(status=CompanyStatus.PENDING)
    assert isinstance(pending, Company)
    assert_error(client.get(f"/api/v1/companies/{pending.id}"), 404, "NOT_FOUND")
