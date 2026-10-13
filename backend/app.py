from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
import sqlite3
import os
import secrets
import hashlib
import time
import jwt
from fastapi.middleware.cors import CORSMiddleware

# Configuration
DB_PATH = os.environ.get("AUTH_DB", "backend/auth.db")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "change_me_admin_token")
JWT_SECRET = os.environ.get("SECRET_KEY", "change_me_secret")
JWT_ALGO = "HS256"
CODE_TTL_SECONDS = int(os.environ.get("CODE_TTL_SECONDS", "300"))  # 5 minutes

app = FastAPI(title="TradingBot Auth Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure DB exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
)
""")
conn.commit()


def hash_code(code: str, salt: str) -> str:
    return hashlib.sha256((salt + code).encode('utf-8')).hexdigest()


class GenerateResponse(BaseModel):
    code: str
    expires_at: int


class VerifyRequest(BaseModel):
    code: str


class VerifyResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int


@app.post("/auth/generate", response_model=GenerateResponse)
def generate_code(request: Request):
    """Generate a one-time code. This endpoint requires an admin token header X-ADMIN-TOKEN.
    Returns the raw code only to the caller with the admin token. The code is stored hashed in the DB and expires in CODE_TTL_SECONDS.
    """
    admin = request.headers.get("X-ADMIN-TOKEN")
    if admin != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="admin token required")

    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    salt = secrets.token_hex(8)
    code_hash = hash_code(code, salt)
    expires_at = int(time.time()) + CODE_TTL_SECONDS

    cur.execute("INSERT INTO codes (code_hash, salt, expires_at, used) VALUES (?, ?, ?, 0)", (code_hash, salt, expires_at))
    conn.commit()

    return {"code": code, "expires_at": expires_at}


@app.post("/auth/verify", response_model=VerifyResponse)
def verify_code(payload: VerifyRequest):
    """Verify a one-time code and return a JWT access token. The code is single-use and expires after use or after TTL.
    """
    code = payload.code.strip()
    now = int(time.time())

    # fetch candidate codes that are not used and not expired
    cur.execute("SELECT id, code_hash, salt, expires_at, used FROM codes WHERE used=0 AND expires_at>=? ORDER BY id DESC", (now,))
    rows = cur.fetchall()
    for r in rows:
        cid, chash, salt, expires_at, used = r
        if hash_code(code, salt) == chash:
            # mark used
            cur.execute("UPDATE codes SET used=1 WHERE id=?", (cid,))
            conn.commit()
            # issue JWT
            exp = now + 3600  # 1 hour
            token = jwt.encode({"sub": "otp_user", "exp": exp}, JWT_SECRET, algorithm=JWT_ALGO)
            return {"access_token": token, "expires_at": exp}

    raise HTTPException(status_code=401, detail="invalid_or_expired_code")


@app.get("/auth/status")
def status():
    return {"status": "ok", "time": int(time.time())}
