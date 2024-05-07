from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from logger_config import setup_logger
from google.cloud import exceptions
from slack_bolt import App
import os

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")

if not SLACK_BOT_TOKEN:
    logger = setup_logger()
    logger.error("SLACK_BOT_TOKEN environment variable not set.")
    slack_app = App(token="default_token")  # Initialize with default token
else:
    slack_app = App(token=SLACK_BOT_TOKEN)

if not firebase_admin._apps:
    cred = credentials.Certificate("ServiceAccountKey.json")
    initialize_app(cred)

db = firestore.client()
logger = setup_logger()

def retrieve_tokens(user_id, service):
    doc_ref = db.collection(u'users').document(user_id)
    try:
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get(service, None)
        else:
            return None
    except exceptions.NotFound:
        logger.error("Document not found")
        return None
