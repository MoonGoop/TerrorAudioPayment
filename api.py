from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import stripe
from fastapi.middleware.cors import CORSMiddleware
import os 
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from.env file

app = FastAPI()

# Your Stripe secret key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")  # Replace with your actual secret key

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
            success_url="https://your-domain.com/success",
            cancel_url="https://your-domain.com/cancel",
        )
        print(f"Checkout session created: {session}")  # Log session data for debugging
        return {"checkout_url": session.url}
    except Exception as e:
        print(f"Error: {str(e)}")  # Log the error message
        raise HTTPException(status_code=400, detail=str(e))
    
@app.get("/")
def welcome_spot():
    return {"message": "Welcome to TerrorAudio"}
    