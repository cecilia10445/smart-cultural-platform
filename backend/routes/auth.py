"""Native FastAPI authentication endpoints."""

from datetime import datetime, timedelta, timezone
import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.routes._bridge import invoke

router = APIRouter(tags=["auth"])

class LoginPayload(BaseModel):
    username: str = ""
    password: str = ""
    role: str = "user"

@router.post("/api/login")
def login(payload: LoginPayload):
    from backend.routes import api
    username, password = payload.username.strip(), payload.password.strip()
    if not username or not password:
        raise HTTPException(400, "用户名和密码不能为空")
    for user in api.users_data.get("users", []) + api.users_data.get("admins", []):
        if user["username"] == username and api.verify_and_migrate_password(user, password):
            if payload.role != user["role"]:
                raise HTTPException(401, "角色选择错误")
            if not api.JWT_SECRET:
                raise HTTPException(503, "Authentication service is not configured.")
            user["last_login"] = datetime.now().isoformat()
            token = jwt.encode({"user_id": user["user_id"], "username": username, "role": user["role"], "exp": datetime.now(timezone.utc) + timedelta(days=1)}, api.JWT_SECRET, algorithm=api.JWT_ALGORITHM)
            return {"status": "success", "message": "登录成功", "token": token, "user": {key: value for key, value in user.items() if key not in {"password", "password_hash"}}}
    raise HTTPException(401, "用户名或密码错误")


@router.post("/api/register")
async def register(request):
    from backend.routes import api
    return await invoke(api.register, request)
