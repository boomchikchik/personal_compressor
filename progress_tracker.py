import time
from typing import Optional


class ProgressTracker:
    """Enhanced progress tracker with proper data handling"""
    
    def __init__(self, message, total_size: int = 0, operation: str = "Processing"):
        self.message = message
        self.total_size = total_size
        self.current = 0
        self.last_update = 0
        self.start_time = time.time()
        self.operation = operation
        self.last_percentage = 0
        self.update_count = 0
        
    async def update_progress(self, current: int, total: Optional[int] = None):
        """Update progress with proper data handling"""
        self.current = current
        self.update_count += 1
        
        if total is not None and total > 0:
            self.total_size = total
        
        current_time = time.time()
        
        if self.update_count == 1:
            self.last_update = current_time
            self.last_percentage = 0
            
            if self.total_size > 0:
                text = self._generate_detailed_progress()
            else:
                text = self._generate_simple_progress()
            
            if text:
                try:
                    await self.message.edit_text(text)
                except Exception:
                    pass
            return
        
        if self.total_size > 0:
            percentage = (current / self.total_size) * 100
            if current_time - self.last_update < 1.5 and abs(percentage - self.last_percentage) < 3:
                return
            self.last_percentage = percentage
        else:
            if current_time - self.last_update < 2:
                return
        
        self.last_update = current_time
        
        if self.total_size > 0:
            text = self._generate_detailed_progress()
        else:
            text = self._generate_simple_progress()
        
        if text is None:
            return
        
        try:
            await self.message.edit_text(text)
        except Exception:
            pass
    
    def _generate_detailed_progress(self) -> str:
        """Generate detailed progress with percentage, speed, ETA"""
        percentage = (self.current / self.total_size) * 100
        
        elapsed = time.time() - self.start_time
        speed = self.current / elapsed if elapsed > 0 else 0
        
        remaining = self.total_size - self.current
        eta = remaining / speed if speed > 0 else 0
        
        progress_bar = self.create_progress_bar(percentage)
        
        text = f"""**{self.operation}**

{progress_bar} {percentage:.1f}%

📊 **Progress:** {self.format_size(self.current)} / {self.format_size(self.total_size)}
⚡ **Speed:** {self.format_size(speed)}/s
⏱️ **ETA:** {self.format_time(eta)}
⏰ **Elapsed:** {self.format_time(elapsed)}"""
        
        return text
    
    def _generate_simple_progress(self) -> str:
        """Generate simple progress without total size"""
        elapsed = time.time() - self.start_time
        speed = self.current / elapsed if elapsed > 0 else 0
        
        text = f"""**{self.operation}**

📊 **Processed:** {self.format_size(self.current)}
⚡ **Speed:** {self.format_size(speed)}/s
⏰ **Elapsed:** {self.format_time(elapsed)}"""
        
        return text
    
    @staticmethod
    def create_progress_bar(percentage: float, length: int = 20) -> str:
        """Create a visual progress bar"""
        filled = int(length * percentage / 100)
        empty = length - filled
        return f"[{'█' * filled}{'░' * empty}]"
    
    @staticmethod
    def format_size(bytes_size: float) -> str:
        """Format bytes to human readable size"""
        if bytes_size < 0:
            bytes_size = 0
            
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} TB"
    
    @staticmethod
    def format_time(seconds: float) -> str:
        """Format seconds to human readable time"""
        if seconds < 0:
            return "Calculating..."
        
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"


class ProcessingProgressTracker:
    """Special tracker for processing operations (compression/conversion)"""
    
    def __init__(self, message, operation: str = "Processing"):
        self.message = message
        self.operation = operation
        self.start_time = time.time()
        self.last_update = 0
        self.current_percentage = 0
        self.update_count = 0
        
    async def update_progress(self, current: float, total: float = 100):
        """Update processing progress (percentage-based)"""
        self.update_count += 1
        current_time = time.time()
        
        if self.update_count == 1:
            self.last_update = current_time
            self.current_percentage = 0
            
            progress_bar = self._create_bar(0)
            
            text = f"""**{self.operation}**

{progress_bar} 0.0%

⏰ **Elapsed:** 0s
⏱️ **ETA:** Calculating..."""
            
            try:
                await self.message.edit_text(text)
            except Exception:
                pass
            return
        
        if current_time - self.last_update < 1:
            return
        
        self.last_update = current_time
        
        if total > 0:
            percentage = min((current / total) * 100, 100)
        else:
            percentage = 0
        
        self.current_percentage = percentage
        elapsed = current_time - self.start_time
        
        progress_bar = self._create_bar(percentage)
        
        if percentage > 0:
            total_estimated = elapsed / (percentage / 100)
            eta = total_estimated - elapsed
        else:
            eta = 0
        
        text = f"""**{self.operation}**

{progress_bar} {percentage:.1f}%

⏰ **Elapsed:** {self._format_time(elapsed)}
⏱️ **ETA:** {self._format_time(eta)}"""
        
        try:
            await self.message.edit_text(text)
        except Exception:
            pass
    
    @staticmethod
    def _create_bar(percentage: float, length: int = 20) -> str:
        """Create progress bar"""
        filled = int(length * percentage / 100)
        empty = length - filled
        return f"[{'█' * filled}{'░' * empty}]"
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format time"""
        if seconds < 0 or seconds > 3600:
            return "Calculating..."
        
        if seconds < 60:
            return f"{int(seconds)}s"
        else:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
