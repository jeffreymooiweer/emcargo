"""Departments, for the administrator; the list, for everybody.

Mounted with the history (see ``main.py``): a department decides who sees
whose kept shipments and means nothing without them. Everybody signed in
may read the list, because the shipments page and the users page show
names rather than ids; only an administrator changes it.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_manager
from app.models.user import Department, User
from app.services import departments

router = APIRouter(prefix="/departments", tags=["departments"])


class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def _department(department_id: int, db: Session) -> Department:
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="No such department")
    return department


@router.get("")
def list_departments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return departments.listing(db)


@router.post("")
def create_department(payload: DepartmentIn, admin: User = Depends(require_manager),
                      db: Session = Depends(get_db)):
    try:
        created = departments.create(db, payload.name)
    except departments.DepartmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": created.id, "name": created.name, "users": 0, "shipments": 0}


@router.put("/{department_id}")
def rename_department(department_id: int, payload: DepartmentIn,
                      admin: User = Depends(require_manager), db: Session = Depends(get_db)):
    try:
        renamed = departments.rename(db, _department(department_id, db), payload.name)
    except departments.DepartmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": renamed.id, "name": renamed.name}


@router.delete("/{department_id}")
def delete_department(department_id: int, admin: User = Depends(require_manager),
                      db: Session = Depends(get_db)):
    return departments.remove(db, _department(department_id, db))
