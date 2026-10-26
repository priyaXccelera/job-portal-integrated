"""Job-seeker profile, resumes, privacy and profile-view endpoints (JOB_SEEKER only)."""

import uuid

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.core.responses import PageParams, ok, page_params, paged, paginate
from app.models.accounts import User
from app.schemas.common import UserRole
from app.schemas.profile import (
    CareerPreferencesUpdate,
    CertificationCreate,
    CertificationUpdate,
    EducationCreate,
    EducationUpdate,
    EmploymentCreate,
    EmploymentUpdate,
    HiddenCompanyCreate,
    LanguageItem,
    LanguagesBody,
    OnlineProfilesUpdate,
    PrivacyUpdate,
    ProfileUpdate,
    ProjectCreate,
    ProjectUpdate,
    SkillItem,
    SkillsReplace,
)
from app.services import matching
from app.services import profile_service as svc

router = APIRouter(tags=["profile"])

seeker_only = require_roles(UserRole.JOB_SEEKER)


# --------------------------------------------------------------------------- basics
@router.get("/profile/me")
def get_profile(user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    payload = svc.build_profile(db, user)
    db.commit()  # persists an auto-created profile row
    return ok(payload)


@router.put("/profile/me")
def update_profile(body: ProfileUpdate, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    svc.update_profile(db, user, body)
    return ok(svc.build_profile(db, user))


@router.get("/profile/completeness")
def get_completeness(user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok(matching.profile_completeness(db, user.id))


@router.post("/profile/photo")
def upload_photo(
    file: UploadFile = File(...), user: User = Depends(seeker_only), db: Session = Depends(get_db)
):
    return ok(svc.save_photo(db, user.id, file.filename or "", file.content_type, file.file))


# --------------------------------------------------------------------------- skills
@router.get("/profile/skills")
def get_skills(user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok(svc.list_skills(db, user.id))


@router.put("/profile/skills")
def put_skills(
    body: list[SkillItem] | SkillsReplace = Body(...),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    items = body if isinstance(body, list) else body.skills
    return ok(svc.replace_skills(db, user.id, items))


@router.post("/profile/skills")
def post_skill(body: SkillItem, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    data, created = svc.add_skill(db, user.id, body)
    return ok(data, status_code=201 if created else 200)


@router.delete("/profile/skills/{skill_id}")
def delete_skill(skill_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    svc.remove_skill(db, user.id, skill_id)
    return ok({"deleted": True})


# --------------------------------------------------------------------------- child record CRUD
def _register_crud(path: str, spec: svc.ChildSpec, create_model, update_model) -> None:
    @router.get(f"/profile/{path}", name=f"list_{path}")
    def list_items(user: User = Depends(seeker_only), db: Session = Depends(get_db)):
        return ok([svc.serialize_child(spec, o) for o in svc.list_children(db, spec, user.id)])

    @router.post(f"/profile/{path}", name=f"create_{path}")
    def create_item(body: create_model, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
        return ok(svc.serialize_child(spec, svc.create_child(db, spec, user.id, body)), status_code=201)

    @router.put(f"/profile/{path}/{{item_id}}", name=f"update_{path}")
    def update_item(
        item_id: uuid.UUID, body: update_model, user: User = Depends(seeker_only), db: Session = Depends(get_db)
    ):
        return ok(svc.serialize_child(spec, svc.update_child(db, spec, user.id, item_id, body)))

    @router.delete(f"/profile/{path}/{{item_id}}", name=f"delete_{path}")
    def delete_item(item_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
        svc.delete_child(db, spec, user.id, item_id)
        return ok({"deleted": True})


_register_crud("employments", svc.EMPLOYMENT, EmploymentCreate, EmploymentUpdate)
_register_crud("educations", svc.EDUCATION, EducationCreate, EducationUpdate)
_register_crud("projects", svc.PROJECT, ProjectCreate, ProjectUpdate)
_register_crud("certifications", svc.CERTIFICATION, CertificationCreate, CertificationUpdate)


# --------------------------------------------------------------------------- languages / links / preferences
@router.put("/profile/languages")
def put_languages(
    body: list[LanguageItem] | LanguagesBody = Body(...),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    items = body if isinstance(body, list) else body.languages
    return ok(svc.set_languages(db, user.id, items))


@router.put("/profile/online-profiles")
def put_online_profiles(
    body: OnlineProfilesUpdate, user: User = Depends(seeker_only), db: Session = Depends(get_db)
):
    return ok(svc.set_online_profiles(db, user.id, body))


@router.get("/profile/career-preferences")
def get_career_preferences(user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok(svc.get_career_preferences(db, user.id))


@router.put("/profile/career-preferences")
def put_career_preferences(
    body: CareerPreferencesUpdate, user: User = Depends(seeker_only), db: Session = Depends(get_db)
):
    return ok(svc.set_career_preferences(db, user.id, body))


# --------------------------------------------------------------------------- privacy
@router.get("/profile/privacy")
def get_privacy(user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok(svc.get_privacy(db, user.id))


@router.put("/profile/privacy")
def put_privacy(body: PrivacyUpdate, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok(svc.set_privacy(db, user.id, body))


@router.get("/profile/hidden-companies")
def get_hidden_companies(user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok(svc.list_hidden_companies(db, user.id))


@router.post("/profile/hidden-companies")
def post_hidden_company(
    body: HiddenCompanyCreate, user: User = Depends(seeker_only), db: Session = Depends(get_db)
):
    data, created = svc.hide_company(db, user.id, body.company_id)
    return ok(data, status_code=201 if created else 200)


@router.delete("/profile/hidden-companies/{company_id}")
def delete_hidden_company(company_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    svc.unhide_company(db, user.id, company_id)
    return ok({"deleted": True})


@router.get("/profile/views")
def get_profile_views(
    params: PageParams = Depends(page_params), user: User = Depends(seeker_only), db: Session = Depends(get_db)
):
    rows, total = paginate(db, svc.views_statement(user.id), params)
    return paged([svc.serialize_view(r) for r in rows], params.page, params.page_size, total)


# --------------------------------------------------------------------------- resumes
@router.post("/resumes")
def upload_resume(
    file: UploadFile = File(...),
    is_default: bool = Form(False, alias="isDefault"),
    user: User = Depends(seeker_only),
    db: Session = Depends(get_db),
):
    resume = svc.save_resume(db, user.id, file.filename or "", file.content_type, file.file, is_default)
    return ok(svc.serialize_resume(resume), status_code=201)


@router.get("/resumes")
def get_resumes(user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok([svc.serialize_resume(r) for r in svc.list_resumes(db, user.id)])


@router.get("/resumes/{resume_id}/download")
def download_resume(resume_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    resume = svc.get_owned_resume(db, user.id, resume_id)
    path = svc.resume_file_path(resume)
    return FileResponse(path, media_type=resume.content_type or "application/octet-stream", filename=resume.file_name)


@router.patch("/resumes/{resume_id}/default")
def make_default_resume(resume_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok(svc.serialize_resume(svc.set_default_resume(db, user.id, resume_id)))


@router.post("/resumes/{resume_id}/parse")
def parse_resume(resume_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    return ok(svc.parse_resume(db, user.id, resume_id))


@router.delete("/resumes/{resume_id}")
def delete_resume(resume_id: uuid.UUID, user: User = Depends(seeker_only), db: Session = Depends(get_db)):
    svc.delete_resume(db, user.id, resume_id)
    return ok({"deleted": True})
