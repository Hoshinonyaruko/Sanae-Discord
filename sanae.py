import discord
import json
import asyncio
from discord.ext import commands
from typing import Any
import aiohttp
import time
import configparser
import random
from dateutil.parser import isoparse
import re
import io
import langid
import requests

ws_conn = None

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='>', intents=intents)

sanae_config = configparser.ConfigParser()
sanae_config.read("sanae.ini")

@bot.event
async def on_ready():
    print(f'{bot.user} 已连接至 Discord!')

    bot_id = str(bot.user.id)  # 将 bot_id 转换为字符串
    await _setup(bot_id)

@bot.event
async def on_message(message):
    # Don't process messages sent by the bot itself
    if message.author == bot.user:
        return

    # Convert the Message object to a dictionary
    message_dict = message_to_dict(message)

    # Add the bot_id field
    message_dict["bot_id"] = bot.user.id

    # Print the message_dict (which now contains all fields)
    message_dict["timestamp"] = isoparse(message_dict["timestamp"])
    converted_json = convert_json(message_dict)
    print(converted_json)
    asyncio.create_task(send_to_ws(bot.user.id,converted_json))

    # Process the commands after printing the message_dict
    await bot.process_commands(message)


@bot.command()
async def ping(ctx):
    await ctx.send('pong')

async def _setup(bot_id):
    global ws_conn
    while True:
        async with aiohttp.ClientSession() as session:
            ws_url = generate_ws_url()
            print("将连接到地址~测试版本~:" + ws_url)

            headers = {
                "User-Agent": "Discord.py",
                "X-Client-Role": "Universal",
                "X-Self-ID": bot_id
            }
            try:
                async with session.ws_connect(ws_url, headers=headers) as ws:
                    message = {
                        "meta_event_type": "lifecycle",
                        "post_type": "meta_event",
                        "self_id": bot_id,
                        "sub_type": "connect",
                        "time": int(time.time())
                    }
                    await ws.send_str(json.dumps(message))
                    ws_conn = ws

                    # 设置心跳间隔
                    heartbeat_interval = 5000  # 5000 毫秒

                    while True:
                        # 发送心跳信息
                        heartbeat_message = {
                            "interval": heartbeat_interval,
                            "meta_event_type": "heartbeat",
                            "post_type": "meta_event",
                            "self_id": bot_id,
                            "time": int(time.time())
                        }
                        await ws.send_str(json.dumps(heartbeat_message))

                        # 等待心跳间隔
                        await asyncio.sleep(heartbeat_interval / 1000)  # 将毫秒转换为秒

                        # 处理接收到的消息
                        async for msg in ws:
                            asyncio.create_task(recv_message(msg, bot_id))

            except aiohttp.ClientError as e:
                print(f"Failed to connect websocket: {e}")

            except ConnectionResetError:
                print(f"连接断开，尝试重新连接...")
                await asyncio.sleep(5)  # 等待 5 秒再尝试重新连接

# 发送消息到 WebSocket 服务端
async def send_to_ws(self_id, message):
    if ws_conn:
            print("发送信息" + json.dumps(message))
            await ws_conn.send_str(json.dumps(message))

def generate_ws_url():
    if sanae_config.has_section("connect"):
        if not sanae_config.get("connect","ws").startswith("ws://"):
            ws_url = sanae_config.get("connect","ws").replace("http://", "ws://").replace("https://", "ws://").replace("wss://", "ws://")
            if not ws_url.startswith("ws://"):
                ws_url="ws://"+ws_url
            sanae_config.set("connect","ws",ws_url)
            with open("sanae.ini", "w") as f:
                sanae_config.write(f)  # 将修改后的配置写回文件
        return f"{sanae_config.get('connect', 'ws')}:{sanae_config.get('connect', 'port')}"
    else:
        #初次设定端口号是随机,20001~20050是早苗~
        #20001~20050,早苗
        # 20050~20070,澪
        # 20071~20099,浅羽
        # 20099-20120浅羽
        # 20120-20150澪
        port = random.randint(20001, 20150)
        #默认的早苗窝地址,交流频道,可替换为其他ob11的ws地址,https://kook.top/VAKBfJ
        ws_url = f"ws://101.35.247.237"
        if not sanae_config.has_section("connect"):
             sanae_config.add_section("connect")
        sanae_config.set("connect","ws",ws_url)
        sanae_config.set("connect","port",str(port))
        with open("sanae.ini", "w") as f:
             sanae_config.write(f)  # 将修改后的配置写回文件
        if 20001 <= port <= 20050:
            print.info(f"Connecting to 早苗 on port {port}...答疑解惑:https://kook.top/VAKBfJ")
        elif 20050 < port <= 20070:
            print.info(f"Connecting to 澪 on port {port}...答疑解惑:https://kook.top/gHCpJe")
        elif 20071 <= port <= 20099:
            print.info(f"Connecting to 浅羽 on port {port}...答疑解惑:https://kook.top/ff6ZZ2")
        elif 20099 < port <= 20120:
            print.info(f"Connecting to 浅羽 on port {port}...答疑解惑:https://kook.top/ff6ZZ2")
        else:
            print.info(f"Connecting to 澪 on port {port}...答疑解惑:https://kook.top/gHCpJe")
        return f"{ws_url}:{port}"

async def recv_message(msg, bot_id):
    #fixed_data = fix_invalid_escapes(msg.data)
    print("收到信息 (Bot {}): {}".format(bot_id, msg.data))
    data = json.loads(msg.data)
    action = data.get('action')

    if action == 'send_guild_channel_msg':
        params = data.get('params', {})
        guild_id = params.get('guild_id')
        channel_id = params.get('channel_id')
        message = params.get('message')

        # 将 [CQ:at,qq=数字] 替换为 Discord 的 @ 形式
        message = re.sub(r'\[CQ:at,qq=(\d+)\]', r'<@!\1>', message)

        await send_message_to_discord_channel(guild_id, channel_id, message)

async def send_message_to_discord_channel(guild_id, channel_id, message):
    guild = bot.get_guild(int(guild_id))
    if guild:
        channel = guild.get_channel(int(channel_id))
        if channel:
            # 提取图片 URL
            img_urls = re.findall(r'\[CQ:image,file=(http.+?)\]', message)
            # 删除图片标签，留下纯文本
            message = re.sub(r'\[CQ:image,file=.+?\]', '', message)

            if len(img_urls) == 1 and message.strip():
                # 使用 embed 发送单张图片和文本
                embed = discord.Embed(description=message, color=0x00ff00)
                embed.set_image(url=img_urls[0])
                await channel.send(embed=embed)
            else:
                # 如果有纯文本，发送纯文本
                if message.strip():
                    await channel.send(message)

                # 发送图片
                for img_url in img_urls:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(img_url) as resp:
                            if resp.status != 200:
                                print(f"获取图片失败：{img_url}")
                                continue
                            img_data = await resp.read()
                            img_file = discord.File(io.BytesIO(img_data), filename="image.png")
                            await channel.send(file=img_file)
        else:
            print(f"未找到频道 ID: {channel_id}")
    else:
        print(f"未找到服务器 ID: {guild_id}")

def message_to_dict(message):
    message_dict = {
        "id": message.id,
        "channel_id": message.channel.id,
        "guild_id": message.guild.id if message.guild else None,
        "author": {
            "id": message.author.id,
            "name": message.author.name,
            "discriminator": message.author.discriminator,
            "avatar_url": str(message.author.avatar.url),
        },
        "content": message.content,
        "timestamp": message.created_at.isoformat(),
        "edited_timestamp": message.edited_at.isoformat() if message.edited_at else None,
        "tts": message.tts,
        "mentions": [user.id for user in message.mentions],
        "attachments": [attachment.url for attachment in message.attachments],
        "embeds": [embed.to_dict() for embed in message.embeds],
        "reactions": [reaction.emoji for reaction in message.reactions],
        "pinned": message.pinned,
        "mention_everyone": message.mention_everyone,
        "flags": message.flags.value,
    }

    return message_dict

def detect_language(text):
    lang, _ = langid.classify(text)
    return lang

def translate_text(text, from_lang, to_lang):
    #这个地址会变化 this is temp adress
    url = "http://101.83.213.105:50118/translate"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    data = {
        "text": text,
        "from_lang": from_lang,
        "to_lang": to_lang,
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        print("Response:", response.text)  # 打印响应内容

        if response.status_code == 200:
            translated_text = response.json()["translated_text"]
            return translated_text
        else:
            print("Error:", response.status_code)
            return None
    except Exception as e:
        print("Error:", e)
        return None

def convert_json(input_json):
    # 检测消息的语言
    language_code = detect_language(input_json["content"])
    print(language_code)

    # 将 "zh-cn" 替换为 "zh"
    if language_code == "zh-cn":
        language_code = "zh"

    # 翻译消息内容
    if language_code == "zh":
        translated_content = input_json["content"]
    else:
        translated_content = translate_text(input_json["content"], language_code, "zh")
        print(input_json["content"])
        print(translated_content)

    output_json = {
        "channel_id": str(input_json["channel_id"]),
        "guild_id": str(input_json["guild_id"]),
        "message": translated_content,  # 使用翻译后的消息内容
        "message_id": str(input_json["id"]),
        "message_type": "guild",
        "post_type": "message",
        "self_id": str(input_json["bot_id"]),
        "self_tiny_id": str(input_json["bot_id"]),
        "sender": {
            "nickname": input_json["author"]["name"],
            "tiny_id": str(input_json["author"]["id"]),
            "user_id": str(input_json["author"]["id"]),
        },
        "sub_type": "channel",
        "time": int(input_json["timestamp"].timestamp()),
        "user_id": str(input_json["author"]["id"]),
        "avatar": input_json["author"]["avatar_url"],
        "lang": language_code,
    }
    
    return output_json
#请填入自己机器人的token your bot token
bot.run('')