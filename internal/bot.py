import discord
from discord import app_commands
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from datetime import datetime
import pymongo
import os
import json
import datetime
from typing import cast, Optional
from dotenv import load_dotenv
import aiohttp
import random
import requests
from cogwatch import watch

# Load environment variables
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
OSU_CLIENT_ID = int(os.getenv('OSU_CLIENT_ID', '0'))
OSU_CLIENT_SECRET = os.getenv('OSU_CLIENT_SECRET')
CALLBACK_URI = os.getenv('CALLBACK_URI')
mongoc = pymongo.MongoClient(os.getenv('MONGODB_CONNECTION_STRING'))


# Initialize bot with intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class OsuBot(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(command_prefix='o!', intents=intents, description="osu!lounge clanker bot", case_insensitive=True, help_command=None)

    @watch(path='cogs', preload=True)
    async def on_ready(self):
        print(f"osu!lounge clanker (or bot) is online as {self.user} (ID: {self.user.id})")
        print("------")
        print('🔄️ Attempting to sync tree...')
        await self.tree.sync()
        print('✅ Commands synced!')
    
    async def setup_hook(self):
        """Load cogs before bot starts"""
        cogs_path = os.path.join(os.path.dirname(__file__), 'cogs')
        if not os.path.isdir(cogs_path):
            print(f"No cogs directory found at {cogs_path}")
            return

        for fname in os.listdir(cogs_path):
            if fname.endswith('.py') and not fname.startswith('__'):
                module = f'cogs.{fname[:-3]}'
                try:
                    await self.load_extension(module)
                    print(f"✅ Loaded cog: {module}")
                except Exception as e:
                    print(f"⚠️ Failed to load cog {module}: {e}")

bot = OsuBot()


# ==================
#   FUNCTIONS
# ==================
db = mongoc['main']
users_collection = db['users']
def findOsulUser(discord_id):
    user_data = users_collection.find_one({'discordId': str(discord_id)})
    if user_data:
        print(f"[findOsulUser] Found user data for Discord ID: {discord_id}")
        print(user_data['osuAccessToken'])
    else:
        print(f"[findOsulUser] No user data found for Discord ID: {discord_id}")
    return user_data
    

def connectOsuEndpoint(endpoint_uri, method, body, access_token, refresh_token):
    """Connect to osu! API endpoint and return data"""

    # Test request to make sure the token is valid ( if its not then refresh )
    response = requests.get("https://osu.ppy.sh/api/v2/me", headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code == 401:
        # Token is invalid, refresh it
        print("[connectOsuEndpoint] Access token is invalid, refreshing...")
        refresh_payload = {
            "client_id": OSU_CLIENT_ID,
            "client_secret": OSU_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        refresh_response = requests.post("https://osu.ppy.sh/oauth/token", data=refresh_payload)
        if refresh_response.status_code == 200:
            new_tokens = refresh_response.json()
            # Update the tokens in the database. Use update_one on the collection (find_one() returns a document).
            users_collection.update_one(
                { 'osuAccessToken': str(access_token) },
                { "$set": {
                    "osuAccessToken": new_tokens.get("access_token"),
                    "osuRefreshToken": new_tokens.get("refresh_token")
                }}
            )
            access_token = new_tokens.get("access_token")
            refresh_token = new_tokens.get("refresh_token")
            print("[connectOsuEndpoint] Access token refreshed successfully.")

        else:
            print(f"[connectOsuEndpoint] Failed to refresh access token: {refresh_response.text}")

    # Make the actual request to the desired endpoint
    response = requests.request(method, f"https://osu.ppy.sh/api/v2/{endpoint_uri}", headers={"Authorization": f"Bearer {access_token}"}, json=body)
    return response.json()

def removeOsulUser(discord_id):
    result = users_collection.delete_one({'discordId': str(discord_id)})
    if result.deleted_count > 0:
        print(f"[removeOsulUser] Successfully removed user with Discord ID: {discord_id}")
    else:
        print(f"[removeOsulUser] No user found with Discord ID: {discord_id} to remove")

def formatNumber(number):
    """Format a number with commas, safely handling None and non-numeric values.

    Returns a human-friendly string (e.g., '1,234') or 'N/A' if the value is missing.
    """
    if number is None:
        return 0
    # If it's already a string that represents a number, try to convert
    try:
        # Prefer integer formatting when possible
        if isinstance(number, str):
            # Remove common separators
            cleaned = number.replace(',', '')
            if cleaned.isdigit():
                return format(int(cleaned), ',')
            # try float
            try:
                f = float(cleaned)
                # If it's whole number, cast to int
                if f.is_integer():
                    return format(int(f), ',')
                return format(f, ',')
            except Exception:
                return number
        if isinstance(number, int):
            return format(number, ',')
        if isinstance(number, float):
            # Show floats with no grouping decimals unless needed
            if number.is_integer():
                return format(int(number), ',')
            return format(number, ',')
        # Fallback: try to format directly
        return format(number, ',')
    except Exception:
        return str(number)

# ===================
#  COGS/COMMANDS
# ===================
# Attach helper function to bot so cogs can use it without circular imports
bot.findOsulUser = findOsulUser
bot.removeOsulUser = removeOsulUser
bot.connectOsuEndpoint = connectOsuEndpoint
bot.formatNumber = formatNumber
bot.client_id = OSU_CLIENT_ID
bot.client_secret = OSU_CLIENT_SECRET
bot.redirect_uri = CALLBACK_URI
bot.version = "1.0.7"


# ============================================
# Main 
# ============================================

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN not found in environment variables")
        exit(1)
    
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error, may be shutting down: {e}")