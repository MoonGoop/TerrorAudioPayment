import os
import logging
from typing import Optional, Iterable, Set

import stripe
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

# ─────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────
STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY")

SUCCESS_URL: str = os.getenv("SUCCESS_URL", "https://terroraudio.com/success-page")
CANCEL_URL: str = os.getenv("CANCEL_URL", "https://terroraudio.com")

# Comma-separated allowlist. Example:
# ALLOW_ORIGINS="https://terroraudio.com,https://www.terroraudio.com,https://staging.yourdomain.com"
ALLOW_ORIGINS_ENV = os.getenv(
    "ALLOW_ORIGINS",
    "https://terroraudio.com,https://www.terroraudio.com"
)

# Set ALLOW_ALL_CORS="1" temporarily if you must unblock everything for testing.
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
# Custom CORS middleware (dynamic echo)
#  - Works with or without credentials from the browser
#  - Adds headers on ALL responses (incl. errors)
#  - Handles preflight for ANY path
# ─────────────────────────────────────────────────────────
def origin_allowed(origin: Optional[str]) -> bool:
    if not origin:
        return False
    if ALLOW_ALL_CORS:
        return True
    # normalize (remove trailing slash)
    o = origin.rstrip("/")
    return o in ALLOWED_ORIGINS

def cors_headers(origin: Optional[str], req_headers: Optional[str]) -> dict:
    headers = {
        "Vary": "Origin",
        "Access-Control-Max-Age": "86400",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Access-Control-Allow-Headers": req_headers or "*",
    }
    if origin_allowed(origin):
        headers["Access-Control-Allow-Origin"] = origin  # echo exact origin
        # We support credentials if browser sends them
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers

@app.middleware("http")
async def dynamic_cors(request: Request, call_next):
    origin = request.headers.get("origin")
    req_ac_req_headers = request.headers.get("access-control-request-headers")

    # Preflight short-circuit: respond 204 with CORS headers, no body
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers(origin, req_ac_req_headers))

    # Normal request path
    try:
        response = await call_next(request)
    except Exception as e:
        # Ensure even error responses carry CORS headers
        log.exception("Unhandled server error")
        response = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    # Attach CORS headers to every response
    for k, v in cors_headers(origin, req_ac_req_headers).items():
        # Merge with existing headers (keep existing Vary entries)
        if k == "Vary" and "Vary" in response.headers:
            if v not in response.headers["Vary"]:
                response.headers["Vary"] += f", {v}"
        else:
            response.headers[k] = v
    return response

# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────
@app.get("/")
def welcome_spot():
    return {"message": "Welcome to TerrorAudio"}

# Provide both variants to avoid 308/301 redirects on preflight
CREATE_PATHS = ["/create-checkout-session", "/create-checkout-session/"]

def _create_session(price_id: str) -> str:
    """Create a Stripe Checkout Session and return its URL."""
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
        # Return safe, helpful error to client
        msg = getattr(se, "user_message", None) or str(se)
        raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        log.exception("Unexpected error from Stripe")
        raise HTTPException(status_code=500, detail="Failed to create checkout session.")

# Pydantic inline to keep file single-module
from pydantic import BaseModel, Field, validator

class CheckoutRequest(BaseModel):
    price_id: str = Field(..., description="Stripe Price ID (e.g., price_123...)")

    @validator("price_id")
    def _valid(cls, v):
        if not isinstance(v, str) or not v:
            raise ValueError("price_id is required")
        # Warn (but don’t block) if format looks off
        if not (v.startswith("price_") or v.startswith("prod_")):
            log.warning("price_id does not start with 'price_' or 'prod_'. Check your Stripe IDs.")
        return v

from fastapi import Body

for path in CREATE_PATHS:
    @app.post(path)
    def create_checkout_session(payload: CheckoutRequest = Body(...)):
        log.info(f"Create checkout request: {payload.dict()}")
        checkout_url = _create_session(payload.price_id)
        log.info(f"Checkout session URL: {checkout_url}")
        return {"checkout_url": checkout_url}

# Optional health for probes
@app.get("/healthz")
def healthz():
    return {"ok": True}

# Local dev
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
