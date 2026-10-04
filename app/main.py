import bcrypt
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI()


class UserCreate(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class GroupCreate(BaseModel):
    name: str
    created_by: int


class MemberAdd(BaseModel):
    user_id: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f"Namaste {name}, SplitKaro me swagat hai"}


@app.post("/users")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()

    new_user = models.User(name=user.name, email=user.email, password_hash=hashed)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"id": new_user.id, "name": new_user.name, "email": new_user.email}


@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return [{"id": u.id, "name": u.name, "email": u.email} for u in users]


@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == data.email).first()

    if user is None or not bcrypt.checkpw(data.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Wrong email or password")

    return {"message": "Login successful", "user_id": user.id, "name": user.name}


@app.post("/groups")
def create_group(data: GroupCreate, db: Session = Depends(get_db)):
    creator = db.query(models.User).filter(models.User.id == data.created_by).first()
    if creator is None:
        raise HTTPException(status_code=404, detail="User not found")

    group = models.Group(name=data.name, created_by=data.created_by)
    db.add(group)
    db.flush()
    db.add(models.GroupMember(group_id=group.id, user_id=data.created_by))
    db.commit()
    return {"id": group.id, "name": group.name, "created_by": group.created_by}


@app.post("/groups/{group_id}/members")
def add_member(group_id: int, data: MemberAdd, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    already = (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id == data.user_id)
        .first()
    )
    if already:
        raise HTTPException(status_code=400, detail="User already in group")

    db.add(models.GroupMember(group_id=group_id, user_id=data.user_id))
    db.commit()
    return {"message": f"{user.name} added to {group.name}"}


@app.get("/groups/{group_id}")
def get_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    members = (
        db.query(models.User)
        .join(models.GroupMember, models.GroupMember.user_id == models.User.id)
        .filter(models.GroupMember.group_id == group_id)
        .all()
    )
    return {
        "id": group.id,
        "name": group.name,
        "members": [{"id": m.id, "name": m.name} for m in members],
    }