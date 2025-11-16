import os
import logging
import asyncio
from PIL import Image
import subprocess
from concurrent.futures import ThreadPoolExecutor

from progress_tracker import ProcessingProgressTracker

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=4)


class FileProcessor:
    """Enhanced file processor with proper progress tracking"""
    
    @staticmethod
    async def compress_image(input_path, output_path, quality=20, progress_callback=None):
        """Compress image with proper progress updates"""
        try:
            if progress_callback:
                await progress_callback.update_progress(0, 100)
            
            # Open image
            with Image.open(input_path) as img:
                if progress_callback:
                    await progress_callback.update_progress(20, 100)
                
                # Convert RGBA/LA to RGB
                if img.mode in ('RGBA', 'LA'):
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = bg
                elif img.mode == 'P':
                    img = img.convert('RGB')
                
                if progress_callback:
                    await progress_callback.update_progress(40, 100)
                
                # Resize if too large
                max_size = 1920
                if max(img.size) > max_size:
                    ratio = max_size / max(img.size)
                    new_size = tuple(int(dim * ratio) for dim in img.size)
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                if progress_callback:
                    await progress_callback.update_progress(70, 100)
                
                # Save compressed image
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
        """Compress video with real-time progress tracking"""
        try:
            # Get video duration
            duration_cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', input_path
            ]
            
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
            
            try:
                duration = float(duration_result.stdout.strip())
            except:
                duration = 0
                logger.warning("Could not get video duration")
            
            # FFmpeg compression command
            cmd = [
                'ffmpeg', '-i', input_path,
                '-c:v', 'libx264', '-crf', str(crf), '-preset', preset,
                '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                '-c:a', 'aac', '-b:a', '64k', '-ac', '1',
                '-movflags', '+faststart',
                '-progress', 'pipe:1', '-y', output_path
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Track progress
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                
                # Parse FFmpeg progress output
                if 'out_time_ms' in line and duration > 0:
                    try:
                        time_ms = int(line.split('=')[1])
                        time_seconds = time_ms / 1000000
                        progress = (time_seconds / duration) * 100
                        
                        if progress_callback:
                            await progress_callback.update_progress(min(progress, 99), 100)
                    except:
                        pass
            
            # Wait for process to complete
            process.wait()
            
            if progress_callback:
                await progress_callback.update_progress(100, 100)
            
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"Video compression error: {e}")
            raise
    
    @staticmethod
    async def compress_audio(input_path, output_path, bitrate='48k', progress_callback=None):
        """Compress audio with progress updates"""
        try:
            if progress_callback:
                await progress_callback.update_progress(0, 100)
            
            cmd = [
                'ffmpeg', '-i', input_path,
                '-c:a', 'libmp3lame', '-b:a', bitrate,
                '-ac', '1', '-ar', '22050',
                '-y', output_path
            ]
            
            if progress_callback:
                await progress_callback.update_progress(30, 100)
            
            # Run in executor to avoid blocking
            result = await asyncio.get_event_loop().run_in_executor(
                executor,
                lambda: subprocess.run(cmd, capture_output=True, text=True)
            )
            
            if progress_callback:
                await progress_callback.update_progress(100, 100)
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Audio compression error: {e}")
            raise
    
    @staticmethod
    async def compress_pdf(input_path, output_path, progress_callback=None):
        """Compress PDF with progress updates"""
        try:
            if progress_callback:
                await progress_callback.update_progress(0, 100)
            
            cmd = [
                'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
                '-dPDFSETTINGS=/screen', '-dNOPAUSE', '-dQUIET', '-dBATCH',
                '-dDownsampleColorImages=true', '-dColorImageResolution=100',
                '-dDownsampleGrayImages=true', '-dGrayImageResolution=100',
                '-dDownsampleMonoImages=true', '-dMonoImageResolution=100',
                f'-sOutputFile={output_path}', input_path
            ]
            
            if progress_callback:
                await progress_callback.update_progress(30, 100)
            
            result = await asyncio.get_event_loop().run_in_executor(
                executor,
                lambda: subprocess.run(cmd, capture_output=True)
            )
            
            if progress_callback:
                await progress_callback.update_progress(100, 100)
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"PDF compression error: {e}")
            return False
    
    @staticmethod
    def convert_image(input_path, output_path, format_type):
        """Convert image format"""
        try:
            with Image.open(input_path) as img:
                # Handle mode conversions
                if format_type.upper() in ['JPG', 'JPEG'] and img.mode in ('RGBA', 'LA', 'P'):
                    if img.mode in ('RGBA', 'LA'):
                        bg = Image.new('RGB', img.size, (255, 255, 255))
                        bg.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        img = bg
                    else:
                        img = img.convert('RGB')
                
                # Save with format-specific settings
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
    async def convert_video(input_path, output_path, format_type, progress_callback=None):
        """Convert video format with progress tracking"""
        try:
            # Get video duration first
            duration_cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', input_path
            ]
            
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
            
            try:
                duration = float(duration_result.stdout.strip())
            except:
                duration = 0
                logger.warning("Could not get video duration for conversion")
            
            codec_map = {
                'mp4': 'libx264',
                'webm': 'libvpx-vp9',
                'avi': 'mpeg4',
                'mkv': 'libx264',
                'mov': 'libx264'
            }
            
            video_codec = codec_map.get(format_type.lower(), 'libx264')
            
            cmd = [
                'ffmpeg', '-i', input_path,
                '-c:v', video_codec, '-crf', '23',
                '-c:a', 'aac', '-b:a', '128k',
                '-movflags', '+faststart',
                '-progress', 'pipe:1',
                '-y', output_path
            ]
            
            if progress_callback:
                await progress_callback.update_progress(0, 100)
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Track progress
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                
                if 'out_time_ms' in line and duration > 0:
                    try:
                        time_ms = int(line.split('=')[1])
                        time_seconds = time_ms / 1000000
                        progress = (time_seconds / duration) * 100
                        
                        if progress_callback:
                            await progress_callback.update_progress(min(progress, 99), 100)
                    except:
                        pass
            
            process.wait()
            
            if progress_callback:
                await progress_callback.update_progress(100, 100)
            
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"Video conversion error: {e}")
            return False
    
    @staticmethod
    def convert_audio(input_path, output_path, format_type):
        """Convert audio format"""
        try:
            codec_map = {
                'mp3': 'libmp3lame',
                'ogg': 'libvorbis',
                'aac': 'aac',
                'wav': 'pcm_s16le',
                'flac': 'flac',
                'm4a': 'aac'
            }
            
            codec = codec_map.get(format_type.lower(), 'libmp3lame')
            
            cmd = [
                'ffmpeg', '-i', input_path,
                '-c:a', codec, '-b:a', '128k',
                '-y', output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Audio conversion error: {e}")
            return False
