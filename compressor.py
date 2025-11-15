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

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot Configuration
API_ID = 13216322  # Get from my.telegram.org
API_HASH = "15e5e632a8a0e52251ac8c3ccbe462c7"  # Get from my.telegram.org
BOT_TOKEN = "7335432995:AAG3phsMDhohsuStZY7m1PyoeLhNY73KYpA"  # Get from @Bo
ADMIN_ID = 5993556795

# Initialize bot
app = Client("file_compression_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Queue system
task_queue = Queue()
processing_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=4)

# Store user data
user_files = {}
active_tasks = {}
temp_directories = []

# Queue settings
MAX_CONCURRENT_TASKS = 3
current_tasks = 0

# Supported formats
IMAGE_FORMATS = ['jpg', 'png', 'webp', 'bmp', 'gif', 'ico', 'tiff']
VIDEO_FORMATS = ['mp4', 'avi', 'mkv', 'mov', 'flv', 'webm', 'wmv', '3gp']
AUDIO_FORMATS = ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a', 'wma']


class ProgressTracker:
    """Track progress for downloads, uploads, and processing"""
    
    def __init__(self, message, total_size=0, operation="Processing"):
        self.message = message
        self.total_size = total_size
        self.current = 0
        self.last_update = 0
        self.start_time = time.time()
        self.operation = operation
        
    async def update_progress(self, current, total=None):
        """Update progress with detailed stats"""
        self.current = current
        if total:
            self.total_size = total
            
        current_time = time.time()
        
        if current_time - self.last_update < 2:
            return
            
        self.last_update = current_time
        
        if self.total_size > 0:
            percentage = (current / self.total_size) * 100
            elapsed = current_time - self.start_time
            speed = current / elapsed if elapsed > 0 else 0
            eta = (self.total_size - current) / speed if speed > 0 else 0
            
            progress_bar = self.create_progress_bar(percentage)
            
            text = f"""{self.operation}... {percentage:.1f}%

{progress_bar}

📊 Progress: {self.format_size(current)} / {self.format_size(self.total_size)}
⚡ Speed: {self.format_size(speed)}/s
⏱️ ETA: {self.format_time(eta)}"""
        else:
            text = f"{self.operation}...\n\n📊 Processed: {self.format_size(current)}"
        
        try:
            if file_type == 'image':
                output_path = os.path.join(temp_dir, "compressed.jpg")
                success = await FileProcessor.compress_image(file_path, output_path, 
                                                            setting['image_quality'], progress_tracker)
            
            elif file_type == 'video':
                output_path = os.path.join(temp_dir, "compressed.mp4")
                success = await FileProcessor.compress_video(file_path, output_path, 
                                                            setting['video_crf'], 'faster', progress_tracker)
            
            elif file_type == 'audio':
                output_path = os.path.join(temp_dir, "compressed.mp3")
                success = await FileProcessor.compress_audio(file_path, output_path, 
                                                            setting['audio_bitrate'], progress_tracker)
            
            elif file_type == 'pdf':
                output_path = os.path.join(temp_dir, "compressed.pdf")
                await progress_tracker.update_progress(50, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.compress_pdf, file_path, output_path)
                await progress_tracker.update_progress(100, 100)
            
            elif file_type == 'other':
                output_path = os.path.join(temp_dir, "compressed.zip")
                await progress_tracker.update_progress(50, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.compress_file_zip, file_path, output_path)
                await progress_tracker.update_progress(100, 100)
        
        except Exception as e:
            logger.error(f"Compression error: {e}")
            await status_msg.edit_text(f"❌ Compression failed: {str(e)}")
            await notify_admin(f"Compression failed for {user_id}", user_id, traceback.format_exc())
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        if success and os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            
            if output_size < file_size:
                reduction = ((file_size - output_size) / file_size) * 100
                saved = (file_size - output_size) / (1024 * 1024)
                
                await status_msg.edit_text("📤 Uploading... 0%")
                upload_tracker = ProgressTracker(status_msg, output_size, "📤 Uploading")
                
                caption = f"""✅ **Compression Complete!**

📊 **Level**: {level.upper()}
📦 **Original**: {file_size / (1024*1024):.2f} MB
🗜️ **Compressed**: {output_size / (1024*1024):.2f} MB
📉 **Reduction**: {reduction:.1f}%
💾 **Saved**: {saved:.2f} MB"""
                
                try:
                    await original_message.reply_document(output_path, caption=caption,
                                                         progress=upload_tracker.update_progress)
                    await status_msg.delete()
                except Exception as e:
                    logger.error(f"Upload error: {e}")
                    await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
                    await notify_admin(f"Upload failed for {user_id}", user_id, traceback.format_exc())
            else:
                await status_msg.edit_text(
                    f"⚠️ **Compression Not Effective**\n\n"
                    f"📦 Original: {file_size / (1024*1024):.2f} MB\n"
                    f"🗜️ Result: {output_size / (1024*1024):.2f} MB\n\n"
                    f"File already optimized!"
                )
        else:
            await status_msg.edit_text("❌ Compression failed.")
            await notify_admin(f"Compression failed for {user_id}", user_id)
        
        CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]
    
    except Exception as e:
        logger.error(f"Critical error: {e}")
        try:
            await message.edit_text("❌ Error occurred. Admin notified.")
        except:
            pass
        await notify_admin(f"Critical error for {user_id}: {str(e)}", user_id, traceback.format_exc())
        if temp_dir:
            CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]


async def process_conversion(client, message: Message, user_id, file_type, output_format):
    temp_dir = None
    try:
        if user_id not in user_files:
            await message.edit_text("❌ File data not found!")
            return
        
        file_info = user_files[user_id]
        file_id = file_info['file_id']
        original_message = file_info['message']
        
        temp_dir = tempfile.mkdtemp()
        CleanupManager.register_temp_dir(temp_dir)
        
        status_msg = await message.edit_text("📥 Downloading... 0%")
        progress_tracker = ProgressTracker(status_msg, operation="📥 Downloading")
        
        try:
            file_path = await client.download_media(file_id, file_name=os.path.join(temp_dir, "input"),
                                                    progress=progress_tracker.update_progress)
        except Exception as e:
            CleanupManager.cleanup_partial_downloads(temp_dir)
            await status_msg.edit_text(f"❌ Download failed: {str(e)}")
            await notify_admin(f"Download failed for {user_id}", user_id, traceback.format_exc())
            return
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ Download failed!")
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        await status_msg.edit_text(f"🔄 Converting to {output_format.upper()}... 0%")
        progress_tracker = ProgressTracker(status_msg, operation=f"🔄 Converting to {output_format.upper()}")
        
        success = False
        output_path = os.path.join(temp_dir, f"converted.{output_format}")
        
        try:
            if file_type == 'image':
                await progress_tracker.update_progress(50, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.convert_image, file_path, output_path, output_format)
                await progress_tracker.update_progress(100, 100)
            
            elif file_type == 'video':
                await progress_tracker.update_progress(10, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.convert_video, file_path, output_path, output_format)
                await progress_tracker.update_progress(100, 100)
            
            elif file_type == 'audio':
                await progress_tracker.update_progress(50, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.convert_audio, file_path, output_path, output_format)
                await progress_tracker.update_progress(100, 100)
        
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            await status_msg.edit_text(f"❌ Conversion failed: {str(e)}")
            await notify_admin(f"Conversion failed for {user_id}", user_id, traceback.format_exc())
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        if success and os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            
            await status_msg.edit_text("📤 Uploading... 0%")
            upload_tracker = ProgressTracker(status_msg, output_size, "📤 Uploading")
            
            caption = f"""✅ **Conversion Complete!**

🔄 **Format**: {output_format.upper()}
📦 **Size**: {output_size / (1024*1024):.2f} MB"""
            
            try:
                await original_message.reply_document(output_path, caption=caption,
                                                     progress=upload_tracker.update_progress)
                await status_msg.delete()
            except Exception as e:
                logger.error(f"Upload error: {e}")
                await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
                await notify_admin(f"Upload failed for {user_id}", user_id, traceback.format_exc())
        else:
            await status_msg.edit_text("❌ Conversion failed.")
            await notify_admin(f"Conversion failed for {user_id}", user_id)
        
        CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]
    
    except Exception as e:
        logger.error(f"Critical error: {e}")
        try:
            await message.edit_text("❌ Error occurred. Admin notified.")
        except:
            pass
        await notify_admin(f"Critical conversion error for {user_id}: {str(e)}", user_id, traceback.format_exc())
        if temp_dir:
            CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]


if __name__ == "__main__":
    print("🤖 Bot starting...")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"📋 Queue system: Active")
    print(f"🔄 Max concurrent tasks: {MAX_CONCURRENT_TASKS}")
    print("✅ Multi-threading: Enabled")
    print("✅ Smart compression: Enabled")
    print("🧹 Auto cleanup: Enabled")
    print("📊 Progress tracking: Enabled")
    print("🚨 Error notifications: Enabled")
    print("✅ Ready to process files!\n")
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        CleanupManager.cleanup_all()
        print("✅ Cleanup complete!")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        CleanupManager.cleanup_all():
            await self.message.edit_text(text)
        except:
            pass
    
    @staticmethod
    def create_progress_bar(percentage, length=20):
        filled = int(length * percentage / 100)
        return f"[{'█' * filled}{'░' * (length - filled)}]"
    
    @staticmethod
    def format_size(bytes_size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} TB"
    
    @staticmethod
    def format_time(seconds):
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds/60)}m {int(seconds%60)}s"
        else:
            return f"{int(seconds/3600)}h {int((seconds%3600)/60)}m"


class CleanupManager:
    """Manage cleanup of temporary files"""
    
    @staticmethod
    def register_temp_dir(temp_dir):
        temp_directories.append(temp_dir)
    
    @staticmethod
    def cleanup_temp_dir(temp_dir):
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                if temp_dir in temp_directories:
                    temp_directories.remove(temp_dir)
                logger.info(f"Cleaned: {temp_dir}")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
    
    @staticmethod
    def cleanup_all():
        for temp_dir in temp_directories.copy():
            CleanupManager.cleanup_temp_dir(temp_dir)
    
    @staticmethod
    def cleanup_partial_downloads(temp_dir):
        try:
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
        except Exception as e:
            logger.error(f"Partial cleanup error: {e}")


async def notify_admin(error_message, user_id=None, traceback_str=None):
    """Notify admin about errors"""
    try:
        notification = f"""🚨 **Bot Error Alert**

⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👤 User ID: {user_id or 'Unknown'}
❌ Error: {error_message}

**Traceback:**
```
{traceback_str or 'No traceback'}
```"""
        await app.send_message(ADMIN_ID, notification)
    except Exception as e:
        logger.error(f"Admin notify failed: {e}")


class FileProcessor:
    """Handle file processing"""
    
    @staticmethod
    async def compress_image(input_path, output_path, quality=20, progress_callback=None):
        try:
            if progress_callback:
                await progress_callback.update_progress(0, 100)
            
            with Image.open(input_path) as img:
                if progress_callback:
                    await progress_callback.update_progress(20, 100)
                
                if img.mode in ('RGBA', 'LA'):
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = bg
                elif img.mode == 'P':
                    img = img.convert('RGB')
                
                if progress_callback:
                    await progress_callback.update_progress(40, 100)
                
                max_size = 1920
                if max(img.size) > max_size:
                    ratio = max_size / max(img.size)
                    new_size = tuple(int(dim * ratio) for dim in img.size)
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                if progress_callback:
                    await progress_callback.update_progress(60, 100)
                
                if output_path.lower().endswith(('.jpg', '.jpeg')):
                    img.save(output_path, 'JPEG', optimize=True, quality=quality, progressive=True)
                elif output_path.lower().endswith('.webp'):
                    img.save(output_path, 'WEBP', quality=quality, method=6)
                elif output_path.lower().endswith('.png'):
                    img.save(output_path, 'PNG', optimize=True, compress_level=9)
                else:
                    img.save(output_path, optimize=True, quality=quality)
                
                if progress_callback:
                    await progress_callback.update_progress(100, 100)
            return True
        except Exception as e:
            logger.error(f"Image compression error: {e}")
            raise
    
    @staticmethod
    async def compress_video(input_path, output_path, crf=32, preset='faster', progress_callback=None):
        try:
            duration_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                          '-of', 'default=noprint_wrappers=1:nokey=1', input_path]
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
            try:
                duration = float(duration_result.stdout.strip())
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
                
                if 'out_time_ms' in line and duration > 0:
                    time_ms = int(line.split('=')[1]) / 1000000
                    progress = (time_ms / duration) * 100
                    if progress_callback:
                        await progress_callback.update_progress(min(progress, 99), 100)
            
            process.wait()
            
            if progress_callback:
                await progress_callback.update_progress(100, 100)
            
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Video compression error: {e}")
            raise
    
    @staticmethod
    async def compress_audio(input_path, output_path, bitrate='48k', progress_callback=None):
        try:
            if progress_callback:
                await progress_callback.update_progress(0, 100)
            
            cmd = ['ffmpeg', '-i', input_path, '-c:a', 'libmp3lame', '-b:a', bitrate,
                   '-ac', '1', '-ar', '22050', '-y', output_path]
            
            if progress_callback:
                await progress_callback.update_progress(50, 100)
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if progress_callback:
                await progress_callback.update_progress(100, 100)
            
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Audio compression error: {e}")
            raise
    
    @staticmethod
    def convert_image(input_path, output_path, format_type):
        try:
            with Image.open(input_path) as img:
                if format_type.upper() in ['JPG', 'JPEG'] and img.mode in ('RGBA', 'LA', 'P'):
                    if img.mode in ('RGBA', 'LA'):
                        bg = Image.new('RGB', img.size, (255, 255, 255))
                        bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        img = bg
                    else:
                        img = img.convert('RGB')
                
                if format_type.upper() in ['JPG', 'JPEG']:
                    img.save(output_path, 'JPEG', quality=85, optimize=True)
                elif format_type.upper() == 'WEBP':
                    img.save(output_path, 'WEBP', quality=80, method=4)
                elif format_type.upper() == 'PNG':
                    img.save(output_path, 'PNG', optimize=True)
                else:
                    img.save(output_path, format=format_type.upper())
            return True
        except Exception as e:
            logger.error(f"Image conversion error: {e}")
            return False
    
    @staticmethod
    def convert_video(input_path, output_path, format_type):
        try:
            codec_map = {'mp4': 'libx264', 'webm': 'libvpx-vp9', 'avi': 'mpeg4', 
                        'mkv': 'libx264', 'mov': 'libx264'}
            video_codec = codec_map.get(format_type.lower(), 'libx264')
            
            cmd = ['ffmpeg', '-i', input_path, '-c:v', video_codec, '-crf', '23',
                   '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-y', output_path]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Video conversion error: {e}")
            return False
    
    @staticmethod
    def convert_audio(input_path, output_path, format_type):
        try:
            codec_map = {'mp3': 'libmp3lame', 'ogg': 'libvorbis', 'aac': 'aac',
                        'wav': 'pcm_s16le', 'flac': 'flac', 'm4a': 'aac'}
            codec = codec_map.get(format_type.lower(), 'libmp3lame')
            
            cmd = ['ffmpeg', '-i', input_path, '-c:a', codec, '-b:a', '128k', '-y', output_path]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Audio conversion error: {e}")
            return False
    
    @staticmethod
    def compress_pdf(input_path, output_path):
        try:
            cmd = ['gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4', '-dPDFSETTINGS=/screen',
                   '-dNOPAUSE', '-dQUIET', '-dBATCH', '-dDownsampleColorImages=true',
                   '-dColorImageResolution=100', '-dDownsampleGrayImages=true',
                   '-dGrayImageResolution=100', '-dDownsampleMonoImages=true',
                   '-dMonoImageResolution=100', f'-sOutputFile={output_path}', input_path]
            result = subprocess.run(cmd, capture_output=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"PDF compression error: {e}")
            return False
    
    @staticmethod
    def compress_file_zip(input_path, output_path):
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
                zipf.write(input_path, os.path.basename(input_path))
            return True
        except Exception as e:
            logger.error(f"ZIP compression error: {e}")
            return False


class TaskQueue:
    """Manage task queue"""
    
    @staticmethod
    async def add_task(task_func, *args, **kwargs):
        global current_tasks
        
        user_id = args[2] if len(args) > 2 else None
        
        if current_tasks >= MAX_CONCURRENT_TASKS:
            position = task_queue.qsize() + 1
            message = args[1] if len(args) > 1 else None
            if message:
                await message.edit_text(
                    f"⏳ **Task Added to Queue**\n\nPosition: #{position}\n"
                    f"Current tasks: {current_tasks}/{MAX_CONCURRENT_TASKS}\n\n"
                    f"Please wait..."
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


def create_compression_level_keyboard(file_type):
    keyboard = [
        [InlineKeyboardButton("🔥 Maximum", callback_data=f"complvl_{file_type}_max"),
         InlineKeyboardButton("⚡ High", callback_data=f"complvl_{file_type}_high")],
        [InlineKeyboardButton("🔧 Medium", callback_data=f"complvl_{file_type}_med"),
         InlineKeyboardButton("✨ Low", callback_data=f"complvl_{file_type}_low")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_format_keyboard(file_type):
    if file_type == 'image':
        formats = IMAGE_FORMATS
    elif file_type == 'video':
        formats = VIDEO_FORMATS
    elif file_type == 'audio':
        formats = AUDIO_FORMATS
    else:
        return None
    
    keyboard = []
    row = []
    for i, fmt in enumerate(formats):
        row.append(InlineKeyboardButton(fmt.upper(), callback_data=f"convert_{file_type}_{fmt}"))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def create_action_keyboard(file_type):
    keyboard = [
        [InlineKeyboardButton("🗜️ Compress", callback_data=f"compress_{file_type}"),
         InlineKeyboardButton("🔄 Convert", callback_data=f"convert_{file_type}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)


@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text("""🤖 **Welcome to Multi-Function File Bot!**

I can help you with:
📸 **Image**: Compress & Convert (JPG, PNG, WEBP, etc.)
🎥 **Video**: Compress & Convert (MP4, AVI, MKV, etc.)
🎵 **Audio**: Compress & Convert (MP3, WAV, OGG, etc.)
📄 **PDF**: Compress documents
📦 **Files**: ZIP compression

**Features:**
✅ Real-time progress tracking
✅ Smart compression
✅ Queue system
✅ Automatic cleanup
✅ Error handling

Send any file to get started! 🚀""")


@app.on_message(filters.command("help"))
async def help_command(client, message: Message):
    await message.reply_text("""📖 **Help & Information**

**Compression Levels:**
🔥 Maximum - Smallest size
⚡ High - Recommended
🔧 Medium - Balanced
✨ Low - Best quality

**Admin Commands:**
/setqueue <number> - Set max tasks
/stats - View statistics
/cleanup - Force cleanup

Send /start to begin!""")


@app.on_message(filters.command("setqueue") & filters.user(ADMIN_ID))
async def set_queue_limit(client, message: Message):
    global MAX_CONCURRENT_TASKS
    
    try:
        limit = int(message.text.split()[1])
        if limit < 1 or limit > 10:
            await message.reply_text("❌ Limit must be 1-10")
            return
        
        MAX_CONCURRENT_TASKS = limit
        await message.reply_text(f"✅ Max tasks set to: {limit}")
    except:
        await message.reply_text("❌ Usage: /setqueue <number>")


@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def bot_stats(client, message: Message):
    await message.reply_text(f"""📊 **Bot Statistics**

⚙️ Current tasks: {current_tasks}/{MAX_CONCURRENT_TASKS}
⏳ Queue: {task_queue.qsize()}
👥 Active users: {len(active_tasks)}
📁 Temp dirs: {len(temp_directories)}""")


@app.on_message(filters.command("cleanup") & filters.user(ADMIN_ID))
async def force_cleanup(client, message: Message):
    msg = await message.reply_text("🧹 Cleaning...")
    CleanupManager.cleanup_all()
    await msg.edit_text("✅ Cleanup complete!")


@app.on_message(filters.command("queue"))
async def queue_status(client, message: Message):
    await message.reply_text(
        f"**Queue Status:**\n\n🔄 Current: {current_tasks}/{MAX_CONCURRENT_TASKS}\n"
        f"⏳ Waiting: {task_queue.qsize()}"
    )


@app.on_message(filters.photo)
async def handle_photo(client, message: Message):
    user_id = message.from_user.id
    user_files[user_id] = {
        'type': 'image', 'message': message, 'file_id': message.photo.file_id, 'format': 'jpg'
    }
    await message.reply_text("📸 **Image received!**\n\nWhat would you like to do?",
                            reply_markup=create_action_keyboard('image'))


@app.on_message(filters.video)
async def handle_video(client, message: Message):
    user_id = message.from_user.id
    if message.video.file_size > 50 * 1024 * 1024:
        await message.reply_text("❌ Video too large! Max 50MB.")
        return
    
    user_files[user_id] = {
        'type': 'video', 'message': message, 'file_id': message.video.file_id, 'format': 'mp4'
    }
    await message.reply_text("🎥 **Video received!**\n\nWhat would you like to do?",
                            reply_markup=create_action_keyboard('video'))


@app.on_message(filters.audio)
async def handle_audio(client, message: Message):
    user_id = message.from_user.id
    user_files[user_id] = {
        'type': 'audio', 'message': message, 'file_id': message.audio.file_id, 'format': 'mp3'
    }
    await message.reply_text("🎵 **Audio received!**\n\nWhat would you like to do?",
                            reply_markup=create_action_keyboard('audio'))


@app.on_message(filters.document)
async def handle_document(client, message: Message):
    user_id = message.from_user.id
    file_name = message.document.file_name
    file_size = message.document.file_size
    ext = os.path.splitext(file_name)[1].lower()[1:]
    
    if file_size > 50 * 1024 * 1024:
        await message.reply_text("❌ File too large! Max 50MB.")
        return
    
    if ext in IMAGE_FORMATS:
        file_type = 'image'
    elif ext in VIDEO_FORMATS:
        file_type = 'video'
    elif ext in AUDIO_FORMATS:
        file_type = 'audio'
    elif ext == 'pdf':
        file_type = 'pdf'
    else:
        file_type = 'other'
    
    user_files[user_id] = {
        'type': file_type, 'message': message, 'file_id': message.document.file_id,
        'file_name': file_name, 'format': ext
    }
    
    if file_type in ['image', 'video', 'audio']:
        await message.reply_text(f"📄 **{file_type.capitalize()} received!**\n\nWhat to do?",
                                reply_markup=create_action_keyboard(file_type))
    elif file_type == 'pdf':
        await message.reply_text("📄 **PDF received!**\n\nCompress it?",
                                reply_markup=InlineKeyboardMarkup([
                                    [InlineKeyboardButton("🗜️ Compress", callback_data="complvl_pdf_max")],
                                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                                ]))
    else:
        await message.reply_text("📦 **File received!**\n\nCompress it?",
                                reply_markup=InlineKeyboardMarkup([
                                    [InlineKeyboardButton("🗜️ ZIP", callback_data="complvl_other_max")],
                                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                                ]))


@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "cancel":
        if user_id in user_files:
            del user_files[user_id]
        await callback_query.message.edit_text("❌ Cancelled.")
        return
    
    if user_id not in user_files:
        await callback_query.answer("❌ No file found!", show_alert=True)
        return
    
    if data.startswith("compress_") and data.count("_") == 1:
        file_type = data.split("_")[1]
        await callback_query.message.edit_text(
            "🎚️ **Select compression level:**\n\n🔥 Maximum = Smallest\n⚡ High = Recommended\n"
            "🔧 Medium = Balanced\n✨ Low = Best quality",
            reply_markup=create_compression_level_keyboard(file_type)
        )
        await callback_query.answer()
    
    elif data.startswith("complvl_"):
        _, file_type, level = data.split("_")
        await callback_query.message.edit_text("⏳ Adding to queue...")
        await TaskQueue.add_task(process_compression, client, callback_query.message, 
                                user_id, file_type, level)
        await callback_query.answer()
    
    elif data.startswith("convert_") and data.count("_") == 1:
        file_type = data.split("_")[1]
        await callback_query.message.edit_text("🔄 **Select format:**",
                                              reply_markup=create_format_keyboard(file_type))
        await callback_query.answer()
    
    elif data.startswith("convert_") and data.count("_") == 2:
        _, file_type, output_format = data.split("_")
        await callback_query.message.edit_text("⏳ Adding to queue...")
        await TaskQueue.add_task(process_conversion, client, callback_query.message,
                                user_id, file_type, output_format)
        await callback_query.answer()


async def process_compression(client, message: Message, user_id, file_type, level):
    temp_dir = None
    try:
        if user_id not in user_files:
            await message.edit_text("❌ File data not found!")
            return
        
        file_info = user_files[user_id]
        file_id = file_info['file_id']
        original_message = file_info['message']
        
        settings = {
            'max': {'image_quality': 15, 'video_crf': 36, 'audio_bitrate': '48k'},
            'high': {'image_quality': 25, 'video_crf': 32, 'audio_bitrate': '64k'},
            'med': {'image_quality': 40, 'video_crf': 28, 'audio_bitrate': '96k'},
            'low': {'image_quality': 60, 'video_crf': 23, 'audio_bitrate': '128k'}
        }
        setting = settings.get(level, settings['high'])
        
        temp_dir = tempfile.mkdtemp()
        CleanupManager.register_temp_dir(temp_dir)
        
        status_msg = await message.edit_text("📥 Downloading... 0%")
        progress_tracker = ProgressTracker(status_msg, operation="📥 Downloading")
        
        try:
            file_path = await client.download_media(file_id, file_name=os.path.join(temp_dir, "input"),
                                                    progress=progress_tracker.update_progress)
        except Exception as e:
            CleanupManager.cleanup_partial_downloads(temp_dir)
            await status_msg.edit_text(f"❌ Download failed: {str(e)}")
            await notify_admin(f"Download failed for {user_id}", user_id, traceback.format_exc())
            return
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ Download failed!")
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        file_size = os.path.getsize(file_path)
        
        await status_msg.edit_text(f"🔄 Compressing ({level.upper()})... 0%")
        progress_tracker = ProgressTracker(status_msg, operation=f"🔄 Compressing ({level.upper()})")
        
        success = False
        output_path = None
        
        try:
          # Add these lines after "try:" in process_compression function (line where it was cut)

            if file_type == 'image':
                output_path = os.path.join(temp_dir, "compressed.jpg")
                success = await FileProcessor.compress_image(file_path, output_path, 
                                                            setting['image_quality'], progress_tracker)
            
            elif file_type == 'video':
                output_path = os.path.join(temp_dir, "compressed.mp4")
                success = await FileProcessor.compress_video(file_path, output_path, 
                                                            setting['video_crf'], 'faster', progress_tracker)
            
            elif file_type == 'audio':
                output_path = os.path.join(temp_dir, "compressed.mp3")
                success = await FileProcessor.compress_audio(file_path, output_path, 
                                                            setting['audio_bitrate'], progress_tracker)
            
            elif file_type == 'pdf':
                output_path = os.path.join(temp_dir, "compressed.pdf")
                await progress_tracker.update_progress(50, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.compress_pdf, file_path, output_path)
                await progress_tracker.update_progress(100, 100)
            
            elif file_type == 'other':
                output_path = os.path.join(temp_dir, "compressed.zip")
                await progress_tracker.update_progress(50, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.compress_file_zip, file_path, output_path)
                await progress_tracker.update_progress(100, 100)
        
        except Exception as e:
            logger.error(f"Compression error: {e}")
            await status_msg.edit_text(f"❌ Compression failed: {str(e)}")
            await notify_admin(f"Compression failed for {user_id}", user_id, traceback.format_exc())
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        if success and os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            
            if output_size < file_size:
                reduction = ((file_size - output_size) / file_size) * 100
                saved = (file_size - output_size) / (1024 * 1024)
                
                await status_msg.edit_text("📤 Uploading... 0%")
                upload_tracker = ProgressTracker(status_msg, output_size, "📤 Uploading")
                
                caption = f"""✅ **Compression Complete!**

📊 **Level**: {level.upper()}
📦 **Original**: {file_size / (1024*1024):.2f} MB
🗜️ **Compressed**: {output_size / (1024*1024):.2f} MB
📉 **Reduction**: {reduction:.1f}%
💾 **Saved**: {saved:.2f} MB"""
                
                try:
                    await original_message.reply_document(output_path, caption=caption,
                                                         progress=upload_tracker.update_progress)
                    await status_msg.delete()
                except Exception as e:
                    logger.error(f"Upload error: {e}")
                    await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
                    await notify_admin(f"Upload failed for {user_id}", user_id, traceback.format_exc())
            else:
                await status_msg.edit_text(
                    f"⚠️ **Compression Not Effective**\n\n"
                    f"📦 Original: {file_size / (1024*1024):.2f} MB\n"
                    f"🗜️ Result: {output_size / (1024*1024):.2f} MB\n\n"
                    f"File already optimized!"
                )
        else:
            await status_msg.edit_text("❌ Compression failed.")
            await notify_admin(f"Compression failed for {user_id}", user_id)
        
        CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]
    
    except Exception as e:
        logger.error(f"Critical error: {e}")
        try:
            await message.edit_text("❌ Error occurred. Admin notified.")
        except:
            pass
        await notify_admin(f"Critical error for {user_id}: {str(e)}", user_id, traceback.format_exc())
        if temp_dir:
            CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]


async def process_conversion(client, message: Message, user_id, file_type, output_format):
    temp_dir = None
    try:
        if user_id not in user_files:
            await message.edit_text("❌ File data not found!")
            return
        
        file_info = user_files[user_id]
        file_id = file_info['file_id']
        original_message = file_info['message']
        
        temp_dir = tempfile.mkdtemp()
        CleanupManager.register_temp_dir(temp_dir)
        
        status_msg = await message.edit_text("📥 Downloading... 0%")
        progress_tracker = ProgressTracker(status_msg, operation="📥 Downloading")
        
        try:
            file_path = await client.download_media(file_id, file_name=os.path.join(temp_dir, "input"),
                                                    progress=progress_tracker.update_progress)
        except Exception as e:
            CleanupManager.cleanup_partial_downloads(temp_dir)
            await status_msg.edit_text(f"❌ Download failed: {str(e)}")
            await notify_admin(f"Download failed for {user_id}", user_id, traceback.format_exc())
            return
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ Download failed!")
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        await status_msg.edit_text(f"🔄 Converting to {output_format.upper()}... 0%")
        progress_tracker = ProgressTracker(status_msg, operation=f"🔄 Converting to {output_format.upper()}")
        
        success = False
        output_path = os.path.join(temp_dir, f"converted.{output_format}")
        
        try:
            if file_type == 'image':
                await progress_tracker.update_progress(50, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.convert_image, file_path, output_path, output_format)
                await progress_tracker.update_progress(100, 100)
            
            elif file_type == 'video':
                await progress_tracker.update_progress(10, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.convert_video, file_path, output_path, output_format)
                await progress_tracker.update_progress(100, 100)
            
            elif file_type == 'audio':
                await progress_tracker.update_progress(50, 100)
                success = await asyncio.get_event_loop().run_in_executor(
                    executor, FileProcessor.convert_audio, file_path, output_path, output_format)
                await progress_tracker.update_progress(100, 100)
        
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            await status_msg.edit_text(f"❌ Conversion failed: {str(e)}")
            await notify_admin(f"Conversion failed for {user_id}", user_id, traceback.format_exc())
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        if success and os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            
            await status_msg.edit_text("📤 Uploading... 0%")
            upload_tracker = ProgressTracker(status_msg, output_size, "📤 Uploading")
            
            caption = f"""✅ **Conversion Complete!**

🔄 **Format**: {output_format.upper()}
📦 **Size**: {output_size / (1024*1024):.2f} MB"""
            
            try:
                await original_message.reply_document(output_path, caption=caption,
                                                     progress=upload_tracker.update_progress)
                await status_msg.delete()
            except Exception as e:
                logger.error(f"Upload error: {e}")
                await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
                await notify_admin(f"Upload failed for {user_id}", user_id, traceback.format_exc())
        else:
            await status_msg.edit_text("❌ Conversion failed.")
            await notify_admin(f"Conversion failed for {user_id}", user_id)
        
        CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]
    
    except Exception as e:
        logger.error(f"Critical error: {e}")
        try:
            await message.edit_text("❌ Error occurred. Admin notified.")
        except:
            pass
        await notify_admin(f"Critical conversion error for {user_id}: {str(e)}", user_id, traceback.format_exc())
        if temp_dir:
            CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]


if __name__ == "__main__":
    print("🤖 Bot starting...")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"📋 Queue system: Active")
    print(f"🔄 Max concurrent tasks: {MAX_CONCURRENT_TASKS}")
    print("✅ Multi-threading: Enabled")
    print("✅ Smart compression: Enabled")
    print("🧹 Auto cleanup: Enabled")
    print("📊 Progress tracking: Enabled")
    print("🚨 Error notifications: Enabled")
    print("✅ Ready to process files!\n")
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        CleanupManager.cleanup_all()
        print("✅ Cleanup complete!")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        CleanupManager.cleanup_all()
