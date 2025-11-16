import os
import logging
import asyncio
import threading
from queue import Queue
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from PIL import Image
import subprocess
import zipfile
import tempfile
from concurrent.futures import ThreadPoolExecutor
import traceback
import time
import shutil

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler('bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

API_ID = 13216322
API_HASH = "15e5e632a8a0e52251ac8c3ccbe462c7"
BOT_TOKEN = "7335432995:AAG3phsMDhohsuStZY7m1PyoeLhNY73KYpA"
ADMIN_ID = 5993556795

app = Client("file_compression_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

task_queue = Queue()
executor = ThreadPoolExecutor(max_workers=4)
user_files = {}
active_tasks = {}
temp_directories = []

MAX_CONCURRENT_TASKS = 3
current_tasks = 0

IMAGE_FORMATS = ['jpg', 'png', 'webp', 'bmp', 'gif', 'ico', 'tiff']
VIDEO_FORMATS = ['mp4', 'avi', 'mkv', 'mov', 'flv', 'webm', 'wmv', '3gp']
AUDIO_FORMATS = ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a', 'wma']


class SimpleProgress:
    """Simple progress tracker that actually works"""
    def __init__(self, message, operation="Processing"):
        self.message = message
        self.operation = operation
        self.start_time = time.time()
        self.last_update = 0
        self.last_percentage = 0
        
    async def __call__(self, current, total):
        """Called by Pyrogram during download/upload"""
        current_time = time.time()
        
        # Don't update too frequently
        if current_time - self.last_update < 1.5:
            return
            
        percentage = (current / total) * 100 if total > 0 else 0
        
        # Skip if percentage didn't change much
        if abs(percentage - self.last_percentage) < 3:
            return
            
        self.last_update = current_time
        self.last_percentage = percentage
        
        elapsed = current_time - self.start_time
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0
        
        bar_length = 20
        filled = int(bar_length * percentage / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        text = f"""**{self.operation}**

[{bar}] {percentage:.1f}%

📊 **Progress:** {self._size(current)} / {self._size(total)}
⚡ **Speed:** {self._size(speed)}/s
⏱️ **ETA:** {self._time(eta)}
⏰ **Elapsed:** {self._time(elapsed)}"""
        
        try:
            await self.message.edit_text(text)
        except:
            pass
    
    @staticmethod
    def _size(b):
        for u in ['B', 'KB', 'MB', 'GB']:
            if b < 1024:
                return f"{b:.2f} {u}"
            b /= 1024
        return f"{b:.2f} TB"
    
    @staticmethod
    def _time(s):
        if s < 60:
            return f"{int(s)}s"
        elif s < 3600:
            return f"{int(s/60)}m {int(s%60)}s"
        return f"{int(s/3600)}h {int((s%3600)/60)}m"


class ProcessProgress:
    """Progress for processing operations"""
    def __init__(self, message, operation="Processing"):
        self.message = message
        self.operation = operation
        self.start_time = time.time()
        self.last_update = 0
        
    async def update(self, current, total=100):
        current_time = time.time()
        
        if current_time - self.last_update < 1:
            return
            
        self.last_update = current_time
        percentage = min((current / total) * 100, 100)
        elapsed = current_time - self.start_time
        
        if percentage > 0:
            eta = (elapsed / percentage) * (100 - percentage)
        else:
            eta = 0
        
        bar_length = 20
        filled = int(bar_length * percentage / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        text = f"""**{self.operation}**

[{bar}] {percentage:.1f}%

⏰ **Elapsed:** {self._time(elapsed)}
⏱️ **ETA:** {self._time(eta)}"""
        
        try:
            await self.message.edit_text(text)
        except:
            pass
    
    @staticmethod
    def _time(s):
        if s < 60:
            return f"{int(s)}s"
        return f"{int(s/60)}m {int(s%60)}s"


async def compress_image(input_path, output_path, quality=20, progress=None):
    try:
        if progress:
            await progress.update(0, 100)
        
        with Image.open(input_path) as img:
            if progress:
                await progress.update(30, 100)
            
            if img.mode in ('RGBA', 'LA'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = bg
            elif img.mode == 'P':
                img = img.convert('RGB')
            
            if progress:
                await progress.update(60, 100)
            
            max_size = 1920
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = tuple(int(dim * ratio) for dim in img.size)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            if output_path.lower().endswith(('.jpg', '.jpeg')):
                img.save(output_path, 'JPEG', optimize=True, quality=quality, progressive=True)
            elif output_path.lower().endswith('.webp'):
                img.save(output_path, 'WEBP', quality=quality, method=6)
            else:
                img.save(output_path, optimize=True, quality=quality)
            
            if progress:
                await progress.update(100, 100)
        return True
    except Exception as e:
        logger.error(f"Image compression error: {e}")
        return False


async def compress_video(input_path, output_path, crf=32, preset='faster', progress=None):
    try:
        duration_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                      '-of', 'default=noprint_wrappers=1:nokey=1', input_path]
        result = subprocess.run(duration_cmd, capture_output=True, text=True)
        try:
            duration = float(result.stdout.strip())
        except:
            duration = 0
        
        cmd = ['ffmpeg', '-i', input_path, '-c:v', 'libx264', '-crf', str(crf), '-preset', preset,
               '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-c:a', 'aac', '-b:a', '64k',
               '-ac', '1', '-movflags', '+faststart', '-progress', 'pipe:1', '-y', output_path]
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                 universal_newlines=True)
        
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            if 'out_time_ms' in line and duration > 0 and progress:
                try:
                    time_ms = int(line.split('=')[1]) / 1000000
                    prog = (time_ms / duration) * 100
                    await progress.update(min(prog, 99), 100)
                except:
                    pass
        
        process.wait()
        
        if progress:
            await progress.update(100, 100)
        
        return process.returncode == 0
    except Exception as e:
        logger.error(f"Video compression error: {e}")
        return False


async def notify_admin(error_message, user_id=None, tb=None):
    try:
        text = f"""🚨 **Error Alert**

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👤 User: {user_id or 'Unknown'}
❌ Error: {error_message}

```{tb or 'No traceback'}```"""
        await app.send_message(ADMIN_ID, text)
    except:
        pass


class TaskQueue:
    @staticmethod
    async def add_task(task_func, *args, **kwargs):
        global current_tasks
        
        user_id = args[2] if len(args) > 2 else None
        
        if current_tasks >= MAX_CONCURRENT_TASKS:
            position = task_queue.qsize() + 1
            message = args[1] if len(args) > 1 else None
            if message:
                await message.edit_text(
                    f"⏳ **Queued**\n\nPosition: #{position}\n"
                    f"Active: {current_tasks}/{MAX_CONCURRENT_TASKS}"
                )
        
        task_queue.put((task_func, args, kwargs, user_id))
        asyncio.create_task(TaskQueue.process_queue())
    
    @staticmethod
    async def process_queue():
        global current_tasks
        
        while not task_queue.empty() and current_tasks < MAX_CONCURRENT_TASKS:
            if task_queue.empty():
                break
            
            task_func, args, kwargs, user_id = task_queue.get()
            current_tasks += 1
            active_tasks[user_id] = datetime.now()
            
            try:
                await task_func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Task error: {e}")
                await notify_admin(str(e), user_id, traceback.format_exc())
            finally:
                current_tasks -= 1
                if user_id in active_tasks:
                    del active_tasks[user_id]
                task_queue.task_done()


async def process_compression(client, message, user_id, file_type, level):
    temp_dir = None
    try:
        if user_id not in user_files:
            await message.edit_text("❌ File not found!")
            return
        
        file_info = user_files[user_id]
        file_id = file_info['file_id']
        original_msg = file_info['message']
        
        settings = {
            'max': {'image_quality': 15, 'video_crf': 36},
            'high': {'image_quality': 25, 'video_crf': 32},
            'med': {'image_quality': 40, 'video_crf': 28},
            'low': {'image_quality': 60, 'video_crf': 23}
        }
        setting = settings.get(level, settings['high'])
        
        temp_dir = tempfile.mkdtemp()
        temp_directories.append(temp_dir)
        
        # Download
        status_msg = await message.edit_text("📥 **Downloading...**")
        progress = SimpleProgress(status_msg, "📥 Downloading")
        
        try:
            file_path = await client.download_media(file_id, 
                file_name=os.path.join(temp_dir, "input"), progress=progress)
        except Exception as e:
            await status_msg.edit_text(f"❌ Download failed: {str(e)}")
            return
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ Download failed!")
            return
        
        file_size = os.path.getsize(file_path)
        
        # Compress
        await status_msg.edit_text(f"🔄 **Compressing ({level.upper()})...**")
        proc_progress = ProcessProgress(status_msg, f"🔄 Compressing ({level.upper()})")
        
        success = False
        output_path = None
        
        if file_type == 'image':
            output_path = os.path.join(temp_dir, "compressed.jpg")
            success = await compress_image(file_path, output_path, 
                setting['image_quality'], proc_progress)
        
        elif file_type == 'video':
            output_path = os.path.join(temp_dir, "compressed.mp4")
            success = await compress_video(file_path, output_path, 
                setting['video_crf'], 'faster', proc_progress)
        
        if success and os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            
            if output_size < file_size:
                reduction = ((file_size - output_size) / file_size) * 100
                saved = (file_size - output_size) / (1024 * 1024)
                
                await status_msg.edit_text("📤 **Uploading...**")
                upload_progress = SimpleProgress(status_msg, "📤 Uploading")
                
                caption = f"""✅ **Done!**

📊 Level: {level.upper()}
📦 Original: {file_size / (1024*1024):.2f} MB
🗜️ Compressed: {output_size / (1024*1024):.2f} MB
📉 Reduced: {reduction:.1f}%
💾 Saved: {saved:.2f} MB"""
                
                await original_msg.reply_document(output_path, caption=caption,
                    progress=upload_progress)
                await status_msg.delete()
            else:
                await status_msg.edit_text("⚠️ File already optimized!")
        else:
            await status_msg.edit_text("❌ Compression failed!")
        
        # Cleanup
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            temp_directories.remove(temp_dir)
        
        if user_id in user_files:
            del user_files[user_id]
    
    except Exception as e:
        logger.error(f"Error: {e}")
        try:
            await message.edit_text("❌ Error occurred!")
        except:
            pass
        await notify_admin(str(e), user_id, traceback.format_exc())
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text("""🤖 **File Compression Bot**

Send me any file to compress or convert!

Supported:
📸 Images • 🎥 Videos • 🎵 Audio • 📄 PDF

Use /help for more info""")


@app.on_message(filters.photo)
async def handle_photo(client, message: Message):
    user_id = message.from_user.id
    user_files[user_id] = {'type': 'image', 'message': message, 
        'file_id': message.photo.file_id}
    
    keyboard = [[
        InlineKeyboardButton("🗜️ Compress", callback_data="compress_image")
    ], [
        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    ]]
    
    await message.reply_text("📸 **Image received!**\n\nWhat to do?",
        reply_markup=InlineKeyboardMarkup(keyboard))


@app.on_message(filters.video)
async def handle_video(client, message: Message):
    user_id = message.from_user.id
    
    if message.video.file_size > 2000 * 1024 * 1024:
        await message.reply_text("❌ Max 2GB!")
        return
    
    user_files[user_id] = {'type': 'video', 'message': message,
        'file_id': message.video.file_id}
    
    keyboard = [[
        InlineKeyboardButton("🗜️ Compress", callback_data="compress_video")
    ], [
        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    ]]
    
    await message.reply_text("🎥 **Video received!**\n\nWhat to do?",
        reply_markup=InlineKeyboardMarkup(keyboard))


@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "cancel":
        if user_id in user_files:
            del user_files[user_id]
        await callback_query.message.edit_text("❌ Cancelled")
        return
    
    if user_id not in user_files:
        await callback_query.answer("❌ No file!", show_alert=True)
        return
    
    if data.startswith("compress_"):
        file_type = data.split("_")[1]
        keyboard = [[
            InlineKeyboardButton("🔥 Max", callback_data=f"complvl_{file_type}_max"),
            InlineKeyboardButton("⚡ High", callback_data=f"complvl_{file_type}_high")
        ], [
            InlineKeyboardButton("🔧 Med", callback_data=f"complvl_{file_type}_med"),
            InlineKeyboardButton("✨ Low", callback_data=f"complvl_{file_type}_low")
        ], [
            InlineKeyboardButton("❌ Cancel", callback_data="cancel")
        ]]
        await callback_query.message.edit_text("🎚️ **Select level:**",
            reply_markup=InlineKeyboardMarkup(keyboard))
        await callback_query.answer()
    
    elif data.startswith("complvl_"):
        _, file_type, level = data.split("_")
        await callback_query.message.edit_text("⏳ Processing...")
        await TaskQueue.add_task(process_compression, client, 
            callback_query.message, user_id, file_type, level)
        await callback_query.answer()


if __name__ == "__main__":
    print("🤖 Bot starting...")
    print(f"✅ Ready!\n")
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        for temp_dir in temp_directories:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        print("✅ Stopped!")
