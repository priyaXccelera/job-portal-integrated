"""Import every model module so Base.metadata is complete (order does not matter)."""

from app.models import accounts, applications, company, enums, jobs, master, profile  # noqa: F401
from app.models.accounts import (  # noqa: F401
    AuditLog,
    EmailToken,
    Notification,
    NotificationPreference,
    OtpCode,
    RefreshToken,
    ResetToken,
    User,
)
from app.models.applications import (  # noqa: F401
    Application,
    ApplicationAnswer,
    ApplicationNote,
    Interview,
    Message,
    MessageThread,
    StatusHistory,
)
from app.models.company import (  # noqa: F401
    CandidateFolder,
    CandidateInvite,
    Company,
    CompanyFollow,
    CompanyReview,
    ContactUnlock,
    CreditLog,
    FolderCandidate,
    Invitation,
)
from app.models.jobs import (  # noqa: F401
    Job,
    JobAlert,
    JobReport,
    JobView,
    RecentSearch,
    SavedJob,
    SavedSearch,
    ScreeningQuestion,
)
from app.models.master import (  # noqa: F401
    MASTER_TYPES,
    Degree,
    Department,
    Industry,
    Location,
    NoticePeriodOption,
    RoleCategory,
    Skill,
)
from app.models.profile import (  # noqa: F401
    Certification,
    Education,
    Employment,
    HiddenCompany,
    JobSeekerProfile,
    ProfileSkill,
    ProfileView,
    Project,
    Resume,
)
