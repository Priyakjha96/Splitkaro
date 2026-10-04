from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI()

# Seekhne ke liye abhi yahan likha hai. Real project me ye .env se aata hai
# aur kabhi GitHub pe nahi jata.
SECRET_KEY = "dev-secret-change-me"
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60

bearer_scheme = HTTPBearer()


class UserCreate(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class GroupCreate(BaseModel):
    name: str


class MemberAdd(BaseModel):
    user_id: int


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def is_member(db: Session, group_id: int, user_id: int) -> bool:
    row = (
        db.query(models.GroupMember)
        .filter(models.GroupMember.group_id == group_id, models.GroupMember.user_id == user_id)
        .first()
    )
    return row is not None


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

    return {
        "access_token": create_token(user.id),
        "token_type": "bearer",
        "user_id": user.id,
        "name": user.name,
    }


@app.get("/me")
def me(current_user: models.User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email}


@app.post("/groups")
def create_group(
    data: GroupCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    group = models.Group(name=data.name, created_by=current_user.id)
    db.add(group)
    db.flush()
    db.add(models.GroupMember(group_id=group.id, user_id=current_user.id))
    db.commit()
    return {"id": group.id, "name": group.name, "created_by": group.created_by}


@app.post("/groups/{group_id}/members")
def add_member(
    group_id: int,
    data: MemberAdd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    if not is_member(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this group")

    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if is_member(db, group_id, data.user_id):
        raise HTTPException(status_code=400, detail="User already in group")

    db.add(models.GroupMember(group_id=group_id, user_id=data.user_id))
    db.commit()
    return {"message": f"{user.name} added to {group.name}"}


@app.get("/groups/{group_id}")
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    if not is_member(db, group_id, current_user.id):
        raise HTTPException(status_code=403, detail="You are not a member of this group")

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