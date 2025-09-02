import os
import logging
from typing import Optional, Set

import stripe
from fastapi import FastAPI, HTTPException, Request, Query, Body
from fastapi.responses import JSONResponse, Response, RedirectResponse
from pydantic import BaseModel, Field, validator

# ─────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────
STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY")
SUCCESS_URL: str = os.getenv("SUCCESS_URL", "https://terroraudio.com/success-page")
CANCEL_URL: str = os.getenv("CANCEL_URL", "https://terroraudio.com")

# CORS allowlist (comma-separated)
ALLOW_ORIGINS_ENV = os.getenv(
    "ALLOW_ORIGINS",
    "https://terroraudio.com,https://www.terroraudio.com"
)
# TEMP: set ALLOW_ALL_CORS=1 to open during testing
ALLOW_ALL_CORS = os.getenv("ALLOW_ALL_CORS", "0") == "1"

def _normalize(origins: str) -> Set[str]:
    return {o.strip().rstrip("/") for o in origins.split(",") if o.strip()}

ALLOWED_ORIGINS: Set[str] = _normalize(ALLOW_ORIGINS_ENV)

# ─────────────────────────────────────────────────────────
# App & logging
# ─────────────────────────────────────────────────────────
app = FastAPI(title="TerrorAudio Payments", version="1.0.0")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("terroraudio")

if not STRIPE_SECRET_KEY:
    log.warning("STRIPE_SECRET_KEY is not set! Stripe calls will fail.")
else:
    stripe.api_key = STRIPE_SECRET_KEY
    log.info(f"Stripe key loaded (prefix): {STRIPE_SECRET_KEY[:8]}••••")

# ─────────────────────────────────────────────────────────
# Dynamic CORS (handles preflight and adds headers to ALL responses)
# ─────────────────────────────────────────────────────────
def origin_allowed(origin: Optional[str]) -> bool:
    if not origin:
        return False
    if ALLOW_ALL_CORS:
        return True
    return origin.rstrip("/") in ALLOWED_ORIGINS

def cors_headers(origin: Optional[str], req_headers: Optional[str]) -> dict:
    headers = {
        "Vary": "Origin",
        "Access-Control-Max-Age": "86400",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": req_headers or "*",
    }
    if origin_allowed(origin):
        headers["Access-Control-Allow-Origin"] = origin  # echo exact origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers

@app.middleware("http")
async def dynamic_cors(request: Request, call_next):
    origin = request.headers.get("origin")
    req_ac_req_headers = request.headers.get("access-control-request-headers")

    # Preflight
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers(origin, req_ac_req_headers))

    # Main path (ensure errors also carry CORS)
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled server error")
        response = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    # Attach CORS headers
    for k, v in cors_headers(origin, req_ac_req_headers).items():
        if k == "Vary" and "Vary" in response.headers:
            if v not in response.headers["Vary"]:
                response.headers["Vary"] += f", {v}"
        else:
            response.headers[k] = v
    return response

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class CheckoutRequest(BaseModel):
    price_id: str = Field(..., description="Stripe Price ID (e.g., price_123...)")
    @validator("price_id")
    def _valid(cls, v):
        if not isinstance(v, str) or not v:
            raise ValueError("price_id is required")
        return v

# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────
def _create_session(price_id: str) -> str:
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Server misconfiguration: missing Stripe key.")
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=CANCEL_URL,
        )
        url = session.get("url")
        if not url:
            raise HTTPException(status_code=502, detail="Stripe did not return a checkout URL.")
        return url
    except stripe.error.StripeError as se:
        msg = getattr(se, "user_message", None) or str(se)
        raise HTTPException(status_code=400, detail=msg)
    except Exception:
        log.exception("Unexpected error from Stripe")
        raise HTTPException(status_code=500, detail="Failed to create checkout session.")

# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────
@app.get("/")
def welcome_spot():
    return {"message": "Welcome to TerrorAudio"}

# POST (no trailing slash)
@app.post("/create-checkout-session")
def create_checkout_session(payload: CheckoutRequest = Body(...)):
    log.info(f"Create checkout request: {payload.dict()}")
    checkout_url = _create_session(payload.price_id)
    log.info(f"Checkout session URL: {checkout_url}")
    return {
        "success": True,
        "url": checkout_url,           # frontend commonly expects this
        "checkout_url": checkout_url   # backward compatibility
    }

# POST (trailing slash) to avoid 308 traps
@app.post("/create-checkout-session/")
def create_checkout_session_slash(payload: CheckoutRequest = Body(...)):
    return create_checkout_session(payload)

# Pure redirect endpoint (use as a normal link)
@app.get("/redirect-checkout-session")
def redirect_checkout_session(price_id: str = Query(..., description="Stripe Price ID")):
    url = _create_session(price_id)
    return RedirectResponse(url=url, status_code=303)

# Health
@app.get("/healthz")
def healthz():
    return {"ok": True}

# Local dev
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
