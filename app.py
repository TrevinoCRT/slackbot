import os
import asyncio
import threading
from flask import Flask, request, redirect, url_for
import uuid
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from loguru import logger
from assistants import process_thread_with_assistant

# Initialize logger
logger.add("debug.log", format="{time} {level} {message}", level="DEBUG")

# Load environment variables
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Initialize Slack app
app = Flask(__name__)
slack_app = App(token=SLACK_BOT_TOKEN)
slack_handler = SlackRequestHandler(slack_app)

# Initialize Firestore DB
if not firebase_admin._apps:
    cred = credentials.Certificate("ServiceAccountKey.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

# OAuth Configuration
JIRA_CLIENT_ID = os.environ.get("JIRA_CLIENT_ID")
JIRA_CLIENT_SECRET = os.environ.get("JIRA_CLIENT_SECRET")
JIRA_SCOPES = os.environ.get("JIRA_SCOPES")
REDIRECT_URI = os.environ.get("REDIRECT_URI")
TOKEN_URL = os.environ.get("TOKEN_URL")
MIRO_CLIENT_ID = os.environ.get("MIRO_CLIENT_ID")
MIRO_CLIENT_SECRET = os.environ.get("MIRO_CLIENT_SECRET")
MIRO_REDIRECT_URI = os.environ.get("MIRO_REDIRECT_URI")

@app.route('/slack/events', methods=['POST'])
def slack_events():
    data = request.json
    logger.debug(f"Received Slack event data: {data}")

    # Handle URL verification from Slack
    if data.get('type') == 'url_verification':
        challenge = data['challenge']
        logger.info(f"Handling URL verification. Challenge: {challenge}")
        return challenge

    # Handle event callbacks
    if data.get('type') == 'event_callback':
        event = data['event']
        logger.info(f"Handling event callback. Event data: {event}")

        # Check if the message is from a bot to prevent responding to its own messages
        if 'bot_id' in event:
            logger.info("Ignoring bot message.")
            return '', 200

        if event.get('type') == 'app_home_opened':
            logger.info(f"Event type is 'app_home_opened'. User ID: {event.get('user')}")
            update_home_tab(slack_app.client, event, logger)
            logger.info("Home tab updated successfully.")
        
        elif event.get('type') == 'message':
            # Process the message asynchronously to avoid blocking
            threading.Thread(target=lambda: process_message(event)).start()
        
        logger.info("Event callback processed successfully.")
        return '', 200

    logger.warning("Received bad request. Data type is not handled: " + str(data.get('type')))
    return '', 400  # Bad request response

def process_message(event):
    user_id = event['user']
    text = event['text']
    channel = event['channel']
    # Assuming process_thread_with_assistant is adapted to handle these parameters
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(process_thread_with_assistant(text, os.getenv('ASSISTANT_ID'), from_user=user_id))
    if response:
        for text in response.get("text", []):
            slack_app.client.chat_postMessage(
                channel=channel,
                text=text,
                mrkdwn=True
            )
    loop.close()


@slack_app.message("")
def message_handler(message, say, ack):
    ack()
    user_id = message.get('user')
    logger.debug(f"Received message from user: {user_id}")
    authorized_user_id = "U0581M58KAM"

    if user_id and user_id == authorized_user_id:
        user_query = message['text']
        assistant_id = os.environ.get('ASSISTANT_ID')
        from_user = message['user']
        thread_ts = message['ts']  # Get the timestamp of the user's message to use as thread_ts
        logger.debug(f"Authorized user {from_user} sent a query: {user_query}")

        def process_and_respond():
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            logger.debug("Event loop set for async processing.")

            async def async_process_and_respond():
                response = await process_thread_with_assistant(user_query, assistant_id, from_user=from_user)
                if response:
                    for text in response.get("text", []):
                        slack_app.client.chat_postMessage(
                            channel=message['channel'],
                            text=text,
                            mrkdwn=True,
                            thread_ts=thread_ts  # Post the response in the same thread
                        )
                else:
                    say("Sorry, I couldn't process your request.", thread_ts=thread_ts)
                logger.info("Response processed and sent to user.")

            loop.run_until_complete(async_process_and_respond())

        threading.Thread(target=process_and_respond).start()
        logger.debug("Processing user query in a separate thread.")

    else:
        logger.warning("Unauthorized or missing user ID in message event.")


@slack_app.event("app_home_opened")
def update_home_tab(client, event, logger):
    user_id = event['user']
    client.views_publish(
        user_id=user_id,
        view={
            "type": "home",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Welcome to the Slack Integration! Please authenticate with the services you need:"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Authenticate with Miro"
                            },
                            "value": "miro_auth",
                            "action_id": "miro_auth",
                            "url": url_for('auth_miro', user_id=user_id, _external=True)
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Authenticate with Jira"
                            },
                            "value": "jira_auth",
                            "action_id": "jira_auth",
                            "url": url_for('auth_jira', user_id=user_id, _external=True)
                        }
                    ]
                }
            ]
        }
    )
def store_tokens(user_id, access_token, refresh_token, service):
    """
    Stores access and refresh tokens in Firestore under the user's document.
    Each service (Miro, Jira) will have its own field in the document.
    """
    doc_ref = db.collection(u'users').document(user_id)
    try:
        tokens = doc_ref.get().to_dict() if doc_ref.get().exists else {}
        tokens[service] = {
            u'access_token': access_token,
            u'refresh_token': refresh_token
        }
        doc_ref.set(tokens)
        logger.info(f"Tokens for {service} stored successfully for user {user_id}.")
    except Exception as e:
        logger.error(f"Failed to store tokens for {service} for user {user_id}: {str(e)}")

def retrieve_tokens(user_id, service):
    """
    Retrieves the access and refresh tokens for a specific service for the given user.
    """
    doc_ref = db.collection(u'users').document(user_id)
    try:
        user_data = doc_ref.get()
        if user_data.exists:
            service_tokens = user_data.to_dict().get(service, {})
            return service_tokens.get('access_token'), service_tokens.get('refresh_token')
        else:
            logger.warning(f"No data found for user {user_id}.")
            return None, None
    except Exception as e:
        logger.error(f"Failed to retrieve tokens for user {user_id}: {str(e)}")
        return None, None

def store_state_in_storage(state, key, user_id):
    """
    Stores a state value in Firestore to validate during the OAuth callback.
    """
    doc_ref = db.collection(u'states').document(key)
    try:
        doc_ref.set({u'state': state, u'user_id': user_id})
        logger.info(f"OAuth state stored successfully for {key}.")
    except Exception as e:
        logger.error(f"Failed to store OAuth state for {key}: {str(e)}")

def retrieve_state_from_storage(key):
    """
    Retrieves a state value from Firestore to validate during the OAuth callback.
    """
    doc_ref = db.collection(u'states').document(key)
    try:
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            logger.warning(f"State document {key} not found.")
            return None
    except Exception as e:
        logger.error(f"Failed to retrieve OAuth state for {key}: {str(e)}")
        return None


# Miro auth and callback
@slack_app.action("miro_auth")
def handle_miro_auth(ack, body, client):
    ack()
    user_id = body['user']['id']
    logger.debug(f"Acknowledgement sent for user {user_id}.")
    client.chat_postMessage(channel=user_id, text="Redirecting you to Miro authentication...")
    logger.debug(f"Message sent to user {user_id} about redirection to Miro authentication.")
    return redirect(url_for('auth_miro', user_id=user_id))


@app.route('/auth/miro', methods=['GET'])
def auth_miro():
    user_id = request.args.get('user_id')
    logger.debug(f"Received user_id {user_id} for Miro authentication.")
    state = uuid.uuid4()  # Generate a unique state value for CSRF protection
    logger.debug(f"Generated unique state {state} for CSRF protection.")
    # Store the state in Firestore for later validation
    store_state_in_storage(str(state), 'miro_auth_state', user_id)
    logger.debug(f"Stored state {state} in Firestore under key 'miro_auth_state' for user {user_id}.")
    auth_url = f"https://miro.com/oauth/authorize?response_type=code&client_id={MIRO_CLIENT_ID}&redirect_uri={MIRO_REDIRECT_URI}&state={state}"
    logger.debug(f"Generated Miro authorization URL: {auth_url}")
    return redirect(auth_url)


def exchange_code_for_token(params):
    url = f'https://api.miro.com/v1/oauth/token'
    logger.debug(f"URL for token exchange set to {url}.")
    
    payload = {
        'grant_type': 'authorization_code',
        'client_id': params['client_id'],
        'client_secret': params['client_secret'],
        'code': params['code'],
        'redirect_uri': params['redirect_uri']
    }
    logger.debug(f"Payload for POST request prepared: {payload}.")
    
    logger.debug(f"Initiating POST request to {url} with payload.")
    response = requests.post(url, data=payload)
    logger.debug(f"POST request sent. Awaiting response...")
    
    if response.status_code == 200:
        logger.debug(f"Response received with status code 200. Processing response data.")
        response_data = response.json()
        logger.debug(f"Response data converted to JSON: {response_data}.")
        
        access_token = response_data.get('access_token')
        refresh_token = response_data.get('refresh_token')
        if access_token and refresh_token:
            logger.debug(f"Access token and refresh token successfully retrieved: Access Token: {access_token}, Refresh Token: {refresh_token}.")
        else:
            logger.warning(f"Missing tokens in the response data. Access Token: {access_token}, Refresh Token: {refresh_token}.")
        
        return access_token, refresh_token
    else:
        logger.error(f"Failed to obtain tokens. Status: {response.status_code}, Response: {response.text}")
        return None, None

@app.route('/miro/callback', methods=['GET'])
def miro_callback():
    error = request.args.get('error')
    if error:
        return f"Error received from Jira: {error}", 400

    state = request.args.get('state')
    code = request.args.get('code')
    if not state or not code:
        return "Missing state or code parameter.", 400

    # Retrieve the expected state and user_id from Firestore
    state_data = retrieve_state_from_storage('miro_auth_state')
    expected_state = state_data['state']
    user_id = state_data['user_id']
    if state != expected_state:
        return "State validation failed.", 400

    if code:
        params = {
            'code': code,
            'client_id': MIRO_CLIENT_ID,
            'client_secret': MIRO_CLIENT_SECRET,
            'redirect_uri': MIRO_REDIRECT_URI
        }
        logger.debug(f"Parameters for token exchange: {params}")
        access_token, refresh_token = exchange_code_for_token(params)
        if access_token:
            # Store the tokens securely using Firestore
            store_tokens(user_id, access_token, refresh_token, 'miro')
            logger.info("Authorization successful. Tokens stored.")
            return "Authorization successful. You may close this window."
        else:
            logger.error("Authorization failed during token exchange.")
            return "Authorization failed."
    else:
        logger.error("Authorization failed due to missing code.")
        return "Authorization failed."
#Jira auth and callback
@slack_app.action("jira_auth")
def handle_jira_auth(ack, body, client):
    ack()
    user_id = body['user']['id']
    client.chat_postMessage(channel=user_id, text="Redirecting you to Jira authentication...")
    return redirect(url_for('auth_jira', user_id=user_id))

@app.route('/auth/jira', methods=['GET'])
def auth_jira():
    user_id = request.args.get('user_id')
    state = uuid.uuid4()  # Generate a unique state value for CSRF protection
    # Store the state in Firestore for later validation
    store_state_in_storage(str(state), 'jira_auth_state', user_id)
    auth_url = f"https://auth.atlassian.com/authorize?audience=api.atlassian.com&client_id={JIRA_CLIENT_ID}&scope={JIRA_SCOPES}&redirect_uri={REDIRECT_URI}&state={state}&response_type=code&prompt=consent"
    return redirect(auth_url)

# Function to exchange authorization code for an access token with Jira API
def exchange_code_for_jira_token(jira_params):
    payload = {
        'grant_type': 'authorization_code',
        'client_id': jira_params['client_id'],
        'client_secret': jira_params['client_secret'],
        'code': jira_params['code'],
        'redirect_uri': jira_params['redirect_uri']
    }
    try:
        response = requests.post(TOKEN_URL, data=payload)
        if response.status_code == 200:
            access_token = response.json().get('access_token')
            refresh_token = response.json().get('refresh_token')
            logger.success(f"Access token obtained: {access_token}")
            return access_token, refresh_token
        else:
            logger.error(f"Failed to obtain access token. Status: {response.status_code}, Response: {response.text}")
            return None, None
    except requests.exceptions.RequestException as e:
        logger.exception(f"Network error occurred during token exchange: {e}")
        return None, None


@app.route('/jira-callback', methods=['GET'])
def jira_callback():
    error = request.args.get('error')
    if error:
        return f"Error received from Jira: {error}", 400

    state = request.args.get('state')
    code = request.args.get('code')
    if not state or not code:
        return "Missing state or code parameter.", 400

    # Retrieve the expected state and user_id from Firestore
    state_data = retrieve_state_from_storage('jira_auth_state')
    expected_state = state_data['state']
    user_id = state_data['user_id']

    if state != expected_state:
        return "State validation failed.", 400

    # Create a dictionary with the required parameters
    jira_params = {
        'code': code,
        'client_id': JIRA_CLIENT_ID,
        'client_secret': JIRA_CLIENT_SECRET,
        'redirect_uri': REDIRECT_URI
    }

    # Exchange the code for a token
    access_token, refresh_token = exchange_code_for_jira_token(jira_params)
    if access_token:
        # Store the tokens securely using Firestore
        store_tokens(user_id, access_token, refresh_token, 'jira')
        return "Jira OAuth flow completed successfully.", 200
    else:
        return "Failed to obtain Jira access token.", 400

# Start the Flask app
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))



