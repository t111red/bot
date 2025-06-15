#!/usr/bin/env python3
import os
import zipfile
import datetime
import logging

def create_archive():
    """
    Creates a zip archive of the entire goldfish directory.
    The archive is saved in the same directory.
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Get the current directory (where this script is located)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.basename(current_dir)  # Should be 'goldfish'
    
    # Create timestamp for unique filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"{parent_dir}_backup_{timestamp}.zip"
    archive_path = os.path.join(current_dir, archive_name)
    
    logging.info(f"Creating archive of {current_dir}")
    logging.info(f"Archive will be saved as: {archive_path}")
    
    try:
        # Create the zip file
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Определяем каталоги, которые нужно пропустить
            skip_dirs = ['.git', '__pycache__', 'env', 'venv', '.venv']
            
            # Счетчик файлов
            file_count = 0
            total_size = 0
            
            # Walk through all files and directories in the current directory
            for root, dirs, files in os.walk(current_dir):
                # Пропускаем определенные директории
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                
                # Skip the zip files we create to avoid recursion and temporary files
                files = [f for f in files if not (f.endswith('.zip') and f.startswith(parent_dir + '_backup_'))]
                
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        # Calculate relative path to maintain directory structure
                        rel_path = os.path.relpath(file_path, current_dir)
                        
                        # Проверка на доступность файла и права на чтение
                        if os.path.exists(file_path) and os.access(file_path, os.R_OK):
                            file_size = os.path.getsize(file_path)
                            total_size += file_size
                            zipf.write(file_path, rel_path)
                            file_count += 1
                            if file_count % 50 == 0:  # Логирование каждые 50 файлов
                                logging.info(f"Archived {file_count} files ({total_size / (1024*1024):.2f} MB)")
                    except Exception as e:
                        logging.warning(f"Skipping file {file_path}: {e}")
        
        logging.info(f"Archive created successfully: {archive_name}")
        logging.info(f"Archive size: {os.path.getsize(archive_path) / (1024*1024):.2f} MB")
        return archive_path
    except Exception as e:
        logging.error(f"Error creating archive: {e}")
        return None

if __name__ == "__main__":
    archive_path = create_archive()
    if archive_path:
        print(f"Archive created successfully: {archive_path}")
    else:
        print("Failed to create archive!")