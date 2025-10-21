import azure.functions as func
import stripe
import json
import os
from azure.communication.email import EmailClient
import logging

# Configure Stripe
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
stripe_webhook_secret = os.environ["STRIPE_WEBHOOK_SECRET"]

# SAS URL for download - UPDATE THIS WITH ACTUAL LINK
DOWNLOAD_LINK = "https://vulturelimiter.blob.core.windows.net/vulturelimiter?sp=r&st=2025-09-11T14:23:42Z&se=2025-09-11T22:38:42Z&spr=https&sv=2024-11-04&sr=c&sig=6%2BXFWUH3cE10sTMIFXvMldpXmz2vuarTeodwEy%2F2MHY%3D"

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    # Get the request body and Stripe signature
    payload = req.get_body()
    sig_header = req.headers.get('stripe-signature')

    if not sig_header:
        return func.HttpResponse("No Stripe signature", status_code=400)

    try:
        # Verify the webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        return func.HttpResponse("Invalid payload", status_code=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return func.HttpResponse("Invalid signature", status_code=400)

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        try:
            # Send email with download link
            send_download_email(session)
            logging.info(f"Download email sent for session: {session['id']}")
            return func.HttpResponse("Email sent successfully", status_code=200)
            
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
            return func.HttpResponse(f"Error sending email: {str(e)}", status_code=500)

    return func.HttpResponse("Event not handled", status_code=200)

def send_download_email(session):
    """Send download link email using Azure Communication Services"""
    
    # Get customer email from Stripe session
    customer_email = session.get('customer_details', {}).get('email')
    if not customer_email:
        logging.error("No customer email found in session")
        return

    # Azure Communication Services setup
    connection_string = os.environ["AZURE_COMMUNICATION_CONNECTION_STRING"]
    sender_address = os.environ["EMAIL_SENDER_ADDRESS"]
    
    email_client = EmailClient.from_connection_string(connection_string)
    
    # Email content with branding
    email_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .logo {{ max-width: 200px; height: auto; }}
            .content {{ margin: 20px 0; }}
            .download-link {{ 
                background-color: #f0f0f0; 
                padding: 15px; 
                border-radius: 5px; 
                margin: 20px 0;
                word-break: break-all;
            }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="header">
            <!-- Add your logo here when available -->
            <h1>Terror Audio</h1>
        </div>
        
        <div class="content">
            <p>Thank you for choosing Terror Audio for your software purchase. This e-mail contains your activation/license link for downloading and installing your new software.</p>
            
            <p><strong>IMPORTANT:</strong> Please retain a copy of this email in a safe place for future reference.</p>
            
            <div class="download-link">
                <strong>Your Activation Link:</strong><br>
                <a href="{DOWNLOAD_LINK}">{DOWNLOAD_LINK}</a>
            </div>
            
            <p>If you have any questions or need assistance, please contact our support team.</p>
        </div>
        
        <div class="footer">
            <p>Best regards,<br>The Terror Audio Team</p>
        </div>
    </body>
    </html>
    """
    
    # Plain text version for fallback
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
    logging.info(f"Email sent successfully to {customer_email}")