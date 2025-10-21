import azure.functions as func
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import stripe
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import json

load_dotenv()

# Configure Stripe
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
stripe_webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
stripe_publishable_key = os.environ["STRIPE_PUBLISHABLE_KEY"]

# Create FastAPI app
fast_app = FastAPI()

# Add CORS middleware
fast_app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://terroraudio.com", "https://www.terroraudio.com"],
    allow_credentials=True,
    allow_methods=["OPTIONS", "GET", "POST"],
    allow_headers=["*"],
)

class CheckoutRequest(BaseModel):
    price_id: str

@fast_app.post("/create-checkout-session")
async def create_checkout_session(request: CheckoutRequest):
    try:
        print(f"Received request: {request.dict()}")

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': request.price_id,
                'quantity': 1,
            }],
            mode='payment',
            success_url="https://terroraudio.com/success-page",
            cancel_url="https://terroraudio.com",
        )
        print(f"Checkout session created: {session.id}")
        return {"checkout_url": session.url}
    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@fast_app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    if not sig_header:
        raise HTTPException(status_code=400, detail="No Stripe signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        await send_download_email(session)
        return {"status": "Email sent"}
    
    return {"status": "Event received"}

@fast_app.get("/")
def welcome():
    return {"message": "Welcome to TerrorAudio"}

async def send_download_email(session):
    """Send download link email using Azure Communication Services"""
    try:
        from azure.communication.email import EmailClient
        
        # Get customer email from Stripe session
        customer_email = session.get('customer_details', {}).get('email')
        if not customer_email:
            print("No customer email found in session")
            return

        # Azure Communication Services setup
        connection_string = os.environ["AZURE_COMMUNICATION_CONNECTION_STRING"]
        sender_address = os.environ["EMAIL_SENDER_ADDRESS"]
        
        # SAS URL for download - UPDATE THIS WITH ACTUAL LINK
        DOWNLOAD_LINK = "https://vulturelimiter.blob.core.windows.net/vulturelimiter?sp=r&st=2025-09-11T14:23:42Z&se=2025-09-11T22:38:42Z&spr=https&sv=2024-11-04&sr=c&sig=6%2BXFWUH3cE10sTMIFXvMldpXmz2vuarTeodwEy%2F2MHY%3D"
        
        email_client = EmailClient.from_connection_string(connection_string)
        
        # Email content
        email_content = f"""
        <html>
        <body>
            <div style="font-family: Arial, sans-serif; margin: 20px;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #FF6B00;">Terror Audio</h1>
                </div>
                
                <div style="margin: 20px 0;">
                    <p>Thank you for choosing Terror Audio for your software purchase. This e-mail contains your activation/license link for downloading and installing your new software.</p>
                    
                    <p><strong>IMPORTANT:</strong> Please retain a copy of this email in a safe place for future reference.</p>
                    
                    <div style="background-color: #f0f0f0; padding: 15px; border-radius: 5px; margin: 20px 0; word-break: break-all;">
                        <strong>Your Activation Link:</strong><br>
                        <a href="{DOWNLOAD_LINK}">{DOWNLOAD_LINK}</a>
                    </div>
                    
                    <p>If you have any questions or need assistance, please contact our support team.</p>
                </div>
                
                <div style="margin-top: 30px; font-size: 12px; color: #666;">
                    <p>Best regards,<br>The Terror Audio Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_text_content = f"""
        Thank you for choosing Terror Audio for your software purchase. This e-mail contains your activation/license link for downloading and installing your new software.

        IMPORTANT: Please retain a copy of this email in a safe place for future reference.

        Your Activation Link: {DOWNLOAD_LINK}

        If you have any questions or need assistance, please contact our support team.

        Best regards,
        The Terror Audio Team
        """
        
        message = {
            "senderAddress": sender_address,
            "recipients": {
                "to": [{"address": customer_email}],
            },
            "content": {
                "subject": "Your Terror Audio Software Download",
                "plainText": plain_text_content,
                "html": email_content,
            }
        }
        
        # Send the email
        poller = email_client.begin_send(message)
        result = poller.result()
        print(f"Email sent successfully to {customer_email}")
        
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        raise

app = func.AsgiFunctionApp(app=fast_app, http_auth_level=func.AuthLevel.ANONYMOUS)
