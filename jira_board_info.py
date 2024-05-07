from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from logger_config import setup_logger
import requests
import json
import os


logger = setup_logger()

CLOUD_ID = os.getenv("CLOUD_ID")

class JiraOAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

        # Parse the query parameters to get the authorization code
        query = urlparse(self.path).query
        query_components = parse_qs(query)
        code = query_components.get('code', None)

        if code:
            self.wfile.write(b'Authorization successful. You may close this window.')
            logger.success(f"Authorization code received: {code[0]}")
        else:
            self.wfile.write(b'Authorization failed.')
            logger.warning("Authorization failed, no code found in request.")
            
async def create_new_jira_issue(token, summary, description, project_id, issue_type_id):
    if not token:
        error_response = {
            "errorMessages": ["No access token provided. Please authenticate."],
            "errors": {},
            "status": 401
        }
        logger.error("No access token provided. Please authenticate.", extra={"status": 401})
        return error_response

    cloud_id = CLOUD_ID
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = json.dumps({
        "fields": {
            "project": {
                "key": project_id  # Ensure this is a valid project key
            },
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{
                        "text": description,
                        "type": "text"
                    }]
                }]
            },
            "issuetype": {
                "id": issue_type_id  # Ensure this is a valid issue type ID
            }
        }
    })

    try:
        response = requests.post(url, headers=headers, data=payload)
        if response.status_code == 201:
            logger.success("Issue created successfully.", extra={"response": response.json(), "status": response.status_code})
            return response.json()
        else:
            error_response = {
                "errorMessages": [f"Failed to create issue: {response.text}"],
                "errors": {},
                "status": response.status_code
            }
            logger.error("Failed to create issue.", extra={"response": response.text, "status": response.status_code})
            return error_response
    except Exception as e:
        error_response = {
            "errorMessages": [f"Error making API request: {e}"],
            "errors": {},
            "status": 500
        }
        logger.exception("Error making API request.", exception=e)
        return error_response
def update_issue_summary_and_description(token, issue_id_or_key, summary, description):
    """
    Updates the summary and description of a given issue.

    Args:
        token (str): The access token for Jira API.
        issue_id_or_key (str): The ID or key of the issue to update.
        summary (str): The new summary for the issue.
        description (str): The new description for the issue.

    Returns:
        bool: True if the update was successful, False otherwise.
    """
    if not token:
        logger.error("No access token provided. User needs to authenticate.", extra={"token": token})
        return False

    cloud_id = CLOUD_ID
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/2/issue/{issue_id_or_key}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "fields": {
            "summary": summary,
            "description": description
        }
    }

    try:
        response = requests.put(url, headers=headers, json=payload)
        if response.status_code == 204:
            logger.success("Issue updated successfully.", extra={"issue_id": issue_id_or_key, "status": response.status_code})
            return True
        else:
            logger.error("Failed to update issue.", extra={"issue_id": issue_id_or_key, "response": response.text, "status": response.status_code})
            return False
    except requests.exceptions.RequestException as e:
        logger.exception("Network error occurred while updating issue.", exception=e)
        return False


def get_issue_details(token, cloud_id, issue_id_or_key, fields=None, fields_by_keys=False, expand=None, properties=None, update_history=False):
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/2/issue/{issue_id_or_key}"
    logger.trace("Fetching issue details.", extra={"issue_id": issue_id_or_key, "cloud_id": cloud_id})

    params = {
        'fields': ','.join(fields) if fields else None,
        'fieldsByKeys': fields_by_keys,
        'expand': expand,
        'properties': ','.join(properties) if properties else None,
        'updateHistory': update_history
    }
    logger.debug("Query params prepared.", extra={"params": params})

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    logger.debug("Authorization headers set.", extra={"token": token[:10]})

    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            response_json = response.json()
            logger.success("Issue details fetched successfully.", extra={"response_size": len(str(response_json)), "status": response.status_code})
            return response_json
        else:
            logger.error("Failed to fetch issue details.", extra={"response": str(response.json())[:100], "status": response.status_code})
            return None
    except requests.exceptions.RequestException as e:
        logger.exception("Network error occurred while fetching issue details.", exception=e)
        return None
    
async def retrieve_jira_issue(issue_key, token):
    logger.trace("Entering retrieve_jira_issue function with issue_key: {}", issue_key)
    if not issue_key:
        logger.warning("No Jira Issue Key provided. Operation aborted.")
        return

    if not token:
        logger.error("No access token provided. User needs to authenticate.")
        return

    cloud_id = CLOUD_ID
    try:
        logger.info("Attempting to retrieve issue with key: {} from cloud ID: {}", issue_key[:10], cloud_id)
        issue_details = get_issue_details(token, cloud_id, issue_key)
        logger.success("Issue retrieved successfully. Issue details (limited): {}", str(issue_details)[:100])
        return {"issue_details": issue_details}
    except Exception as e:
        logger.error("Error retrieving issue from Jira: {}", e)
        return None

def get_epic_details(epic_id_or_key, token):
    logger.trace("Entering get_epic_details function with epic_id_or_key: {}", epic_id_or_key)
    if not token:
        logger.error("No access token provided. User needs to authenticate.")
        return

    cloud_id = CLOUD_ID
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/2/issue/{epic_id_or_key}"

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            epic_details = response.json()
            logger.success("Epic details retrieved successfully for {}", epic_id_or_key)
            return {
                "Key": epic_details.get('key'),
                "Summary": epic_details.get('fields', {}).get('summary', 'No summary provided'),
                "Description": epic_details.get('fields', {}).get('description', 'No description provided')
            }
        else:
            logger.error("Failed to retrieve epic details for {}. Status code: {}, Response: {}", epic_id_or_key, response.status_code, response.text)
            return None
    except requests.exceptions.RequestException as e:
        logger.exception("Network error occurred while retrieving epic details: {}", e)
        return None
def get_issues_for_epic(epic_id_or_key):
    logger.trace("Entering get_issues_for_epic function with epic_id_or_key: {}", epic_id_or_key)
    epic_details = get_epic_details(epic_id_or_key)
    child_issues = get_child_issues_for_epic(epic_id_or_key)
    combined_details = {
        "EpicDetails": epic_details,
        "ChildIssues": child_issues
    }
    logger.debug("Combined epic and child issues details: {}", combined_details)
    return combined_details

def get_child_issues_for_epic(epic_id_or_key, token):
    logger.trace("Entering get_child_issues_for_epic function with epic_id_or_key: {}", epic_id_or_key)
    if not token:
        logger.error("No access token provided. User needs to authenticate.")
        return None

    cloud_id = CLOUD_ID
    url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/2/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    jql_query = f'parent = {epic_id_or_key}'
    payload = {
        "jql": jql_query,
        "startAt": 0,
        "maxResults": 50,
        "fields": ["id", "key", "summary", "status", "assignee"]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            issues = response.json().get('issues', [])
            logger.success("Child issues retrieved successfully for epic {}", epic_id_or_key)
            return issues
        else:
            logger.error("Failed to retrieve child issues for epic {}. Status code: {}, Response: {}", epic_id_or_key, response.status_code, response.text)
            return None
    except requests.exceptions.RequestException as e:
        logger.exception("Network error occurred while retrieving child issues: {}", e)
        return None
def format_linked_issues(combined_details):
    """
    Formats the combined epic details and list of linked child issues for display or further processing.

    Args:
        combined_details (dict): A dictionary containing epic details and a list of child issues.

    Returns:
        dict: Formatted epic details and a list of formatted child issues.
    """
    logger.trace("Entering format_linked_issues with combined_details: {}", combined_details)
    formatted_issues_list = []
    if not combined_details or "ChildIssues" not in combined_details or not combined_details["ChildIssues"]:
        logger.info("No linked issues found to format. Combined details: {}", combined_details)
        return {"EpicDetails": combined_details.get("EpicDetails", {}), "ChildIssues": formatted_issues_list}

    linked_issues = combined_details["ChildIssues"]
    logger.info("Formatting {} linked issues.", len(linked_issues))
    for issue in linked_issues:
        fields = issue.get('fields', {})
        formatted_issue = {
            "Key": issue.get('key'),
            "Summary": fields.get('summary', 'No summary provided'),
            "Description": fields.get('description', 'No description provided'),
            # Additional fields as needed
        }
        formatted_issues_list.append(formatted_issue)
        logger.debug("Formatted issue: {}", formatted_issue)
    
    result = {
        "EpicDetails": combined_details.get("EpicDetails", {}),
        "ChildIssues": formatted_issues_list
    }
    logger.success("Formatted linked issues successfully. Result: {}", result)
    return result

def format_jira_issue(raw_issue_details):
    logger.trace("Entering format_jira_issue with raw_issue_details: {}", raw_issue_details)
    issue = raw_issue_details.get('fields', {})
    formatted_issue = {
        "Summary": issue.get('summary', 'No summary provided'),
        "Description": issue.get('description', 'No description provided'),
        "Issue Type": issue.get('issuetype', {}).get('name', 'N/A'),
        "Status": issue.get('status', {}).get('name', 'N/A'),
        # Add more fields here as needed
    }
    logger.debug("Formatted Jira issue: {}", formatted_issue)
    return formatted_issue
