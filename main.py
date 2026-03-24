import discord
from discord.ext import commands, tasks
import re
import json
import os
from datetime import datetime, timedelta
import asyncio
import aiohttp

# ---------- إعدادات البوت ----------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

# ---------- إعدادات الملفات ----------
SETTINGS_FILE = 'protection_settings.json'
LINE_SETTINGS_FILE = 'line_settings.json'
BAN_LOGS_FILE = 'ban_logs.json'
TIMEOUT_LOGS_FILE = 'timeout_logs.json'
WARN_LOGS_FILE = 'warn_logs.json'

def load_json(file):
    if os.path.exists(file):
        with open(file, 'r') as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=4)

protection_settings = load_json(SETTINGS_FILE)
line_settings = load_json(LINE_SETTINGS_FILE)
ban_logs = load_json(BAN_LOGS_FILE)
timeout_logs = load_json(TIMEOUT_LOGS_FILE)
warn_logs = load_json(WARN_LOGS_FILE)

spam_tracker = {}

if not os.path.exists('line_images'):
    os.makedirs('line_images')

# ---------- دوال مساعدة ----------
def parse_duration(duration_str):
    duration_str = duration_str.lower().strip()
    if duration_str.endswith('s'):
        return int(duration_str[:-1])
    elif duration_str.endswith('m'):
        return int(duration_str[:-1]) * 60
    elif duration_str.endswith('h'):
        return int(duration_str[:-1]) * 3600
    elif duration_str.endswith('d'):
        return int(duration_str[:-1]) * 86400
    elif duration_str.endswith('w'):
        return int(duration_str[:-1]) * 604800
    else:
        try:
            return int(duration_str)
        except:
            return None

def add_ban_log(guild_id, user, mod, reason):
    guild_id = str(guild_id)
    if guild_id not in ban_logs:
        ban_logs[guild_id] = []
    ban_logs[guild_id].append({
        "user_id": user.id,
        "user_name": str(user),
        "mod_id": mod.id,
        "mod_name": str(mod),
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    })
    save_json(BAN_LOGS_FILE, ban_logs)

def add_timeout_log(guild_id, user, mod, duration, reason):
    guild_id = str(guild_id)
    if guild_id not in timeout_logs:
        timeout_logs[guild_id] = []
    timeout_logs[guild_id].append({
        "user_id": user.id,
        "user_name": str(user),
        "mod_id": mod.id,
        "mod_name": str(mod),
        "duration": duration,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    })
    save_json(TIMEOUT_LOGS_FILE, timeout_logs)

def add_warn_log(guild_id, user, mod, reason):
    guild_id = str(guild_id)
    user_id = str(user.id)
    if guild_id not in warn_logs:
        warn_logs[guild_id] = {}
    if user_id not in warn_logs[guild_id]:
        warn_logs[guild_id][user_id] = []
    warn_logs[guild_id][user_id].append({
        "mod_id": mod.id,
        "mod_name": str(mod),
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    })
    save_json(WARN_LOGS_FILE, warn_logs)

def get_warn_count(guild_id, user_id):
    guild_id = str(guild_id)
    user_id = str(user_id)
    if guild_id in warn_logs and user_id in warn_logs[guild_id]:
        return len(warn_logs[guild_id][user_id])
    return 0

# ---------- أوامر الإدارة ----------
@bot.command(name='ban', aliases=['بنعالي', 'ختفو'])
@commands.has_permissions(ban_members=True)
async def ban_command(ctx, member: discord.Member = None, *, reason="لا يوجد سبب"):
    if member is None:
        embed = discord.Embed(title="خطأ", description="يرجى منشن العضو المراد حظره.\nمثال: `!ban @user سبب (اختياري)`", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    await member.ban(reason=reason)
    add_ban_log(ctx.guild.id, member, ctx.author, reason)
    embed = discord.Embed(title="تم الحظر", description=f"تم حظر {member.mention} من السيرفر", color=discord.Color.red())
    embed.add_field(name="من قبل", value=ctx.author.mention, inline=True)
    embed.add_field(name="السبب", value=reason, inline=True)
    await ctx.send(embed=embed)

@bot.command(name='kick', aliases=['شقلب'])
@commands.has_permissions(kick_members=True)
async def kick_command(ctx, member: discord.Member = None, *, reason="لا يوجد سبب"):
    if member is None:
        embed = discord.Embed(title="خطأ", description="يرجى منشن العضو المراد طرده.\nمثال: `!kick @user سبب (اختياري)`", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    await member.kick(reason=reason)
    embed = discord.Embed(title="تم الطرد", description=f"تم طرد {member.mention} من السيرفر", color=discord.Color.orange())
    embed.add_field(name="من قبل", value=ctx.author.mention, inline=True)
    embed.add_field(name="السبب", value=reason, inline=True)
    await ctx.send(embed=embed)

@bot.command(name='timeout', aliases=['اص', 'انطم', 'اخرس', 'تايم'])
@commands.has_permissions(moderate_members=True)
async def timeout_command(ctx, member: discord.Member = None, duration: str = None, *, reason="لا يوجد سبب"):
    if member is None or duration is None:
        embed = discord.Embed(title="خطأ", description="يرجى تحديد العضو والمدة.\nمثال: `!timeout @user 5m سبب (اختياري)`", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    seconds = parse_duration(duration)
    if seconds is None:
        await ctx.send("مدة غير صالحة. استخدم مثلاً: 5m, 1h, 7d, 1w")
        return
    if seconds > 2419200:
        await ctx.send("المدة لا يمكن أن تتجاوز 28 يومًا (4 أسابيع)")
        return
    until = discord.utils.utcnow() + timedelta(seconds=seconds)
    await member.timeout(until, reason=reason)
    add_timeout_log(ctx.guild.id, member, ctx.author, duration, reason)
    embed = discord.Embed(title="تم التقييد", description=f"تم تقييد {member.mention} لمدة {duration}", color=discord.Color.gold())
    embed.add_field(name="من قبل", value=ctx.author.mention, inline=True)
    embed.add_field(name="السبب", value=reason, inline=True)
    await ctx.send(embed=embed)

@bot.command(name='lock', aliases=['قفل', 'ق'])
@commands.has_permissions(manage_channels=True)
async def lock_command(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    embed = discord.Embed(title="قفل الروم", description="تم قفل الروم بنجاح.", color=discord.Color.dark_red())
    await ctx.send(embed=embed)

@bot.command(name='unlock', aliases=['فتح', 'ف'])
@commands.has_permissions(manage_channels=True)
async def unlock_command(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    embed = discord.Embed(title="فتح الروم", description="تم فتح الروم بنجاح.", color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name='slowmode', aliases=['بطء'])
@commands.has_permissions(manage_channels=True)
async def slowmode_command(ctx, seconds: int = None):
    if seconds is None:
        embed = discord.Embed(title="خطأ", description="يرجى تحديد عدد الثواني.\nمثال: `!slowmode 5`", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    await ctx.channel.edit(slowmode_delay=seconds)
    embed = discord.Embed(title="وضع البطء", description=f"تم تعيين وضع البطء إلى {seconds} ثانية.", color=discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command(name='unslowmode', aliases=['الغاء_بطء'])
@commands.has_permissions(manage_channels=True)
async def unslowmode_command(ctx):
    await ctx.channel.edit(slowmode_delay=0)
    embed = discord.Embed(title="وضع البطء", description="تم إلغاء وضع البطء.", color=discord.Color.green())
    await ctx.send(embed=embed)

# ---------- نظام الخط ----------
@bot.command(name='line', aliases=['خط'])
@commands.has_permissions(manage_channels=True)
async def line_command(ctx):
    if not ctx.message.attachments:
        embed = discord.Embed(title="خطأ", description="يرجى إرفاق صورة مع الأمر لتعيينها كنظام الخط.\nمثال: `!line` مع رفع صورة", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    attachment = ctx.message.attachments[0]
    if not attachment.content_type.startswith('image/'):
        await ctx.send("الملف المرفق ليس صورة.")
        return
    guild_id = str(ctx.guild.id)
    channel_id = str(ctx.channel.id)
    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as resp:
            if resp.status == 200:
                img_data = await resp.read()
                file_path = f"line_images/{guild_id}_{channel_id}.png"
                with open(file_path, 'wb') as f:
                    f.write(img_data)
    if guild_id not in line_settings:
        line_settings[guild_id] = {}
    line_settings[guild_id][channel_id] = {"enabled": True, "image_path": file_path}
    save_json(LINE_SETTINGS_FILE, line_settings)
    embed = discord.Embed(title="نظام الخط", description="تم تفعيل نظام الخط في هذا الروم. سيتم إرسال الصورة بعد كل رسالة.", color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command(name='unline', aliases=['الغاء_خط'])
@commands.has_permissions(manage_channels=True)
async def unline_command(ctx):
    guild_id = str(ctx.guild.id)
    channel_id = str(ctx.channel.id)
    if guild_id not in line_settings or channel_id not in line_settings[guild_id]:
        await ctx.send("نظام الخط غير مفعل في هذا الروم.")
        return
    del line_settings[guild_id][channel_id]
    if not line_settings[guild_id]:
        del line_settings[guild_id]
    save_json(LINE_SETTINGS_FILE, line_settings)
    file_path = f"line_images/{guild_id}_{channel_id}.png"
    if os.path.exists(file_path):
        os.remove(file_path)
    embed = discord.Embed(title="نظام الخط", description="تم إيقاف نظام الخط في هذا الروم.", color=discord.Color.red())
    await ctx.send(embed=embed)

# ---------- أوامر الحماية ----------
@bot.command(name='Anti_Links', aliases=['مضاد_روابط'])
@commands.has_permissions(administrator=True)
async def anti_links_toggle(ctx):
    guild_id = str(ctx.guild.id)
    current = protection_settings.get(guild_id, {}).get('anti_links', False)
    protection_settings.setdefault(guild_id, {})['anti_links'] = not current
    status = "مفعل" if not current else "معطل"
    embed = discord.Embed(title="مضاد الروابط", description=f"تم {status} مضاد الروابط.", color=discord.Color.blue())
    await ctx.send(embed=embed)
    save_json(SETTINGS_FILE, protection_settings)

@bot.command(name='UnAnti_Links', aliases=['unمضاد_روابط', 'unanti_links'])
@commands.has_permissions(administrator=True)
async def unanti_links(ctx):
    guild_id = str(ctx.guild.id)
    protection_settings.setdefault(guild_id, {})['anti_links'] = False
    embed = discord.Embed(title="مضاد الروابط", description="تم إيقاف مضاد الروابط.", color=discord.Color.red())
    await ctx.send(embed=embed)
    save_json(SETTINGS_FILE, protection_settings)

@bot.command(name='Anti_invite', aliases=['مضاد_دعوه'])
@commands.has_permissions(administrator=True)
async def anti_invite_toggle(ctx):
    guild_id = str(ctx.guild.id)
    current = protection_settings.get(guild_id, {}).get('anti_invite', False)
    protection_settings.setdefault(guild_id, {})['anti_invite'] = not current
    status = "مفعل" if not current else "معطل"
    embed = discord.Embed(title="مضاد الدعوات", description=f"تم {status} مضاد الدعوات.", color=discord.Color.blue())
    await ctx.send(embed=embed)
    save_json(SETTINGS_FILE, protection_settings)

@bot.command(name='UnAnti_invite', aliases=['unمضاد_دعوه', 'unanti_invite'])
@commands.has_permissions(administrator=True)
async def unanti_invite(ctx):
    guild_id = str(ctx.guild.id)
    protection_settings.setdefault(guild_id, {})['anti_invite'] = False
    embed = discord.Embed(title="مضاد الدعوات", description="تم إيقاف مضاد الدعوات.", color=discord.Color.red())
    await ctx.send(embed=embed)
    save_json(SETTINGS_FILE, protection_settings)

@bot.command(name='Anti_Spam', aliases=['مضاد_سبام'])
@commands.has_permissions(administrator=True)
async def anti_spam_toggle(ctx):
    guild_id = str(ctx.guild.id)
    current = protection_settings.get(guild_id, {}).get('anti_spam', False)
    protection_settings.setdefault(guild_id, {})['anti_spam'] = not current
    status = "مفعل" if not current else "معطل"
    embed = discord.Embed(title="مضاد السبام", description=f"تم {status} مضاد السبام.", color=discord.Color.blue())
    await ctx.send(embed=embed)
    save_json(SETTINGS_FILE, protection_settings)

@bot.command(name='UnAnti_Spam', aliases=['unمضاد_سبام', 'unanti_spam'])
@commands.has_permissions(administrator=True)
async def unanti_spam(ctx):
    guild_id = str(ctx.guild.id)
    protection_settings.setdefault(guild_id, {})['anti_spam'] = False
    embed = discord.Embed(title="مضاد السبام", description="تم إيقاف مضاد السبام.", color=discord.Color.red())
    await ctx.send(embed=embed)
    save_json(SETTINGS_FILE, protection_settings)

# ---------- أمر المسح ----------
@bot.command(name='مسح', aliases=['م'])
@commands.has_permissions(manage_messages=True)
async def purge_command(ctx, member: discord.Member = None, amount: int = None):
    if member is not None and amount is None:
        embed = discord.Embed(title="خطأ", description="يرجى تحديد عدد الرسائل المراد حذفها (1-500).\nمثال: `!مسح @user 10`", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    elif member is None and amount is None:
        embed = discord.Embed(title="خطأ", description="يرجى تحديد عدد الرسائل المراد حذفها (1-500).\nمثال: `!مسح 10` أو `!مسح @user 10`", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    elif member is None:
        if amount < 1 or amount > 500:
            await ctx.send("العدد يجب أن يكون بين 1 و 500.")
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        embed = discord.Embed(title="تم الحذف", description=f"تم حذف {len(deleted)-1} رسالة.", color=discord.Color.green())
        await ctx.send(embed=embed, delete_after=5)
    else:
        if amount < 1 or amount > 500:
            await ctx.send("العدد يجب أن يكون بين 1 و 500.")
            return
        def check(m):
            return m.author == member and not m.pinned
        deleted = 0
        async for message in ctx.channel.history(limit=amount + 50):
            if deleted >= amount:
                break
            if check(message):
                await message.delete()
                deleted += 1
        embed = discord.Embed(title="تم الحذف", description=f"تم حذف {deleted} رسالة من {member.mention}.", color=discord.Color.green())
        await ctx.send(embed=embed, delete_after=5)
    try:
        await ctx.message.delete()
    except:
        pass

# ---------- نظام التحذيرات ----------
@bot.command(name='warn', aliases=['تحذير'])
@commands.has_permissions(kick_members=True)
async def warn_command(ctx, member: discord.Member = None, *, reason="لا يوجد سبب"):
    if member is None:
        embed = discord.Embed(title="خطأ", description="يرجى منشن العضو المراد تحذيره.\nمثال: `!warn @user سبب (اختياري)`", color=discord.Color.red())
        await ctx.send(embed=embed)
        return
    add_warn_log(ctx.guild.id, member, ctx.author, reason)
    warn_count = get_warn_count(ctx.guild.id, member.id)
    embed = discord.Embed(title="تحذير", description=f"تم تحذير {member.mention}", color=discord.Color.orange())
    embed.add_field(name="من قبل", value=ctx.author.mention, inline=True)
    embed.add_field(name="السبب", value=reason, inline=True)
    embed.add_field(name="عدد التحذيرات", value=str(warn_count), inline=True)
    await ctx.send(embed=embed)

# ---------- سجلات الحظر والتقييد والتحذيرات ----------
class BanLogsView(discord.ui.View):
    def __init__(self, guild_id, page=0):
        super().__init__(timeout=60)
        self.guild_id = str(guild_id)
        self.page = page
        self.logs = ban_logs.get(self.guild_id, [])
        self.max_page = (len(self.logs) - 1) // 10 if self.logs else 0
    def get_embed(self):
        if not self.logs:
            embed = discord.Embed(title="سجلات الحظر", description="لا توجد سجلات حظر حتى الآن.", color=discord.Color.dark_gray())
            return embed
        start = self.page * 10
        end = start + 10
        page_logs = self.logs[start:end]
        embed = discord.Embed(title="سجلات الحظر", color=discord.Color.dark_red())
        embed.set_footer(text=f"الصفحة {self.page+1} من {self.max_page+1}")
        for log in page_logs:
            timestamp = datetime.fromisoformat(log['timestamp']).strftime("%Y-%m-%d %H:%M")
            embed.add_field(name=f"{log['user_name']}", value=f"بواسطة: {log['mod_name']}\nالسبب: {log['reason']}\nالتاريخ: {timestamp}", inline=False)
        return embed
    @discord.ui.button(label="السابق", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.send_message("أنت في الصفحة الأولى.", ephemeral=True)
    @discord.ui.button(label="التالي", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.send_message("هذه آخر صفحة.", ephemeral=True)

@bot.command(name='BanLogs', aliases=['لوق_الباند'])
@commands.has_permissions(administrator=True)
async def ban_logs_command(ctx):
    view = BanLogsView(ctx.guild.id)
    embed = view.get_embed()
    await ctx.send(embed=embed, view=view)

class TimeoutLogsView(discord.ui.View):
    def __init__(self, guild_id, page=0):
        super().__init__(timeout=60)
        self.guild_id = str(guild_id)
        self.page = page
        self.logs = timeout_logs.get(self.guild_id, [])
        self.max_page = (len(self.logs) - 1) // 10 if self.logs else 0
    def get_embed(self):
        if not self.logs:
            embed = discord.Embed(title="سجلات التقييد", description="لا توجد سجلات تقييد حتى الآن.", color=discord.Color.dark_gray())
            return embed
        start = self.page * 10
        end = start + 10
        page_logs = self.logs[start:end]
        embed = discord.Embed(title="سجلات التقييد", color=discord.Color.dark_gold())
        embed.set_footer(text=f"الصفحة {self.page+1} من {self.max_page+1}")
        for log in page_logs:
            timestamp = datetime.fromisoformat(log['timestamp']).strftime("%Y-%m-%d %H:%M")
            embed.add_field(name=f"{log['user_name']}", value=f"بواسطة: {log['mod_name']}\nالمدة: {log['duration']}\nالسبب: {log['reason']}\nالتاريخ: {timestamp}", inline=False)
        return embed
    @discord.ui.button(label="السابق", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.send_message("أنت في الصفحة الأولى.", ephemeral=True)
    @discord.ui.button(label="التالي", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.send_message("هذه آخر صفحة.", ephemeral=True)

@bot.command(name='TimeoutLogs', aliases=['لوق_تايم'])
@commands.has_permissions(administrator=True)
async def timeout_logs_command(ctx):
    view = TimeoutLogsView(ctx.guild.id)
    embed = view.get_embed()
    await ctx.send(embed=embed, view=view)

class WarnLogsView(discord.ui.View):
    def __init__(self, guild_id, page=0):
        super().__init__(timeout=60)
        self.guild_id = str(guild_id)
        self.page = page
        self._build_warns()

    def _build_warns(self):
        self.all_warns = []
        if self.guild_id in warn_logs:
            for user_id, warns in warn_logs[self.guild_id].items():
                user_name = f"مستخدم {user_id}"
                for idx, warn in enumerate(warns, start=1):
                    self.all_warns.append({
                        "user_id": int(user_id),
                        "user_name": warn.get("user_name", user_name),
                        "mod_name": warn["mod_name"],
                        "reason": warn["reason"],
                        "timestamp": warn["timestamp"],
                        "warn_number": idx
                    })
        self.all_warns.sort(key=lambda x: x["timestamp"], reverse=True)
        self.max_page = (len(self.all_warns) - 1) // 10 if self.all_warns else 0

    def get_embed(self):
        self._build_warns()
        if not self.all_warns:
            embed = discord.Embed(title="سجلات التحذيرات", description="لا توجد سجلات تحذيرات حتى الآن.", color=discord.Color.dark_gray())
            return embed
        start = self.page * 10
        end = start + 10
        page_warns = self.all_warns[start:end]
        embed = discord.Embed(title="سجلات التحذيرات", color=discord.Color.dark_orange())
        embed.set_footer(text=f"الصفحة {self.page+1} من {self.max_page+1}")
        for w in page_warns:
            timestamp = datetime.fromisoformat(w['timestamp']).strftime("%Y-%m-%d %H:%M")
            embed.add_field(
                name=f"{w['user_name']} - التحذير #{w['warn_number']}",
                value=f"بواسطة: {w['mod_name']}\nالسبب: {w['reason']}\nالتاريخ: {timestamp}",
                inline=False
            )
        return embed

    @discord.ui.button(label="السابق", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.send_message("أنت في الصفحة الأولى.", ephemeral=True)

    @discord.ui.button(label="التالي", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._build_warns()
        if self.page < self.max_page:
            self.page += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.send_message("هذه آخر صفحة.", ephemeral=True)

@bot.command(name='WarnLogs', aliases=['لوق_تحذير'])
@commands.has_permissions(administrator=True)
async def warn_logs_command(ctx):
    view = WarnLogsView(ctx.guild.id)
    embed = view.get_embed()
    await ctx.send(embed=embed, view=view)

# ---------- أمر say ----------
@bot.command(name='say')
async def say_command(ctx, *, message: str):
    await ctx.message.delete()
    await ctx.send(message)

# ---------- أمر help ----------
@bot.command(name='help', aliases=['مساعدة'])
async def help_command(ctx, command_name: str = None):
    if command_name:
        command = bot.get_command(command_name)
        if not command:
            await ctx.send("الأمر غير موجود.")
            return
        embed = discord.Embed(title=f"شرح الأمر: {command.name}", description=command.help or "لا يوجد شرح مفصل.", color=discord.Color.gold())
        aliases = command.aliases
        if aliases:
            embed.add_field(name="الاختصارات", value=", ".join(aliases), inline=False)
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(
        title="🛡️ بوت الحماية والإدارة",
        description=("مرحبًا بك في بوت حماية وإدارة السيرفر.\nاستخدم الأوامر التالية لإدارة سيرفرك بكل سهولة.\n**البادئة:** `!`"),
        color=discord.Color.blurple()
    )
    if bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)

    embed.add_field(
        name="⚙️ أوامر الإدارة",
        value=(
            "`!ban / بنعالي / ختفو`\nحظر عضو\n\n"
            "`!kick / شقلب`\nطرد عضو\n\n"
            "`!timeout / اص / انطم / اخرس / تايم`\nتقييد عضو\n\n"
            "`!lock / قفل / ق`\nقفل الروم\n\n"
            "`!unlock / فتح / ف`\nفتح الروم\n\n"
            "`!slowmode / بطء`\nوضع البطء\n\n"
            "`!unslowmode / الغاء_بطء`\nإلغاء وضع البطء\n\n"
            "`!مسح / م`\nحذف رسائل (مع منشن أو بدون)\n\n"
            "`!warn / تحذير`\nإعطاء تحذير لعضو"
        ),
        inline=False
    )

    embed.add_field(
        name="✏️ نظام الخط",
        value=(
            "`!line / خط`\nتفعيل نظام الخط (أرسل مع صورة)\n\n"
            "`!unline / الغاء_خط`\nإيقاف نظام الخط"
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ أوامر الحماية",
        value=(
            "`!Anti_Links / مضاد_روابط`\nتفعيل/تعطيل منع الروابط\n\n"
            "`!UnAnti_Links / unمضاد_روابط`\nإيقاف منع الروابط\n\n"
            "`!Anti_invite / مضاد_دعوه`\nتفعيل/تعطيل منع الدعوات\n\n"
            "`!UnAnti_invite / unمضاد_دعوه`\nإيقاف منع الدعوات\n\n"
            "`!Anti_Spam / مضاد_سبام`\nتفعيل/تعطيل منع السبام\n\n"
            "`!UnAnti_Spam / unمضاد_سبام`\nإيقاف منع السبام"
        ),
        inline=False
    )

    embed.add_field(
        name="📜 سجلات الحظر والتقييد والتحذيرات",
        value=(
            "`!BanLogs / لوق_الباند`\nعرض سجلات الحظر\n\n"
            "`!TimeoutLogs / لوق_تايم`\nعرض سجلات التقييد\n\n"
            "`!WarnLogs / لوق_تحذير`\nعرض سجلات التحذيرات"
        ),
        inline=False
    )

    embed.add_field(
        name="💬 أوامر أخرى",
        value=(
            "`!say [النص]`\nيرسل البوت النص ويحذف رسالتك\n\n"
            "`!help [الأمر]`\nشرح مفصل لأمر معين"
        ),
        inline=False
    )

    embed.set_footer(text="جميع الأوامر تحتاج للصلاحيات المناسبة | البوت بحماية سيرفرك 24/7")
    await ctx.send(embed=embed)

# ---------- أحداث الحماية ونظام الخط ----------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    guild = message.guild
    if not guild:
        return
    guild_id = str(guild.id)
    channel_id = str(message.channel.id)

    # نظام الخط
    if guild_id in line_settings and channel_id in line_settings[guild_id]:
        line_data = line_settings[guild_id][channel_id]
        if line_data.get("enabled", False) and os.path.exists(line_data["image_path"]):
            try:
                with open(line_data["image_path"], 'rb') as f:
                    file = discord.File(f, filename="line.png")
                    await message.channel.send(file=file)
            except Exception as e:
                print(f"خطأ في إرسال صورة الخط: {e}")

    # إعدادات الحماية
    settings = protection_settings.get(guild_id, {})
    # مضاد الروابط
    if settings.get('anti_links', False):
        if not message.author.guild_permissions.administrator:
            link_pattern = re.compile(r'(https?://|www\.)\S+', re.IGNORECASE)
            if link_pattern.search(message.content):
                await message.delete()
                try:
                    await message.author.timeout(timedelta(minutes=10), reason="إرسال رابط (مضاد الروابط)")
                    await message.channel.send(f"{message.author.mention} تم منحك تايم أوت 10 دقائق بسبب إرسال رابط.", delete_after=5)
                except:
                    pass
                return
    # مضاد الدعوات
    if settings.get('anti_invite', False):
        if not message.author.guild_permissions.administrator:
            invite_pattern = re.compile(r'(discord\.gg|discord\.com/invite)/\S+', re.IGNORECASE)
            if invite_pattern.search(message.content):
                await message.delete()
                try:
                    await message.author.timeout(timedelta(minutes=25), reason="إرسال دعوة ديسكورد (مضاد الدعوات)")
                    await message.channel.send(f"{message.author.mention} تم منحك تايم أوت 25 دقيقة بسبب إرسال دعوة.", delete_after=5)
                except:
                    pass
                return
    # مضاد السبام
    if settings.get('anti_spam', False):
        if not message.author.guild_permissions.administrator:
            if guild_id not in spam_tracker:
                spam_tracker[guild_id] = {}
            if message.channel.id not in spam_tracker[guild_id]:
                spam_tracker[guild_id][message.channel.id] = {}
            user_tracker = spam_tracker[guild_id][message.channel.id].setdefault(message.author.id, [])
            now = datetime.utcnow()
            user_tracker.append(now)
            user_tracker[:] = [t for t in user_tracker if (now - t).total_seconds() < 0.5]
            if len(user_tracker) >= 4:
                await message.delete()
                try:
                    await message.author.timeout(timedelta(minutes=2), reason="إرسال سبام (مضاد السبام)")
                    await message.channel.send(f"{message.author.mention} تم منحك تايم أوت دقيقتين بسبب السبام.", delete_after=5)
                except:
                    pass
                spam_tracker[guild_id][message.channel.id][message.author.id] = []
                return
    await bot.process_commands(message)

# ---------- تنظيف spam_tracker ----------
@tasks.loop(minutes=10)
async def clean_spam_tracker():
    for guild_id in list(spam_tracker.keys()):
        for channel_id in list(spam_tracker[guild_id].keys()):
            for user_id in list(spam_tracker[guild_id][channel_id].keys()):
                if not spam_tracker[guild_id][channel_id][user_id]:
                    del spam_tracker[guild_id][channel_id][user_id]
            if not spam_tracker[guild_id][channel_id]:
                del spam_tracker[guild_id][channel_id]
        if not spam_tracker[guild_id]:
            del spam_tracker[guild_id]

@clean_spam_tracker.before_loop
async def before_clean():
    await bot.wait_until_ready()

# ---------- حدث الجاهزية ----------
@bot.event
async def on_ready():
    print(f'✅ البوت {bot.user} يعمل الآن!')
    await bot.change_presence(activity=discord.Game(name="تفعيل نظام الخط: أرسل مع صورة | !help"))
    clean_spam_tracker.start()

# ---------- تشغيل البوت ----------
if __name__ == "__main__":
    TOKEN = os.getenv('BOT_TOKEN')
    if not TOKEN:
        print("❌ لم يتم العثور على التوكن. تأكد من تعيين BOT_TOKEN في متغيرات البيئة.")
    else:
        bot.run(TOKEN)
