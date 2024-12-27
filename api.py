from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import stripe
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

# Set Stripe API key from Railway's environment variable
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

# Verify the key is loaded for debugging (remove this after testing)
if not stripe.api_key:
    print("Stripe API key not loaded! Check Railway environment variables.")
else:
    print(f"Stripe API Key Loaded: {stripe.api_key[:8]}...")  # Logs partial key for security

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust with the domain where your frontend is hosted
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Model for request body
class CheckoutRequest(BaseModel):
    price_id: str  # Stripe price ID or product ID

@app.post("/create-checkout-session")
async def create_checkout_session(request: CheckoutRequest):
    try:
        print(f"Received request: {request.dict()}")  # Log the request data for debugging

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': request.price_id,
                'quantity': 1,
            }],
            mode='payment',
            success_url="https://terroraudiopayment-production.up.railway.app/success",
            cancel_url="https://terroraudiopayment-production.up.railway.app/cancel",
        )
        print(f"Checkout session created: {session}")  # Log session data for debugging
        return {"checkout_url": session.url}
    except Exception as e:
        print(f"Error: {str(e)}")  # Log the error message
        raise HTTPException(status_code=400, detail=str(e))
    
@app.get("/")
def welcome_spot():
    return {"message": "Welcome to TerrorAudio"}