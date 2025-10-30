import discord
import json
from discord.ext import commands
from discord import app_commands
import os
from datetime import datetime, timezone
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import re

class OsuCog(commands.Cog):
    """Simple osu! cog"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    group = app_commands.Group(name="osu", description="osu! related commands")

    @group.command(name="link", description="Check if your account is linked or not")
    async def osulink(self, interaction: discord.Interaction) -> None:
        user_data = None
        # Use helper attached to bot by main script
        if hasattr(self.bot, 'findOsulUser'):
            user_data = self.bot.findOsulUser(interaction.user.id)

        if user_data:
            linked_at = user_data.get('linkedAt', 'unknown')
            await interaction.response.send_message(
                f"Your osu! account is linked! Last linked at {str(linked_at)}"
            )
        else:
            await interaction.response.send_message(
                "Your osu! account is not linked.", ephemeral=True
            )
    @group.command(name="unlink", description="Unlink your osu! account, you will still have access to the server")
    async def osuunlink(self, interaction: discord.Interaction) -> None:
        user_data = None
        # Use helper attached to bot by main script
        if hasattr(self.bot, 'findOsulUser'):
            user_data = self.bot.findOsulUser(interaction.user.id)

        if user_data:
            await interaction.response.send_message(
                f"Your osu! account is now unlinked! Your authentication tokens are now deleted from our database. We hope to see you link again in the future."
            )
            self.bot.removeOsulUser(interaction.user.id)
        else:
            await interaction.response.send_message(
                "Your osu! account is not linked, so it is not possible to unlink.", ephemeral=True
            )
    @group.command(name="auth", description="Authenticate your osu! account to refresh tokens")
    async def osuauth(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"To authenticate your osu! account, please visit the following link: https://osu.ppy.sh/oauth/authorize?client_id={self.bot.client_id}&response_type=code&scope=public&redirect_uri={self.bot.redirect_uri}"
        , ephemeral=True)

    @group.command(name="profile", description="Get your osu! profile or somebody else's")
    @app_commands.describe(
        user="The osu! username to look up (leave blank for your own)",
        mode="The game mode to display stats for",
        detailed="Whether to show more stats or not"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="osu!standard", value="osu"),
        app_commands.Choice(name="osu!taiko", value="taiko"),
        app_commands.Choice(name="osu!catch", value="fruits"),
        app_commands.Choice(name="osu!mania", value="mania")
    ], detailed=[
        app_commands.Choice(name="Yes", value="true"),
        app_commands.Choice(name="No", value="false")
    ])
    async def osuprofile(self, interaction: discord.Interaction, user: str | None = None, mode: app_commands.Choice[str] | None = None, detailed: app_commands.Choice[str] | None = None) -> None:
        user_tokens = self.bot.findOsulUser(interaction.user.id)
        if not user_tokens:
            await interaction.response.send_message(
                "Your osu! account is not linked. Please link your account first.", ephemeral=True
            )
            return
        data = None
        
        # Get the mode value (defaults to "osu" if not provided)
        mode_value = mode.value if mode else "osu"
        detailbool = detailed.value if detailed else "false"
        mode_display = None

        if mode_value == "osu":
            mode_display = "osu!standard"
        elif mode_value == "taiko":
            mode_display = "osu!taiko"
        elif mode_value == "mania":
            mode_display = "osu!mania"
        elif mode_value == "fruits":    
            mode_display = "osu!catch (ctb)"

        if not user:
            # fetch own profile
            data = self.bot.connectOsuEndpoint(f"me/{mode_value}", "GET", {}, user_tokens['osuAccessToken'], user_tokens['osuRefreshToken']) # endpoint, method, body, access, refresh
        else:
            # fetch specified user's profile
            data = self.bot.connectOsuEndpoint(f"users/{user}/{mode_value}", "GET", {}, user_tokens['osuAccessToken'], user_tokens['osuRefreshToken']) # endpoint, method, body, access, refresh

        # Check if we got valid data back
        if not data or not isinstance(data, dict):
            await interaction.response.send_message(
                "❌ Failed to fetch osu! profile data. Please try again later.", ephemeral=True
            )
            return
        
        # Safely extract nested values with defaults
        stats = data.get('statistics', {})
        rank_highest = data.get('rank_highest', {})
        country = data.get('country', {})
        team = data.get('team', {})
        level = stats.get('level', {})
        grade_counts = stats.get('grade_counts', {})
        cover = data.get('cover', {})

        
        # Build title with safe defaults
        team_name = team.get('short_name', '') if team else ''
        team_name_full = team.get('name', '') if team else ''
        team_id = team.get('id', 0) if team else 0
        username = data.get('username', 'Unknown')
        country_code = data.get('country_code', 'XX')
        current_level = level.get('current', 0) if level else 0
        user_id = data.get('id', 0)

        # Build regional indicator flag emoji from country_code (e.g., US -> 🇺🇸)
        def country_flag(cc: str) -> str:
            if not cc or len(cc) != 2:
                return ''
            cc = cc.upper()
            if not cc.isalpha():
                return ''
            base = 0x1F1E6
            try:
                return chr(base + ord(cc[0]) - ord('A')) + chr(base + ord(cc[1]) - ord('A'))
            except Exception:
                return ''

        flag = country_flag(country_code)
        if flag:
            title = f"{mode_display} Profile: {flag} {team_name} {username} (level {current_level})".strip()
        else:
            title = f"{mode_display} Profile: {team_name} {username} ({country_code} - level {current_level})".strip()
        
        # Build description with safe formatting
        global_rank = self.bot.formatNumber(stats.get('global_rank'))
        country_rank = self.bot.formatNumber(stats.get('country_rank'))
        country_short = country.get('code', country_code) if country else country_code
        peak_rank = self.bot.formatNumber(rank_highest.get('rank')) if rank_highest else 'N/A'
        pp_value = self.bot.formatNumber(stats.get('pp'))
        accuracy = stats.get('hit_accuracy', 0.0)
        play_count = self.bot.formatNumber(stats.get('play_count'))
        total_score = self.bot.formatNumber(stats.get('total_score'))
        ranked_score = self.bot.formatNumber(stats.get('ranked_score'))
        # Extra details
        previous_names = ", ".join(data.get('previous_usernames', [])) if data.get('previous_usernames') else 'N/A'
        playstyles = ", ".join(data.get('playstyle', [])) if data.get('playstyle') else 'N/A'
        countone = stats.get('count_100', {})
        counttwo = stats.get('count_300', {})
        countthree = stats.get('count_50', {})
        countfour = stats.get('count_miss', {})
        occupation = data.get('occupation', 'N/A')
        interests = data.get('interests', 'N/A')
        location = data.get('location', 'N/A')
        discordname = data.get('discord', 'N/A')
        twittername = data.get('twitter', 'N/A')
        kudosu = f"{data.get('kudosu', {}).get('total', 0)} (Available: {data.get('kudosu', {}).get('available', 0)})"
        pending_beatmapsets = self.bot.formatNumber(data.get('pending_beatmapset_count', 0))
        replays_watched_by_others = self.bot.formatNumber(stats.get('replays_watched_by_others', 0))
        sp_level = data.get('support_level', 0)
        
        # Format last online time using Discord timestamp
        last_visit = data.get('last_visit')
        if last_visit:
            try:
                dt = datetime.fromisoformat(last_visit.replace('Z', '+00:00'))
                # Calculate relative time manually for footer since Discord timestamps don't work there
                now = datetime.now(timezone.utc)
                delta = now - dt
                seconds = int(delta.total_seconds())
                
                if seconds < 60:
                    last_online_text = f"{seconds} second{'s' if seconds != 1 else ''} ago"
                elif seconds < 3600:
                    minutes = seconds // 60
                    last_online_text = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
                elif seconds < 86400:
                    hours = seconds // 3600
                    last_online_text = f"{hours} hour{'s' if hours != 1 else ''} ago"
                elif seconds < 2592000:  # 30 days
                    days = seconds // 86400
                    last_online_text = f"{days} day{'s' if days != 1 else ''} ago"
                else:
                    last_online_text = dt.strftime("%B %d, %Y")
            except Exception:
                last_online_text = 'Unknown'
        else:
            last_online_text = 'Unknown'
        
        description = (
            f"**>┃ Rank:** #{global_rank}, ({country_short}#{country_rank})\n"
            f"**>┃ Peak Rank:** #{peak_rank}\n"
            f"**>┃ PP:** {pp_value}pp\n"
            f"**>┃ Accuracy:** {accuracy:.2f}%\n"
            f"**>┃ Playcount:** {play_count} plays\n"
            f"**>┃ Total Score:** {total_score} points\n"
            f"**>┃ Ranked Score:** {ranked_score} points\n"
            f"**>┃ Team:** [{team_name_full} ({team_name})](https://osu.ppy.sh/teams/{team_id})\n"
            f"**>┃ Grades:** <:gradeXSS:1433338218320760842> `{grade_counts.get('ss', 0)}`, <:gradeXHSSH:1433338240131141642> `{grade_counts.get('ssh', 0)}`, "
            f"<:gradeS:1433338127245639711> `{grade_counts.get('s', 0)}`, <:gradeSH:1433338154621861928> `{grade_counts.get('sh', 0)}`, <:gradeA:1433338005212368916> `{grade_counts.get('a', 0)}`\n"
            f"**>┃ Banner: Image below**"
        )
        
        dataEmbed = None
        dataEmbed = discord.Embed(
            title=title,
            
            url=f"https://osu.ppy.sh/users/{user_id}",
            color=0xFF66AA,
            description=description
        )
        detailedEmbed = discord.Embed(
            title=f"Additional Details for {team_name} {username}",
            color=0xFF66AA,
            description=(
                f"**>┃ Previous Username/s:** {previous_names}\n"
                f"**>┃ Playstyle/s:** {playstyles}\n"
                f"**>┃ Occupation/s:** {occupation}\n"
                f"**>┃ Interest/s:** {interests}\n"
                f"**>┃ Location:** {location}\n"
                f"**>┃ Discord Username:** {discordname}\n"
                f"**>┃ Twitter Username:** {twittername}\n"
                f"**>┃ Kudosu:** {kudosu}\n"
                f"**>┃ Pending Beatmapsets:** {pending_beatmapsets}\n"
                f"**>┃ Replays watched by Others:** {replays_watched_by_others}\n"
                f"**>┃ Supporter Level:** {sp_level}\n"



                f"**>┃ Counts:** <:hit100:1433356282659868714> `{self.bot.formatNumber(countone)}` <:hit300:1433356437672955924> `{self.bot.formatNumber(counttwo)}` <:hit50:1433356116560969820> `{self.bot.formatNumber(countthree)}` <:miss:1433355834833895505> `{self.bot.formatNumber(countfour)}`\n"
                f"**>┃ Graphs: Image below**"
            )
        )

        # Set thumbnail and image if available
        avatar_url = data.get('avatar_url')
        if avatar_url:
            dataEmbed.set_thumbnail(url=avatar_url)
        
        # Generate combined graph with rank history, monthly playcounts, and replays watched
        rank_history = data.get('rank_history', {})
        rank_data = rank_history.get('data', [])
        monthly_playcounts = data.get('monthly_playcounts', [])
        replays_watched_counts = data.get('replays_watched_counts', [])
        combined_graph_file = None
        
        if (rank_data and len(rank_data) > 0) or (monthly_playcounts and len(monthly_playcounts) > 0) or (replays_watched_counts and len(replays_watched_counts) > 0):
            try:
                # Create figure with 3 subplots stacked vertically
                fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), facecolor='#1a1a1a')
                
                # --- Top graph: Rank History ---
                if rank_data and len(rank_data) > 0:
                    ax1.set_facecolor('#1a1a1a')
                    days = list(range(len(rank_data)))
                    
                    # Draw line with gradient fill
                    ax1.plot(days, rank_data, color='#FFB84D', linewidth=2.5, zorder=2)
                    ax1.fill_between(days, rank_data, max(rank_data), alpha=0.3, color='#FFB84D', zorder=1)
                    
                    # Style the axes
                    ax1.spines['top'].set_visible(False)
                    ax1.spines['right'].set_visible(False)
                    ax1.spines['left'].set_color('#404040')
                    ax1.spines['bottom'].set_color('#404040')
                    ax1.tick_params(colors='#808080', which='both', length=0)
                    ax1.invert_yaxis()
                    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
                    ax1.set_xlabel('')
                    ax1.set_ylabel('Rank', color='#808080', fontsize=10)
                    ax1.grid(False)
                    ax1.set_title('Rank History', color='#FFB84D', fontsize=12, pad=10)
                else:
                    ax1.set_visible(False)
                
                # --- Middle graph: Monthly Playcounts ---
                if monthly_playcounts and len(monthly_playcounts) > 0:
                    ax2.set_facecolor('#2b2b2b')
                    
                    # Extract labels and counts
                    labels = []
                    for entry in monthly_playcounts:
                        date_str = entry.get('start_date', '')
                        if date_str:
                            try:
                                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                labels.append(dt.strftime('%b %Y'))
                            except Exception:
                                labels.append(date_str[-7:])
                        else:
                            labels.append('')
                    counts = [entry.get('count', 0) for entry in monthly_playcounts]
                    
                    # Plot line chart
                    ax2.plot(range(len(counts)), counts, color='#D4AF37', linewidth=2.5, zorder=2)
                    ax2.fill_between(range(len(counts)), counts, 0, alpha=0.15, color='#D4AF37', zorder=1)
                    
                    # Style the axes
                    ax2.spines['top'].set_visible(False)
                    ax2.spines['right'].set_visible(False)
                    ax2.spines['left'].set_color('#505050')
                    ax2.spines['bottom'].set_color('#505050')
                    ax2.grid(True, alpha=0.15, color='#505050', linewidth=0.5, linestyle='-', zorder=0)
                    ax2.tick_params(colors='#909090', which='both', length=0)
                    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
                    
                    # Set X axis labels
                    step = max(1, len(labels) // 10)
                    ax2.set_xticks(range(0, len(labels), step))
                    ax2.set_xticklabels([labels[i] for i in range(0, len(labels), step)], rotation=45, ha='right', fontsize=8)
                    ax2.set_xlabel('')
                    ax2.set_ylabel('Playcount', color='#909090', fontsize=10)
                    ax2.set_title('Monthly Playcounts', color='#D4AF37', fontsize=12, pad=10)
                else:
                    ax2.set_visible(False)
                
                # --- Bottom graph: Replays Watched ---
                if replays_watched_counts and len(replays_watched_counts) > 0:
                    ax3.set_facecolor('#2b2b2b')
                    
                    # Extract labels and counts
                    replay_labels = []
                    for entry in replays_watched_counts:
                        date_str = entry.get('start_date', '')
                        if date_str:
                            try:
                                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                replay_labels.append(dt.strftime('%b %Y'))
                            except Exception:
                                replay_labels.append(date_str[-7:])
                        else:
                            replay_labels.append('')
                    replay_counts = [entry.get('count', 0) for entry in replays_watched_counts]
                    
                    # Plot line chart with different color
                    ax3.plot(range(len(replay_counts)), replay_counts, color='#66CCFF', linewidth=2.5, zorder=2)
                    ax3.fill_between(range(len(replay_counts)), replay_counts, 0, alpha=0.15, color='#66CCFF', zorder=1)
                    
                    # Style the axes
                    ax3.spines['top'].set_visible(False)
                    ax3.spines['right'].set_visible(False)
                    ax3.spines['left'].set_color('#505050')
                    ax3.spines['bottom'].set_color('#505050')
                    ax3.grid(True, alpha=0.15, color='#505050', linewidth=0.5, linestyle='-', zorder=0)
                    ax3.tick_params(colors='#909090', which='both', length=0)
                    ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
                    
                    # Set X axis labels
                    step_replay = max(1, len(replay_labels) // 10)
                    ax3.set_xticks(range(0, len(replay_labels), step_replay))
                    ax3.set_xticklabels([replay_labels[i] for i in range(0, len(replay_labels), step_replay)], rotation=45, ha='right', fontsize=8)
                    ax3.set_xlabel('')
                    ax3.set_ylabel('Replays Watched', color='#909090', fontsize=10)
                    ax3.set_title('Replays Watched by Others', color='#66CCFF', fontsize=12, pad=10)
                else:
                    ax3.set_visible(False)
                
                plt.tight_layout(pad=1.0)
                
                # Save to bytes buffer
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=120, facecolor='#1a1a1a', edgecolor='none')
                buf.seek(0)
                plt.close()
                
                # Create Discord file
                combined_graph_file = discord.File(buf, filename='combined_graphs.png')
                
            except Exception as e:
                print(f"[osuprofile] Failed to generate combined graphs: {e}")
        
        dataEmbed.set_footer(text=f"User last online {last_online_text} via WS")

        # If no graph, use cover image
        cover_url = cover.get('url') if cover else None
        if cover_url:
            dataEmbed.set_image(url=cover_url)
        if combined_graph_file:
            detailedEmbed.set_image(url='attachment://combined_graphs.png')
        
        # Send the main embed first
        await interaction.response.send_message(embed=dataEmbed)

        try:
            if combined_graph_file:
                await interaction.followup.send(embed=detailedEmbed, file=combined_graph_file)
            else:
                await interaction.followup.send(embed=detailedEmbed)
        except Exception as e:
            print(f"[osuprofile] Failed to send followup (embed+file): {e}")

    @group.command(name="top", description="Get your top plays or someone else's")
    @app_commands.describe(
        user="The osu! username to look up (leave blank for your own)",
        mode="The game mode to display top plays for"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="osu!standard", value="osu"),
        app_commands.Choice(name="osu!taiko", value="taiko"),
        app_commands.Choice(name="osu!catch", value="fruits"),
        app_commands.Choice(name="osu!mania", value="mania")
    ])
    async def osutop(self, interaction: discord.Interaction, user: str | None = None, mode: app_commands.Choice[str] | None = None) -> None:
        user_tokens = self.bot.findOsulUser(interaction.user.id)
        if not user_tokens:
            await interaction.response.send_message(
                "Your osu! account is not linked. Please link your account first.", ephemeral=True
            )
            return
        
        # Get the mode value (defaults to "osu" if not provided)
        mode_value = mode.value if mode else "osu"
        mode_display = None

        if mode_value == "osu":
            mode_display = "osu!standard"
        elif mode_value == "taiko":
            mode_display = "osu!taiko"
        elif mode_value == "mania":
            mode_display = "osu!mania"
        elif mode_value == "fruits":    
            mode_display = "osu!catch (ctb)"

        # Get user info first to get their username/ID
        user_data = None
        if not user:
            user_data = self.bot.connectOsuEndpoint(f"me/{mode_value}", "GET", {}, user_tokens['osuAccessToken'], user_tokens['osuRefreshToken'])
        else:
            user_data = self.bot.connectOsuEndpoint(f"users/{user}/{mode_value}", "GET", {}, user_tokens['osuAccessToken'], user_tokens['osuRefreshToken'])

        if not user_data or not isinstance(user_data, dict):
            await interaction.response.send_message(
                "❌ Failed to fetch user data. Please try again later.", ephemeral=True
            )
            return
        
        user_id = user_data.get('id', 0)
        username = user_data.get('username', 'Unknown')
        
        # Fetch top plays
        top_plays = self.bot.connectOsuEndpoint(f"users/{user_id}/scores/best", "GET", {"mode": mode_value, "limit": 5}, user_tokens['osuAccessToken'], user_tokens['osuRefreshToken'])
        
        if not top_plays or not isinstance(top_plays, list) or len(top_plays) == 0:
            await interaction.response.send_message(
                f"❌ No top plays found for **{username}** in {mode_display}.", ephemeral=True
            )
            return
        
        # Build embed
        embed = discord.Embed(
            title=f"{mode_display} Top Plays for {username}",
            url=f"https://osu.ppy.sh/users/{user_id}",
            color=0xFF66AA
        )
        
        # Add each play as a field
        for idx, play in enumerate(top_plays[:5], 1):
            beatmap = play.get('beatmap', {})
            beatmapset = play.get('beatmapset', {})
            stats = play.get('statistics', {})
            
            title = beatmapset.get('title', 'Unknown')
            artist = beatmapset.get('artist', 'Unknown')
            version = beatmap.get('version', 'Unknown')
            beatmap_id = beatmap.get('id', 0)
            
            pp = play.get('pp', 0)
            accuracy = play.get('accuracy', 0) * 100
            rank = play.get('rank', 'F')
            max_combo = play.get('max_combo', 0)
            mods = play.get('mods', [])
            mods_str = '+' + ''.join(mods) if mods else 'No mods'
            
            count_300 = stats.get('count_300', 0)
            count_100 = stats.get('count_100', 0)
            count_50 = stats.get('count_50', 0)
            count_miss = stats.get('count_miss', 0)
            
            # Format date
            created_at = play.get('created_at', '')
            date_str = 'Unknown date'
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    date_str = dt.strftime('%b %d, %Y')
                except Exception:
                    pass
            
            field_value = (
                f"[{artist} - {title} [{version}]](https://osu.ppy.sh/b/{beatmap_id})\n"
                f"**{self.bot.formatNumber(pp)}pp** • {accuracy:.2f}% • {rank} • {max_combo}x\n"
                f"{mods_str} • {date_str}\n"
                f"<:hit300:1433356437672955924> {count_300} <:hit100:1433356282659868714> {count_100} <:hit50:1433356116560969820> {count_50} <:miss:1433355834833895505> {count_miss}"
            )
            
            embed.add_field(name=f"#{idx}", value=field_value, inline=False)
        
        avatar_url = user_data.get('avatar_url')
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        
        embed.set_footer(text=f"Top 5 plays for {username} via WS")
        
        await interaction.response.send_message(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for osu! beatmap links and respond with beatmap info"""
        if message.author.bot:
            return
        
        # Regex patterns for osu! beatmap URLs
        beatmap_pattern = r'https?://osu\.ppy\.sh/beatmapsets/(\d+)(?:#(osu|taiko|fruits|mania)/(\d+))?'
        beatmap_direct = r'https?://osu\.ppy\.sh/b(?:eatmaps)?/(\d+)'
        
        match = re.search(beatmap_pattern, message.content)
        match_direct = re.search(beatmap_direct, message.content)
        
        beatmap_id = None
        if match:
            # Has beatmapset ID and possibly specific difficulty ID
            beatmapset_id = match.group(1)
            beatmap_id = match.group(3) if match.group(3) else None
        elif match_direct:
            # Direct beatmap ID link
            beatmap_id = match_direct.group(1)
        else:
            return  # No osu! link found
        
        # Try to find a linked user to use their tokens (prefer message author)
        user_tokens = self.bot.findOsulUser(message.author.id)
        if not user_tokens:
            # Try to find any linked user in the server
            return  # Can't fetch without tokens
        
        try:
            # Fetch beatmap data
            beatmap_data = None
            is_specific_difficulty = False
            
            if beatmap_id:
                # Specific difficulty requested
                beatmap_data = self.bot.connectOsuEndpoint(f"beatmaps/{beatmap_id}", "GET", {}, user_tokens['osuAccessToken'], user_tokens['osuRefreshToken'])
                is_specific_difficulty = True
            else:
                # Just beatmapset - fetch set info
                beatmap_data = self.bot.connectOsuEndpoint(f"beatmapsets/{beatmapset_id}", "GET", {}, user_tokens['osuAccessToken'], user_tokens['osuRefreshToken'])
                is_specific_difficulty = False
            
            if not beatmap_data:
                return
            
            if is_specific_difficulty:
                # Showing specific difficulty info
                beatmapset = beatmap_data.get('beatmapset', {})
                title = beatmapset.get('title', 'Unknown')
                artist = beatmapset.get('artist', 'Unknown')
                creator = beatmapset.get('creator', 'Unknown')
                version = beatmap_data.get('version', 'Unknown')
                beatmapset_id_display = beatmapset.get('id', beatmap_data.get('beatmapset_id', 0))
                
                difficulty_rating = beatmap_data.get('difficulty_rating', 0)
                bpm = beatmap_data.get('bpm', 0)
                total_length = beatmap_data.get('total_length', beatmap_data.get('hit_length', 0))
                count_circles = beatmap_data.get('count_circles', 0)
                count_sliders = beatmap_data.get('count_sliders', 0)
                count_spinners = beatmap_data.get('count_spinners', 0)
                ar = beatmap_data.get('ar', 0)
                cs = beatmap_data.get('cs', 0)
                od = beatmap_data.get('accuracy', beatmap_data.get('od', 0))
                hp = beatmap_data.get('drain', beatmap_data.get('hp', 0))
                max_combo = beatmap_data.get('max_combo', 0)
                
                mode = beatmap_data.get('mode', 'osu')
                status = beatmap_data.get('status', 'unknown').title()
                beatmap_id_display = beatmap_data.get('id', 0)
                
                # Format length
                minutes = total_length // 60
                seconds = total_length % 60
                length_str = f"{minutes}:{seconds:02d}"
                
                # Build embed for specific difficulty
                embed = discord.Embed(
                    title=f"{artist} - {title} [{version}]",
                    url=f"https://osu.ppy.sh/b/{beatmap_id_display}",
                    color=0xFF66AA,
                    description=(
                        f"**Mapped by** {creator}\n"
                        f"**Status:** {status} • **Mode:** {mode}\n"
                        f"**⭐ Difficulty:** {difficulty_rating:.2f}★\n\n"
                        f"**Length:** {length_str} • **BPM:** {bpm}\n"
                        f"**Objects:** {count_circles + count_sliders + count_spinners} "
                        f"({count_circles} circles, {count_sliders} sliders, {count_spinners} spinners)\n"
                        f"**Max Combo:** {max_combo}x\n\n"
                        f"**CS:** {cs} • **AR:** {ar} • **OD:** {od} • **HP:** {hp}"
                    )
                )
                
                # Set thumbnail and image
                cover_url = beatmapset.get('covers', {}).get('cover@2x')
                if cover_url:
                    embed.set_thumbnail(url=cover_url)
                
                list_cover = beatmapset.get('covers', {}).get('list@2x')
                if list_cover:
                    embed.set_image(url=list_cover)
                
                embed.set_footer(text=f"Beatmap ID: {beatmap_id_display} • Beatmapset ID: {beatmapset_id_display}")
                
            else:
                # Showing beatmapset info with all difficulties
                title = beatmap_data.get('title', 'Unknown')
                artist = beatmap_data.get('artist', 'Unknown')
                creator = beatmap_data.get('creator', 'Unknown')
                beatmapset_id_display = beatmap_data.get('id', 0)
                status = beatmap_data.get('status', 'unknown').title()
                bpm = beatmap_data.get('bpm', 0)
                
                beatmaps = beatmap_data.get('beatmaps', [])
                
                # Get min/max length and other stats
                if beatmaps:
                    lengths = [bm.get('total_length', 0) for bm in beatmaps]
                    min_length = min(lengths) if lengths else 0
                    max_length = max(lengths) if lengths else 0
                    
                    # Format length
                    if min_length == max_length:
                        min_minutes = min_length // 60
                        min_seconds = min_length % 60
                        length_str = f"{min_minutes}:{min_seconds:02d}"
                    else:
                        min_minutes = min_length // 60
                        min_seconds = min_length % 60
                        max_minutes = max_length // 60
                        max_seconds = max_length % 60
                        length_str = f"{min_minutes}:{min_seconds:02d} - {max_minutes}:{max_seconds:02d}"
                else:
                    length_str = "-"
                
                # Build difficulty list with details
                diff_lines = []
                for bm in beatmaps:
                    diff_name = bm.get('version', 'Unknown')
                    stars = bm.get('difficulty_rating', 0)
                    max_combo = bm.get('max_combo', 0)
                    ar = bm.get('ar', 0)
                    od = bm.get('accuracy', bm.get('od', 0))
                    hp = bm.get('drain', bm.get('hp', 0))
                    cs = bm.get('cs', 0)
                    diff_id = bm.get('id', 0)
                    
                    diff_lines.append(
                        f"▸ **[{diff_name}](https://osu.ppy.sh/b/{diff_id}):** {stars:.2f}★ "
                        f"• Max Combo: {max_combo}x\n"
                        f"  **AR:** {ar} • **OD:** {od} • **HP:** {hp} • **CS:** {cs}"
                    )
                
                difficulties_text = '\n'.join(diff_lines)
                
                # Get additional info
                ranked_date = beatmap_data.get('ranked_date', '')
                submitted_date = beatmap_data.get('submitted_date', '')
                last_updated = beatmap_data.get('last_updated', '')
                
                date_info = ""
                if status == "Ranked" and ranked_date:
                    try:
                        dt = datetime.fromisoformat(ranked_date.replace('Z', '+00:00'))
                        date_info = f"**{status}** | Last Updated {dt.strftime('%b %d, %Y')}"
                    except:
                        date_info = f"**{status}**"
                else:
                    date_info = f"**{status}**"
                
                # Download links
                download_links = []
                download_links.append(f"[map](https://osu.ppy.sh/d/{beatmapset_id_display})")
                download_links.append(f"[nerinyan](https://api.nerinyan.moe/d/{beatmapset_id_display})")
                download_links.append(f"[beatconnect](https://beatconnect.io/b/{beatmapset_id_display})")
                download_links.append(f"[sayobot](https://osu.sayobot.cn/osu.php?s={beatmapset_id_display})")
                download_str = " | ".join(download_links)
                
                modes_present = list(set([bm.get('mode', 'osu') for bm in beatmaps]))
                modes_str = ", ".join(modes_present) if modes_present else "-"
                
                # Build embed for beatmapset
                embed = discord.Embed(
                    title=f"{title} - {artist} <Version 0> by {creator}",
                    url=f"https://osu.ppy.sh/beatmapsets/{beatmapset_id_display}",
                    color=0xFF66AA,
                    description=(
                        f"**Length:** {length_str} **BPM:** {bpm} **Modes:** {modes_str}\n"
                        f"**Download:** {download_str}\n\n"
                        f"{difficulties_text}\n\n"
                        f"{date_info}"
                    )
                )
                
                # Set thumbnail and image
                cover_url = beatmap_data.get('covers', {}).get('card@2x')
                if cover_url:
                    embed.set_thumbnail(url=cover_url)
                
                list_cover = beatmap_data.get('covers', {}).get('cover@2x')
                if list_cover:
                    embed.set_image(url=list_cover)
                
                embed.set_footer(text=f"Beatmapset ID: {beatmapset_id_display}")
            
            await message.channel.send(embed=embed)
            
        except Exception as e:
            print(f"[on_message beatmap] Failed to fetch beatmap: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(OsuCog(bot))
