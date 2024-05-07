from loguru import logger
from slack_bolt import App
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
import json
import os
# Initialize logger
logger.add("debug.log", format="{time} {level} {message}", level="DEBUG")

# Initialize Slack app
slack_app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Fetch the environment variable
firebase_service_account = os.getenv('FIREBASE_SERVICE_ACCOUNT')

if firebase_service_account is None:
    raise ValueError("FIREBASE_SERVICE_ACCOUNT environment variable is not set.")

# Convert the string back to a dictionary
service_account_info = json.loads(firebase_service_account)

# Initialize Firestore DB
if not firebase_admin._apps:
    # Pass the dictionary directly to credentials.Certificate
    cred = credentials.Certificate(service_account_info)
    initialize_app(cred)
db = firestore.client()