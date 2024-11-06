import discord
import os
from discord.ext  import commands
from discord import app_commands
from dotenv import load_dotenv
import asyncio
from discord import ClientException
from yt_dlp import YoutubeDL
import sys
import io

sys.stdout=io.TextIOWrapper(sys.stdout.buffer, encoding = "utf-8")

load_dotenv()

intents = discord.Intents.all()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents, heartbeat_timeout=60)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

is_playing = False
is_looping_playlist = False

mqueue = []
YDL_OPTIONS = {"format":"m4a/bestaudio/best", "noplaylist": True}
FFMPEG_OPTIONS = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", 
                  "options": "-vn"}  

vc = None

def search_yt(item):
    try:
        with YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info("ytsearch:%s" % item, download = False)["entries"][0]
            return {"source": info["url"], "title": info["title"]}
    except Exception as e:
        print(f"Error in search_yt: {e}")
        return None

def play_next():
    global is_playing, vc, mqueue, is_looping_playlist

    if is_looping_playlist:
        mqueue.append(mqueue[0])
    if len(mqueue) > 0: 
        is_playing= True
        mqueue.pop(0)
        if len(mqueue) > 0:
            m_url = mqueue[0][0]["source"]   #call_me_daddy ;)
            if vc and vc.is_connected():
                vc.play(discord.FFmpegPCMAudio(m_url, **FFMPEG_OPTIONS), after = lambda e: play_next())
                asyncio.run_coroutine_threadsafe(send_now_playing_message(mqueue[0][0]["title"]), bot.loop)
            else:
                 is_playing = False
        else:
             is_playing = False 
    else:
        is_playing = False

async def send_now_playing_message(song_title):
    global vc, mqueue

    text_channel = mqueue[0][2]

    embed = discord.Embed(title= "Now Playing", description=f"{song_title}", color=discord.color.light_gray())
    await text_channel.send(embed=embed, delete_after=120)

async def play_music():
    global is_playing, vc, mqueue

    if len(mqueue) > 0:
        is_playing = True
        
        m_url = mqueue[0][0]['source']
        if vc == "" or not vc.is_connected() or vc is None:
            vc = await mqueue[0][1].connect()
        else:
            await vc.move_to(mqueue[0][1])

        print(mqueue)
        try:
            vc.play(discord.FFmpegPCMAudio(m_url, **FFMPEG_OPTIONS), after=lambda e: play_next())
        except ClientException as e:
            print(f"Ignoring exception: {e}")
            pass
    else:
         is_playing = False


@bot.tree.command(name='help', description='Display the list of available commands and their descriptions')
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title = "Available Commands", description = "Here are the commands you can use:", color=0x00ff00)

    for command in bot.tree.get_commands():
        embed.add_field(name=command.name, value=command.description, inline = False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='play', description= 'Add a song to the queue (Example: /play Faded)')
async def play(interaction: discord.Interaction, query: str):
    global vc, mqueue
    await interaction.response.send_message("Processing your request. . .")

    if interaction.user.voice is None:
        embed = discord.Embed(description = "Get in a voice channel first", color = discord.Color.red())
        await interaction.followup.send(embed=embed)
        return
    if vc is None or not vc.is_connected():
        vc = await interaction.user.voice.channel.connect()
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)
        embed = discord.Embed(description = "Moving over to your voice channel", color=discord.Color.blue())
        await interaction.followup.send(embed=embed)

    song = search_yt(query)
    if song is None:
        embed = discord.Embed(description = "I could'nt find your desired song", color=discord.Color.red())
        await interaction.followup.send(embed=embed)
        return
    mqueue.append([song, interaction.user.voice.channel, interaction.channel, interaction.user])

    if is_playing:
        author = interaction.user
        embed = discord.Embed(title="Queued", color=discord.Color.green())
        embed.add_field(name="Song", value=song['title'], inline=False)
        embed.add_field(name="By", value=author.mention, inline = False)
        await interaction.followup.send(embed=embed)
    else:
        author = interaction.user
        embed = discord.Embed(title="Now Playing", color=discord.Color.green())
        embed.add_field(name="Song", value=song['title'], inline = False)
        await interaction.followup.send(embed=embed)
        await play_music()


@bot.tree.command(name='queue', description = 'Shows the queue of songs')
async def queue(interaction: discord.Interaction):
    global mqueue

    if interaction.user.voice is None:
        embed = discord.Embed(description= "Get in a voice channel first", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return

    embed = discord.Embed(title="Queue", color=discord.Color.green())
    if len(mqueue) > 0:
        max_songs = min(25, len(mqueue))
        for i in range(max_songs):
            item = mqueue[i]
            requester_mention = item[3].mention if isinstance(item[3], discord.Member) else "Unknown"
            if i == 0 and interaction.guild.voice_client.is_playing():
                embed.add_field(name=f"{i + 1}. {item[0]['title']}", value="", inline=False)
            else:
                   embed.add_field(name=f"{i + 1}. {item[0]['title']}", value="", inline=False)
        if len(mqueue) > max_songs:
            footer_text = f"And {len(mqueue) - max_songs} more . . ."
            embed.set_footer(text=footer_text)
    else:
        embed.description = "Queue is empty"
    await interaction.response.send_message(embed=embed, delete_after=3600)


@bot.tree.command(name='skip', description= 'skips the current song')
async def skip(interaction: discord.Interaction):
    global vc, mqueue

    if interaction.user.voice is None:
        embed = discord.Embed(description="Get in a voice channel first", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    
    if not mqueue:
        embed = discord.Embed(description="The queue is empty", color=discord.Color.dark_red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    
    if vc and vc.is_playing():
        vc.stop()
        retval = mqueue[0][0]['title']
        embed = discord.Embed(title="Song skipped", description=f"{retval}", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, delete_after=120)


@bot.tree.command(name='remove', description='Removes a song from the queue (Example: /remove 3)')
async def remove(interaction: discord.Interaction, index: int):
    global vc, mqueue

    if len(mqueue) == 0:
        embed = discord.Embed(description="There is nothing to erase", color=discord.Colo.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    if index - 1 == 0:
        vc.stop()
        retval = mqueue[0][0]['title']
        embed = discord.Embed(title="Song removed", description=f"{retval}", color=discord.Color.dark_gray())
        await interaction.response.send_message(embed=embed)
    else:
        x = index - 1
        retval = mqueue[0][0]['title']
        embed = discord.Embed(title="Song Removed", description=f"{retval}", color=discord.Color.dark_grey())
        await interaction.response.send_message(embed=embed)


@bot.tree.command(name='jump', description='Jumps to a song in the queue(Example: /jump 3)')
async def jump(interaction: discord.Interaction, index: int):
    global vc, mqueue, is_looping_playlist

    if interaction.user.voice is None:
        embed = discord.Embed(description='Get in a voice channel first', color=discord.Color.red())
        await interaction.response.send_messages(embed=embed, delete_after=15)
        return
    
    if len(mqueue) == 0:
        embed = discord.Embed(description="The queue is empty", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    
    if index <= 1 or index > len(mqueue):
        embed = discord.Embed(description="Invalid index", color = discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    
    songs_to_move = mqueue[:index-1] if not is_looping_playlist else mqueue[:index-2]
    mqueue = mqueue[index-2:]
    mqueue.extend(songs_to_move)

    if vc.is_playing():
        vc.stop()


@bot.tree.command(name='loop', description='Loops the playlist (once to enable, twice to disable)')
async def playlist_loop(interaction: discord.Interaction):
    global is_looping_playlist

    is_looping_playlist = not is_looping_playlist

    embed = discord.Embed(description=f"{'loop **enabled**' if is_looping_playlist else 'loop **disabled**'}", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='leave', description='Leaves the voice channel')
async def leave(interaction: discord.Interaction):
    global vc, is_playing, mqueue, is_looping_playlist
    if interaction.user.voice is None:
        embed = discord.Embed(description="Get in a voice channel first ", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    
    if interaction.guild.voice_client is None:
        embed = discord.Embed(description='The bot is not connected to a voice channel', color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return 

    is_playing = False
    is_looping_playlist = False
    
    await interaction.guild.voice_client.disconnect()
    embed = discord.Embed(description= "disconnected", color=discord.Color.dark_grey())
    await interaction.response.send_message(embed=embed, delete_after=15)

    mqueue=[]
    vc = None


@bot.tree.command(name='pause', description='Pause the song')
async def pause(interaction: discord.Interaction):
    global vc, mqueue
    if interaction.user.voice is None:
        embed = discord.Embed(description="Get into a voice channel", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    
    if interaction.guild.voice_client.is_playing is None:
        embed = discord.Embed(description="The bot is not connected to the voice channel", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    
    if interaction.guild.voice_client.is_playing():
        embed = discord.Embed(description="Paused", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
        interaction.guild.voice_client.pause()
    else:
        embed = discord.Embed(description="There is no song playing to pause", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)


@bot.tree.command(name='resume', description='Resume the song')
async def resume(interaction: discord.Interaction):
    global vc, mqueue
    if interaction.user.voice is None:
        embed = discord.Embed(description="Get in a voice channel first", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    
    if interaction.guild.voice_client is None:
        embed = discord.Embed(description="The bot is not connected to a voice channel", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
        return
    
    if interaction.guild.voice_client.is_paused():
        embed = discord.Embed(description="Resumed", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
        interaction.guild.voice_client.resume()
    else:
        embed = discord.Embed(description="The song is not paused", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15) 


@bot.tree.command(name='nowplaying', description='Shows the song that is playing')
async def nowplaying(interaction: discord.Interaction):
    global vc, mqueue
    if interaction.user.voice is None:
        embed = discord.Embed(description="Get in a voice channel first", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=15)
    else:
        retval = mqueue[0][0]['title']
        embed = discord.Embed(title="Now Playing", description=f"{retval}", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, delete_after=120)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    await bot.change_presence(activity=discord.Game(name="status-name"), status=discord.Status.idle)
    await bot.tree.sync()

bot.run(DISCORD_TOKEN)      