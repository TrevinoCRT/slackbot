import asyncio
import json
import os


from openai import AsyncOpenAI
from shared import retrieve_tokens, logger, slack_app
from miro_data_assistant import analyze_miro_board_data
from jira_board_info import retrieve_jira_issue, update_issue_summary_and_description, get_issues_for_epic, create_new_jira_issue

# Load environment variables

# Global variables
global_thread_id = None

# Initialize OpenAI API client
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

async def execute_function(function_name, arguments, from_user):
    # Retrieve tokens for both Miro and Jira using the user ID
    miro_tokens = retrieve_tokens(from_user, 'miro')
    jira_tokens = retrieve_tokens(from_user, 'jira')

    miro_token = miro_tokens.get('access_token') if miro_tokens else None
    jira_token = jira_tokens.get('access_token') if jira_tokens else None

    if function_name == "get_miro_board_content":
        if not miro_token:
            logger.info("No Miro access token found. Prompting user to authenticate with Miro.")
            slack_app.client.chat_postMessage(
                channel=from_user,
                text="Please authenticate with Miro to continue. Click on the button in the Home tab."
            )
            return {"status": "error", "message": "Miro authentication required."}
        
        board_id = arguments.get("board_id")
        insights = await analyze_miro_board_data(board_id, miro_token)
        return insights

    elif function_name in ['get_jiraissue', 'update_jiraissue', 'get_issues_for_epic', 'create_new_jira_issue']:
        if not jira_token:
            logger.info("No Jira access token found. Prompting user to authenticate with Jira.")
            slack_app.client.chat_postMessage(
                channel=from_user,
                text="Please authenticate with Jira to continue. Click on the button in the Home tab."
            )
            return {"status": "error", "message": "Jira authentication required."}

        if function_name == 'get_jiraissue':
            issue_id = arguments.get("issue_id")
            return await retrieve_jira_issue(issue_id, jira_token)
        elif function_name == 'update_jiraissue':
            issue_id = arguments.get("issue_id")
            summary = arguments.get("summary")
            description = arguments.get("description")
            return await update_issue_summary_and_description(jira_token, issue_id, summary, description)
        elif function_name == "get_issues_for_epic":
            epic_id = arguments.get("epic_id")
            return await get_issues_for_epic(jira_token, epic_id)
        elif function_name == "create_new_jira_issue":
            summary = arguments.get("summary")
            description = arguments.get("description")
            project_id = arguments.get("project_id")
            issue_type_id = arguments.get("issue_type_id")
            return await create_new_jira_issue(jira_token, summary, description, project_id, issue_type_id)
    else:
        return {"status": "error", "message": "Function not recognized"}


async def process_thread_with_assistant(query, assistant_id, model="gpt-4-turbo-2024-04-09", from_user=None):
    global global_thread_id
    response_texts = []
    response_files = []
    in_memory_files = []
    try:
        if not global_thread_id:
            logger.debug("Creating a new thread for the user query...")
            thread = await client.beta.threads.create()
            global_thread_id = thread.id
            logger.debug(f"New thread created with ID: {global_thread_id}")
        
        logger.debug("Adding the user query as a message to the thread...")
        await client.beta.threads.messages.create(
            thread_id=global_thread_id,
            role="user",
            content=query
        )
        logger.debug("User query added to the thread.")

        logger.debug("Creating a run to process the thread with the assistant...")
        run = await client.beta.threads.runs.create(
            thread_id=global_thread_id,
            assistant_id=assistant_id,
            model=model
        )
        logger.debug(f"Run created with ID: {run.id}")

        while True:
            logger.debug("Checking the status of the run...")
            run_status = await client.beta.threads.runs.retrieve(
                thread_id=global_thread_id,
                run_id=run.id
            )
            logger.debug(f"Current status of the run: {run_status.status}")

            if run_status.status == "requires_action":
                logger.debug("Run requires action. Executing specified function...")
                tool_call = run_status.required_action.submit_tool_outputs.tool_calls[0]
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                function_output = await execute_function(function_name, arguments, from_user)
                function_output_str = json.dumps(function_output)

                logger.debug("Submitting tool outputs...")
                await client.beta.threads.runs.submit_tool_outputs(
                    thread_id=global_thread_id,
                    run_id=run.id,
                    tool_outputs=[{
                        "tool_call_id": tool_call.id,
                        "output": function_output_str
                    }]
                )
                logger.debug("Tool outputs submitted.")

            elif run_status.status in ["completed", "failed", "cancelled"]:
                logger.debug("Fetching the latest message added by the assistant...")
                messages = await client.beta.threads.messages.list(
                    thread_id=global_thread_id,
                    order="desc"
                )
                
                latest_assistant_message = next((message for message in messages.data if message.role == "assistant"), None)

                if latest_assistant_message:
                    for content in latest_assistant_message.content:
                        if content.type == "text":
                            text_value = content.text.value
                            for annotation in content.text.annotations:
                                if annotation.type == "file_citation":
                                    cited_file = await client.files.retrieve(annotation.file_citation.file_id)
                                    citation_text = f"[Cited from {cited_file.filename}]"
                                    text_value = text_value.replace(annotation.text, citation_text)
                                elif annotation.type == "file_path":
                                    file_info = await client.files.retrieve(annotation.file_path.file_id)
                                    download_link = f"<https://platform.openai.com/files/{file_info.id}|Download {file_info.filename}>"
                                    text_value = text_value.replace(annotation.text, download_link)
                            response_texts.append(text_value)
                        elif content.type == "file":
                            file_id = content.file.file_id
                            file_mime_type = content.file.mime_type
                            response_files.append((file_id, mime_type))

                    for file_id, mime_type in response_files:
                        try:
                            logger.debug(f"Retrieving content for file ID: {file_id} with MIME type: {mime_type}")
                            file_response = await client.files.content(file_id)
                            file_content = file_response.content if hasattr(file_response, 'content') else file_response

                            extensions = {
                                "text/x-c": ".c", "text/x-csharp": ".cs", "text/x-c++": ".cpp",
                                "application/msword": ".doc", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                                "text/html": ".html", "text/x-java": ".java", "application/json": ".json",
                                "text/markdown": ".md", "application/pdf": ".pdf", "text/x-php": ".php",
                                "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
                                "text/x-python": ".py", "text/x-script.python": ".py", "text/x-ruby": ".rb",
                                "text/x-tex": ".tex", "text/plain": ".txt", "text/css": ".css",
                                "text/javascript": ".js", "application/x-sh": ".sh", "application/typescript": ".ts",
                                "application/csv": ".csv", "image/jpeg": ".jpeg", "image/gif": ".gif",
                                "image/png": ".png", "application/x-tar": ".tar",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                                "application/xml": "text/xml", "application/zip": ".zip"
                            }
                            file_extension = extensions.get(mime_type, ".bin")

                            local_file_path = f"./downloaded_file_{file_id}{file_extension}"
                            with open(local_file_path, "wb") as local_file:
                                local_file.write(file_content)
                            logger.debug(f"File saved locally at {local_file_path}")

                        except Exception as e:
                            logger.error(f"Failed to retrieve content for file ID: {file_id}. Error: {e}")

                break
            await asyncio.sleep(1)

        return {"text": response_texts, "in_memory_files": in_memory_files}

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return {"text": [], "in_memory_files": []}
    