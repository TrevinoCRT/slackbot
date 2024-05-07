import aiohttp
from logger_config import setup_logger

logger = setup_logger()

async def get_miro_board_content(board_id, access_token):
    base_url = f"https://api.miro.com/v2/boards/{board_id}"
    items_url = f"{base_url}/items"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        try:
            logger.debug(f"Attempting to fetch board details for board ID: {board_id}")
            # Get board details
            async with session.get(base_url, headers=headers) as response:
                response.raise_for_status()
                board_content = await response.json()
                logger.debug("Board details fetched successfully.")

            # Initialize items collection
            board_content['items'] = []
            cursor = None

            logger.debug("Starting to fetch items with cursor-based pagination.")
            # Fetch items with cursor-based pagination
            while True:
                params = {}
                if cursor:
                    params['cursor'] = cursor
                async with session.get(items_url, headers=headers, params=params) as response:
                    response.raise_for_status()
                    items_data = await response.json()
                    board_content['items'].extend(items_data.get('data', []))
                    cursor = items_data.get('cursor')
                    if not cursor:
                        logger.debug("All items fetched, no more cursor found.")
                        break

            logger.info("Successfully fetched all content for the board.")
            return board_content

        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch board content: {e}")
            return {"error": str(e)}

