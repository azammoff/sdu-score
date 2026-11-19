from fastapi import APIRouter, Depends, Path, status

from app.deps import get_store, require_admin
from app.schemas.faculty import FacultyCreate, FacultyRead, FacultyUpdate
from app.schemas.team import TeamRead
from app.services import faculties as service

router = APIRouter(prefix="/faculties", tags=["Faculties"])
admin = [Depends(require_admin)]
FacultyId = Path(gt=0, description="Faculty ID")


@router.get("", response_model=list[FacultyRead], summary="List faculties")
def list_faculties(store=Depends(get_store)):
    return service.list_faculties(store)


@router.post("", response_model=FacultyRead, status_code=status.HTTP_201_CREATED, dependencies=admin)
def create_faculty(data: FacultyCreate, store=Depends(get_store)):
    return service.create_faculty(store, data)


@router.get("/{faculty_id}", response_model=FacultyRead)
def get_faculty(faculty_id: int = FacultyId, store=Depends(get_store)):
    return service.get_faculty(store, faculty_id)


@router.patch("/{faculty_id}", response_model=FacultyRead, dependencies=admin)
def update_faculty(data: FacultyUpdate, faculty_id: int = FacultyId, store=Depends(get_store)):
    return service.update_faculty(store, faculty_id, data)


@router.delete("/{faculty_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=admin)
def delete_faculty(faculty_id: int = FacultyId, store=Depends(get_store)):
    service.delete_faculty(store, faculty_id)


@router.get("/{faculty_id}/teams", response_model=list[TeamRead], summary="Teams of a faculty")
def list_faculty_teams(faculty_id: int = FacultyId, store=Depends(get_store)):
    return service.list_faculty_teams(store, faculty_id)
