from loguru import logger
from slack_bolt import App
import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize logger
logger.add("debug.log", format="{time} {level} {message}", level="DEBUG")

# Initialize Slack app
slack_app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Initialize Firestore DB
if not firebase_admin._apps:
    cred = credentials.Certificate("ServiceAccountKey.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()