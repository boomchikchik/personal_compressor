import os
import shutil
import logging

logger = logging.getLogger(__name__)

temp_directories = []


class CleanupManager:
    """Manage temporary directory cleanup"""
    
    @staticmethod
    def register_temp_dir(temp_dir):
        """Register a temporary directory for cleanup"""
        if temp_dir not in temp_directories:
            temp_directories.append(temp_dir)
            logger.info(f"Registered temp dir: {temp_dir}")
    
    @staticmethod
    def cleanup_temp_dir(temp_dir):
        """Clean up a specific temporary directory"""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                if temp_dir in temp_directories:
                    temp_directories.remove(temp_dir)
                logger.info(f"Cleaned up: {temp_dir}")
        except Exception as e:
            logger.error(f"Cleanup error for {temp_dir}: {e}")
    
    @staticmethod
    def cleanup_all():
        """Clean up all registered temporary directories"""
        count = 0
        for temp_dir in temp_directories.copy():
            CleanupManager.cleanup_temp_dir(temp_dir)
            count += 1
        logger.info(f"Cleaned up {count} temporary directories")
    
    @staticmethod
    def cleanup_partial_downloads(temp_dir):
        """Clean up partial downloads in a directory"""
        try:
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        logger.info(f"Removed partial file: {file_path}")
        except Exception as e:
            logger.error(f"Partial cleanup error: {e}")
