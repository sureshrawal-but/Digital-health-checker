import json
import os
import hashlib
import secrets
import datetime
import re
import time
import jwt
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from health_checker import DigitalHealthChecker

USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
TOKEN_EXPIRY_DAYS = 7
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15

# ── App ──

app = FastAPI(
    title="Digital Health Checker API",
    description="Analyze and score the digital presence of any website",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ── Security Headers Middleware ──

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# ── Rate Limiter ──

login_attempts = {}

def check_rate_limit(identifier: str):
    now = time.time()
    if identifier in login_attempts:
        attempts = login_attempts[identifier]
        # Clean old entries
        attempts = [t for t in attempts if now - t < LOGIN_LOCKOUT_MINUTES * 60]
        if len(attempts) >= MAX_LOGIN_ATTEMPTS:
            retry_after = int(LOGIN_LOCKOUT_MINUTES * 60 - (now - attempts[0]))
            raise HTTPException(
                status_code=429,
                detail=f"Too many login attempts. Try again in {max(1, retry_after // 60)} minutes."
            )
        login_attempts[identifier] = attempts
    else:
        login_attempts[identifier] = []

def record_attempt(identifier: str):
    if identifier not in login_attempts:
        login_attempts[identifier] = []
    login_attempts[identifier].append(time.time())
    # Keep only recent attempts
    login_attempts[identifier] = [t for t in login_attempts[identifier] if time.time() - t < LOGIN_LOCKOUT_MINUTES * 60]

# ── Input Sanitizer ──

def sanitize_string(value: str, max_length: int = 100) -> str:
    if not value:
        return ""
    value = value.strip()
    value = re.sub(r'<[^>]*>', '', value)  # strip HTML tags
    value = re.sub(r'[<>"\'\\;{}()]', '', value)  # strip dangerous chars
    value = value[:max_length]
    return value

# ── Data Models ──

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class BusinessRequest(BaseModel):
    business_name: str
    website_url: Optional[str] = None

class BatchRequest(BaseModel):
    businesses: list[BusinessRequest]

# ── Password Hashing (PBKDF2 with salt) ──

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return f"{salt}${pwd_hash.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        if "$" in stored:
            salt, pwd_hash = stored.split("$", 1)
            computed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
            return computed.hex() == pwd_hash
        else:
            return hashlib.sha256(password.encode()).hexdigest() == stored
    except (ValueError, AttributeError):
        return False

# ── Password Strength ──

def check_password_strength(password: str) -> Optional[str]:
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r'[A-Za-z]', password):
        return "Password must contain at least one letter"
    if not re.search(r'[0-9]', password):
        return "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-]', password):
        return "Password must contain at least one special character"
    return None

# ── User Storage ──

def load_users():
    if not os.path.exists(USERS_FILE):
        default_admin_pwd = hash_password("Suresh@9848")
        default = {
            "Suresh": {
                "password": default_admin_pwd,
                "role": "admin",
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "searches": []
            }
        }
        with open(USERS_FILE, "w") as f:
            json.dump(default, f, indent=2)
        return default
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# ── JWT ──

def create_token(username, role):
    jti = secrets.token_hex(16)
    payload = {
        "username": username,
        "role": role,
        "jti": jti,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=TOKEN_EXPIRY_DAYS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid token format")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token expired or invalid. Please login again.")
    return payload

# ── Frontend ──

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"), media_type="text/html")

# ── Auth Endpoints ──

@app.post("/auth/register")
def register(req: RegisterRequest):
    username = sanitize_string(req.username, 30)
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        raise HTTPException(status_code=400, detail="Username can only contain letters, numbers, and underscores")

    pwd_error = check_password_strength(req.password)
    if pwd_error:
        raise HTTPException(status_code=400, detail=pwd_error)

    users = load_users()
    if username in users:
        raise HTTPException(status_code=400, detail="Username already exists")

    users[username] = {
        "password": hash_password(req.password),
        "role": "user",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "searches": []
    }
    save_users(users)

    token = create_token(username, "user")
    return {"success": True, "token": token, "username": username, "role": "user"}

@app.post("/auth/login")
def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"

    check_rate_limit(client_ip)

    username = sanitize_string(req.username, 30)
    users = load_users()
    user = users.get(username)

    if not user or not verify_password(req.password, user["password"]):
        record_attempt(client_ip)
        # Don't reveal which field is wrong
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Clear attempts on success
    login_attempts.pop(client_ip, None)

    token = create_token(username, user["role"])
    return {"success": True, "token": token, "username": username, "role": user["role"]}

@app.get("/auth/me")
def me(current_user: dict = Depends(get_current_user)):
    return {"success": True, "username": current_user["username"], "role": current_user["role"]}

# ── Analyze ──

@app.post("/analyze")
def analyze_business(request: BusinessRequest, authorization: str = Header(None)):
    try:
        current_user = get_current_user(authorization)

        name = sanitize_string(request.business_name, 80)
        url = sanitize_string(request.website_url, 200) if request.website_url else None
        if not name:
            raise HTTPException(status_code=400, detail="Business name is required")

        checker = DigitalHealthChecker(name, url)
        report = checker.run_all_checks()
        report["live_checks"] = True

        score = report["total_score"]
        if score >= 80:
            report["ai_summary"] = f"✨ {name} has a strong digital foundation!"
        elif score >= 60:
            report["ai_summary"] = f"📈 {name} is on the right track but has room to grow."
        elif score >= 40:
            report["ai_summary"] = f"🔄 {name} has significant digital gaps that need attention."
        else:
            report["ai_summary"] = f"🚨 {name} is currently digitally invisible. Start with a Google Business Profile and social media pages."

        has_website = bool(url)
        social_platforms = report.get("details", {}).get("social_media", {}).get("platforms_found", [])
        has_social = len(social_platforms) > 0

        recommendations = []
        if not has_website:
            recommendations.append({"priority": "Critical", "action": "Create a website (use platforms like Wix, WordPress, or Squarespace)", "impact": "Opens your business to 24/7 global discovery", "cost": "Free – $20/month"})
        if not has_social:
            recommendations.append({"priority": "High", "action": "Create social media business pages (Facebook, Instagram, LinkedIn)", "impact": "Reach billions of potential customers worldwide", "cost": "Free"})
        recommendations.append({"priority": "High", "action": "Claim and optimize your Google Business Profile", "impact": "Show up in Google Maps and local search results", "cost": "Free"})
        recommendations.append({"priority": "Medium", "action": "Add contact information (phone, email, WhatsApp) to all platforms", "impact": "Makes it easy for customers to reach you", "cost": "Free"})
        if report.get("issues"):
            recommendations.append({"priority": "Medium", "action": "Address the issues listed below to improve your digital presence", "impact": "Improves customer trust and conversion rates", "cost": "Varies"})
        recommendations.append({"priority": "Maintenance", "action": "Ask satisfied customers to leave reviews on Google and social media", "impact": "Builds social proof and improves search ranking", "cost": "Free"})
        report["recommendations"] = recommendations

        roadmap = []
        if not has_website:
            roadmap.append({"week": 1, "task": "Create/improve website", "effort": "2-3 hours"})
        if not has_social:
            roadmap.append({"week": 1, "task": "Set up social media pages", "effort": "1-2 hours"})
        roadmap.append({"week": 2, "task": "Optimize Google Business Profile with photos & info", "effort": "1 hour"})
        roadmap.append({"week": 2, "task": "Add contact details to all platforms", "effort": "30 min"})
        roadmap.append({"week": 3, "task": "Collect reviews from existing customers", "effort": "1 hour"})
        roadmap.append({"week": 4, "task": "Review progress and re-check digital health score", "effort": "30 min"})
        report["roadmap"] = roadmap

        # Track search
        users = load_users()
        if current_user["username"] in users:
            search_entry = {
                "business": name,
                "url": url,
                "score": score,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            users[current_user["username"]]["searches"].append(search_entry)
            save_users(users)

        return {"success": True, "data": report}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Analysis failed. Please try again.")

@app.post("/analyze/batch")
def analyze_batch(request: BatchRequest, authorization: str = Header(None)):
    current_user = get_current_user(authorization)
    results = []
    for biz in request.businesses:
        try:
            name = sanitize_string(biz.business_name, 80)
            url = sanitize_string(biz.website_url, 200) if biz.website_url else None
            checker = DigitalHealthChecker(name, url)
            report = checker.run_all_checks()
            results.append({"business": name, "success": True, "data": report})
        except Exception as e:
            results.append({"business": name, "success": False, "error": "Processing failed"})
    return {"success": True, "results": results}

@app.get("/check-website")
def quick_website_check(url: str):
    url = sanitize_string(url, 200)
    if not url:
        return {"success": False, "error": "URL is required"}
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    try:
        import requests
        resp = requests.get(url, timeout=10, allow_redirects=True)
        return {
            "success": True,
            "url": resp.url,
            "status_code": resp.status_code,
            "ssl": resp.url.startswith('https://'),
            "load_time_seconds": round(resp.elapsed.total_seconds(), 2),
            "content_type": resp.headers.get('Content-Type', 'unknown')
        }
    except Exception:
        return {"success": False, "url": url, "error": "Could not reach the website"}

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "api_version": "2.1.0"
    }

# ── Admin Endpoints ──

@app.get("/admin/users")
def admin_users(authorization: str = Header(None)):
    current_user = get_current_user(authorization)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    users = load_users()
    safe = {}
    for uname, data in users.items():
        safe[uname] = {
            "role": data["role"],
            "created_at": data["created_at"],
            "searches_count": len(data.get("searches", []))
        }
    return {"success": True, "users": safe}

@app.get("/admin/searches")
def admin_searches(authorization: str = Header(None)):
    current_user = get_current_user(authorization)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    users = load_users()
    all_searches = []
    for uname, data in users.items():
        for s in data.get("searches", []):
            safe = {k: v for k, v in s.items() if k in ("username", "business", "url", "score", "timestamp")}
            safe["username"] = uname
            all_searches.append(safe)
    all_searches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"success": True, "searches": all_searches}

# ── Serve static frontend files ──

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
