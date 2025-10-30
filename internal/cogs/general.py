import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv

load_dotenv()


class GeneralCog(commands.Cog):
    """General commands for the bot"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    group = app_commands.Group(name="general", description="General commands for the bot")

    @group.command(name="about", description="Get information about the bot")
    async def about(self, interaction: discord.Interaction) -> None:
        communityInstance = None
        parenthesesString = "(community instance)"
        # determine if it is a community instance based on .env
        if os.getenv("CALLBACK_URI") == "https://osul.br0k3.me/oauth/osu/callback":
            communityInstance = False
            parenthesesString = "(official instance)"
        else:
            communityInstance = True


        embed = discord.Embed(
            title=f"osu!lounge bot {self.bot.version} {parenthesesString}",
            description=f"A Discord bot for osu!lounge. This is a {('community' if communityInstance else 'official')} instance. \n **GitHub**: br0k3x/osulounge",
        )
        await interaction.response.send_message(
            embed=embed
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
