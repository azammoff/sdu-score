from app.errors import ConflictError
from app.schemas.faculty import FacultyCreate, FacultyUpdate
from app.services.common import changes, get_or_404


def _check_unique(store, name: str | None, code: str | None, exclude_id: int | None = None) -> None:
    for f in store.faculties.all():
        if f.id == exclude_id:
            continue
        if name and f.name.lower() == name.lower():
            raise ConflictError(f"Faculty named '{name}' already exists")
        if code and f.code == code:
            raise ConflictError(f"Faculty code '{code}' is already used")


def list_faculties(store):
    return sorted(store.faculties.all(), key=lambda f: f.name)


def get_faculty(store, faculty_id: int):
    return get_or_404(store.faculties, faculty_id, "Faculty")


def create_faculty(store, data: FacultyCreate):
    _check_unique(store, data.name, data.code)
    faculty = store.faculties.add(name=data.name, code=data.code)
    store.commit()
    return faculty


def update_faculty(store, faculty_id: int, data: FacultyUpdate):
    faculty = get_faculty(store, faculty_id)
    fields = changes(data)
    _check_unique(store, fields.get("name"), fields.get("code"), exclude_id=faculty_id)
    store.faculties.update(faculty, **fields)
    store.commit()
    return faculty


def delete_faculty(store, faculty_id: int) -> None:
    faculty = get_faculty(store, faculty_id)
    teams = store.teams.where(faculty_id=faculty_id)
    if teams:
        raise ConflictError(
            f"Faculty has {len(teams)} team(s); move or delete them first",
            details={"team_ids": [t.id for t in teams]},
        )
    store.faculties.delete(faculty)
    store.commit()


def list_faculty_teams(store, faculty_id: int):
    get_faculty(store, faculty_id)
    return sorted(store.teams.where(faculty_id=faculty_id), key=lambda t: t.name)
