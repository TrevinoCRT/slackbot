import json
from miro_board_info import get_miro_board_content
from openai import AsyncOpenAI
import os
from logger_config import setup_logger

logger = setup_logger()

# Load your OpenAI API key from an environment variable or other secure location
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

async def analyze_miro_board_data(board_id):
    board_data = await get_miro_board_content(board_id)
    formatted_board_data = json.dumps(board_data, indent=4)
    
    # Set a maximum character limit for the data sent to the model
    max_char_limit = 450000  # Adjust based on experimentation and buffer for system/user messages
    if len(formatted_board_data) > max_char_limit:
        # Truncate or summarize the data here
        formatted_board_data = formatted_board_data[:max_char_limit] + "\n... [Content truncated due to length]"
    
    conversation = [
        {"role": "system", "content": "You are a helpful assistant tasked with extracting information from a miro board api call in a structured, readable way."},
        {"role": "user", "content": f"Analyze this Miro board api call and format the details on the following (important text cards, process flows, frame titles, etc.): {formatted_board_data}"}
    ]
    
    response = await client.chat.completions.create(
        model="gpt-4-turbo-2024-04-09",
        messages=conversation
    )
    
    assistant_response = response.choices[0].message.content
    return assistant_response