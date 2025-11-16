import os
import logging
import asyncio
import tempfile
import traceback
import zipfile

from progress_tracker import ProgressTracker, ProcessingProgressTracker
from file_handlers import FileProcessor
from cleanup_manager import CleanupManager

logger = logging.getLogger(__name__)


async def process_compression(client, message, user_id, file_type, level, user_files, notify_admin_func):
    """Process file compression with proper progress tracking"""
    temp_dir = None
    
    try:
        # Check if file info exists
        if user_id not in user_files:
            await message.edit_text("❌ File data not found!")
            return
        
        file_info = user_files[user_id]
        file_id = file_info['file_id']
        original_message = file_info['message']
        
        # Compression settings
        settings = {
            'max': {'image_quality': 15, 'video_crf': 36, 'audio_bitrate': '48k'},
            'high': {'image_quality': 25, 'video_crf': 32, 'audio_bitrate': '64k'},
            'med': {'image_quality': 40, 'video_crf': 28, 'audio_bitrate': '96k'},
            'low': {'image_quality': 60, 'video_crf': 23, 'audio_bitrate': '128k'}
        }
        setting = settings.get(level, settings['high'])
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        CleanupManager.register_temp_dir(temp_dir)
        
        # === DOWNLOAD PHASE ===
        status_msg = await message.edit_text("📥 **Downloading file...**\n\nPreparing...")
        
        # Create download progress tracker (this will show bytes)
        download_progress = ProgressTracker(status_msg, operation="📥 Downloading")
        
        try:
            file_path = await client.download_media(
                file_id,
                file_name=os.path.join(temp_dir, "input"),
                progress=download_progress.update_progress
            )
        except Exception as e:
            CleanupManager.cleanup_partial_downloads(temp_dir)
            await status_msg.edit_text(f"❌ Download failed: {str(e)}")
            await notify_admin_func(f"Download failed for {user_id}", user_id, traceback.format_exc())
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ Download failed!")
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        file_size = os.path.getsize(file_path)
        
        # === COMPRESSION PHASE ===
        await status_msg.edit_text(f"🔄 **Compressing ({level.upper()})...**\n\nStarting...")
        
        # Create processing progress tracker (this will show percentage)
        processing_progress = ProcessingProgressTracker(
            status_msg,
            operation=f"🔄 Compressing ({level.upper()})"
        )
        
        success = False
        output_path = None
        
        try:
            if file_type == 'image':
                output_path = os.path.join(temp_dir, "compressed.jpg")
                success = await FileProcessor.compress_image(
                    file_path, output_path,
                    setting['image_quality'],
                    processing_progress
                )
            
            elif file_type == 'video':
                output_path = os.path.join(temp_dir, "compressed.mp4")
                success = await FileProcessor.compress_video(
                    file_path, output_path,
                    setting['video_crf'], 'faster',
                    processing_progress
                )
            
            elif file_type == 'audio':
                output_path = os.path.join(temp_dir, "compressed.mp3")
                success = await FileProcessor.compress_audio(
                    file_path, output_path,
                    setting['audio_bitrate'],
                    processing_progress
                )
            
            elif file_type == 'pdf':
                output_path = os.path.join(temp_dir, "compressed.pdf")
                success = await FileProcessor.compress_pdf(
                    file_path, output_path,
                    processing_progress
                )
            
            elif file_type == 'other':
                output_path = os.path.join(temp_dir, "compressed.zip")
                await processing_progress.update_progress(0, 100)
                
                # ZIP compression
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
                    zipf.write(file_path, os.path.basename(file_path))
                    await processing_progress.update_progress(100, 100)
                
                success = True
        
        except Exception as e:
            logger.error(f"Compression error: {e}")
            await status_msg.edit_text(f"❌ Compression failed: {str(e)}")
            await notify_admin_func(f"Compression failed for {user_id}", user_id, traceback.format_exc())
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        # === UPLOAD PHASE ===
        if success and os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            
            if output_size < file_size:
                reduction = ((file_size - output_size) / file_size) * 100
                saved = (file_size - output_size) / (1024 * 1024)
                
                await status_msg.edit_text("📤 **Uploading...**\n\nPreparing...")
                
                # Create upload progress tracker
                upload_progress = ProgressTracker(
                    status_msg,
                    output_size,
                    "📤 Uploading"
                )
                
                caption = f"""✅ **Compression Complete!**

📊 **Level**: {level.upper()}
📦 **Original**: {file_size / (1024*1024):.2f} MB
🗜️ **Compressed**: {output_size / (1024*1024):.2f} MB
📉 **Reduction**: {reduction:.1f}%
💾 **Saved**: {saved:.2f} MB"""
                
                try:
                    await original_message.reply_document(
                        output_path,
                        caption=caption,
                        progress=upload_progress.update_progress
                    )
                    await status_msg.delete()
                except Exception as e:
                    logger.error(f"Upload error: {e}")
                    await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
                    await notify_admin_func(f"Upload failed for {user_id}", user_id, traceback.format_exc())
            else:
                await status_msg.edit_text(
                    f"⚠️ **Compression Not Effective**\n\n"
                    f"📦 Original: {file_size / (1024*1024):.2f} MB\n"
                    f"🗜️ Result: {output_size / (1024*1024):.2f} MB\n\n"
                    f"File already optimized!"
                )
        else:
            await status_msg.edit_text("❌ Compression failed.")
            await notify_admin_func(f"Compression failed for {user_id}", user_id)
        
        # Cleanup
        CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]
    
    except Exception as e:
        logger.error(f"Critical error: {e}")
        try:
            await message.edit_text("❌ Error occurred. Admin notified.")
        except:
            pass
        await notify_admin_func(f"Critical error for {user_id}: {str(e)}", user_id, traceback.format_exc())
        if temp_dir:
            CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]


async def process_conversion(client, message, user_id, file_type, output_format, user_files, notify_admin_func):
    """Process file conversion with proper progress tracking"""
    temp_dir = None
    
    try:
        if user_id not in user_files:
            await message.edit_text("❌ File data not found!")
            return
        
        file_info = user_files[user_id]
        file_id = file_info['file_id']
        original_message = file_info['message']
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        CleanupManager.register_temp_dir(temp_dir)
        
        # === DOWNLOAD PHASE ===
        status_msg = await message.edit_text("📥 **Downloading file...**\n\nPreparing...")
        download_progress = ProgressTracker(status_msg, operation="📥 Downloading")
        
        try:
            file_path = await client.download_media(
                file_id,
                file_name=os.path.join(temp_dir, "input"),
                progress=download_progress.update_progress
            )
        except Exception as e:
            CleanupManager.cleanup_partial_downloads(temp_dir)
            await status_msg.edit_text(f"❌ Download failed: {str(e)}")
            await notify_admin_func(f"Download failed for {user_id}", user_id, traceback.format_exc())
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ Download failed!")
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        # === CONVERSION PHASE ===
        await status_msg.edit_text(f"🔄 **Converting to {output_format.upper()}...**\n\nStarting...")
        
        processing_progress = ProcessingProgressTracker(
            status_msg,
            operation=f"🔄 Converting to {output_format.upper()}"
        )
        
        success = False
        output_path = os.path.join(temp_dir, f"converted.{output_format}")
        
        try:
            if file_type == 'image':
                await processing_progress.update_progress(0, 100)
                success = await FileProcessor.convert_image(
                    file_path, output_path, output_format, processing_progress
                )
            
            elif file_type == 'video':
                success = await FileProcessor.convert_video(
                    file_path, output_path, output_format, processing_progress
                )
            
            elif file_type == 'audio':
                success = await FileProcessor.convert_audio(
                    file_path, output_path, output_format, processing_progress
                )
        
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            await status_msg.edit_text(f"❌ Conversion failed: {str(e)}")
            await notify_admin_func(f"Conversion failed for {user_id}", user_id, traceback.format_exc())
            CleanupManager.cleanup_temp_dir(temp_dir)
            return
        
        # === UPLOAD PHASE ===
        if success and os.path.exists(output_path):
            output_size = os.path.getsize(output_path)
            
            await status_msg.edit_text("📤 **Uploading...**\n\nPreparing...")
            upload_progress = ProgressTracker(status_msg, output_size, "📤 Uploading")
            
            caption = f"""✅ **Conversion Complete!**

🔄 **Format**: {output_format.upper()}
📦 **Size**: {output_size / (1024*1024):.2f} MB"""
            
            try:
                await original_message.reply_document(
                    output_path,
                    caption=caption,
                    progress=upload_progress.update_progress
                )
                await status_msg.delete()
            except Exception as e:
                logger.error(f"Upload error: {e}")
                await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
                await notify_admin_func(f"Upload failed for {user_id}", user_id, traceback.format_exc())
        else:
            await status_msg.edit_text("❌ Conversion failed.")
            await notify_admin_func(f"Conversion failed for {user_id}", user_id)
        
        # Cleanup
        CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]
    
    except Exception as e:
        logger.error(f"Critical error: {e}")
        try:
            await message.edit_text("❌ Error occurred. Admin notified.")
        except:
            pass
        await notify_admin_func(f"Critical conversion error for {user_id}: {str(e)}", user_id, traceback.format_exc())
        if temp_dir:
            CleanupManager.cleanup_temp_dir(temp_dir)
        if user_id in user_files:
            del user_files[user_id]
