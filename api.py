from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import stripe
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

# Hardcoding the Stripe API Key for testing
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")  # Replace this with your actual test API key

# Debugging: Verify that the key is loaded
print(f"Stripe API Key Loaded: {stripe.api_key[:8]}...")  # Logs partial key for security

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://terroraudio.com", "https://www.terroraudio.com"],  # ✅ Allow both with and without 'www'
    allow_credentials=True,
    allow_methods=["OPTIONS", "GET", "POST"],
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
            success_url="https://terroraudio.com/success-page",
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