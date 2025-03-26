import asyncio
import os
import re
import stat
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Union

import aiofiles
import filetype
from fastapi import UploadFile
from pydub import AudioSegment

from app.utils.logging_utils import configure_logging

# 初始化静态线程池，所有实例共享 | Initialize static thread pool, shared by all instances
_executor = ThreadPoolExecutor()


class FileUtils:
    """
    一个高性能且注重安全的文件工具类，支持异步操作，用于保存、删除和清理临时文件。

    A high-performance and security-focused file utility class that supports asynchronous operations for saving, deleting, and cleaning up temporary files.
    """

    def __init__(
        self,
        chunk_size: int = 1024 * 1024,
        batch_size: int = 10,
        delete_batch_size: int = 5,
        auto_delete: bool = True,
        limit_file_size: bool = True,
        max_file_size: int = 2 * 1024 * 1024 * 1024,
        temp_dir: str = "./temp_files",
        allowed_extensions: Optional[List[str]] = None,
    ):
        """
        初始化文件工具类

        Initialize the file utility class.

        :param chunk_size: 文件读取块大小，默认1MB | File read chunk size, default is 1MB.
        :param batch_size: 分批处理的批大小，默认10 | Batch size for processing files, default is 10.
        :param delete_batch_size: 文件删除批大小，默认5 | Batch size for deleting files, default is 5.
        :param auto_delete: 是否自动删除临时文件，默认True | Whether to auto-delete temporary files, default is True.
        :param limit_file_size: 是否限制文件大小，默认True | Whether to limit file size, default is True.
        :param max_file_size: 最大文件大小（字节），默认2GB | Maximum file size in bytes, default is 2GB.
        :param temp_dir: 临时文件夹路径，默认'./temp_files' | Temporary directory path, default is './temp_files'.
        :return: None
        """
        # 配置日志记录器 | Configure the logger
        self.logger = configure_logging(name=__name__)

        # 设置 umask，确保新创建的文件权限为 600 | Set umask to ensure new files have 600 permissions
        if os.name != "nt":
            # 在非 Windows 系统上设置 umask
            os.umask(0o077)

        # 将 temp_dir 转换为基于当前工作目录的绝对路径 | Convert temp_dir to an absolute path
        if temp_dir:
            # 创建临时目录 | Create temporary directory
            os.makedirs(temp_dir, exist_ok=True)
            self.TEMP_DIR = os.path.abspath(temp_dir)
            self.temp_dir_obj = None

            # 在非 Windows 系统上设置目录权限
            if os.name != "nt":
                os.chmod(
                    self.TEMP_DIR, stat.S_IRWXU
                )  # 设置目录权限为 700 | Set directory permissions to 700
            self.logger.debug(f"Temporary directory set to: {self.TEMP_DIR}")
        else:
            self.temp_dir_obj = tempfile.TemporaryDirectory()
            self.TEMP_DIR = self.temp_dir_obj.name
            if os.name != "nt":
                os.chmod(self.TEMP_DIR, stat.S_IRWXU)
            self.logger.debug(f"Using system temporary directory {self.TEMP_DIR}")

        # 配置类属性 | Configure class attributes
        self.AUTO_DELETE = auto_delete
        self.LIMIT_FILE_SIZE = limit_file_size
        self.MAX_FILE_SIZE = max_file_size
        self.CHUNK_SIZE = chunk_size
        self.BATCH_SIZE = batch_size
        self.DELETE_BATCH_SIZE = delete_batch_size

        # 定义允许的文件扩展名 | Define allowed file extensions
        self.ALLOWED_EXTENSIONS = allowed_extensions

    async def save_file(
        self,
        file: bytes,
        file_name: str,
        generate_safe_file_name: bool = True,
        check_file_allowed: bool = True,
    ) -> str:
        """
        自动生成安全的文件名，然后保存字节文件到临时目录

        Automatically generate a safe file name, then save the byte file to the temporary directory.

        :param file: 要保存的文件内容 | Content of the file to save.
        :param file_name: 原始文件名 | Original file name.
        :param generate_safe_file_name: 是否生成安全的文件名，默认为True | Whether to generate a safe file name, default is True.
        :param check_file_allowed: 检查文件类型是否被允许，默认为True | Check if the file type is allowed, default is True.
        :return: 保存的文件路径 | Path to the saved file.
        """
        safe_file_name = (
            self._generate_safe_file_name(file_name)
            if generate_safe_file_name
            else file_name
        )
        file_path = os.path.join(self.TEMP_DIR, safe_file_name)
        file_path = os.path.realpath(file_path)

        # 确保文件路径在 TEMP_DIR 内部 | Ensure file path is within TEMP_DIR
        if not file_path.startswith(os.path.realpath(self.TEMP_DIR) + os.sep):
            self.logger.error(f"Invalid file path detected: {file_path}")
            raise ValueError("Invalid file path detected.")

        try:
            # 检查文件大小限制 | Check file size limit
            if self.LIMIT_FILE_SIZE and len(file) > self.MAX_FILE_SIZE:
                error_msg = (
                    f"File size exceeds the limit: {len(file)} > {self.MAX_FILE_SIZE}"
                )
                self.logger.error(error_msg)
                raise ValueError(error_msg)

            # 异步写入文件 | Asynchronously write file
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(file)

            # 设置文件权限，仅所有者可读写 | Set file permissions to 600
            if os.name != "nt":
                await asyncio.to_thread(
                    os.chmod, file_path, stat.S_IRUSR | stat.S_IWUSR
                )

            if check_file_allowed and not self.is_allowed_file_type(file_path):
                error_msg = f"File type: {file_name} is not supported."
                self.logger.error(error_msg)
                await self.delete_file(file_path)
                raise ValueError(error_msg)

            self.logger.debug("File saved successfully.")
            return file_path
        except IOError as e:
            self.logger.error(f"Failed to save file due to an exception: {str(e)}")
            raise ValueError("An error occurred while saving the file.")

    async def save_uploaded_file(
        self, file: Union[UploadFile, bytes], file_name: str
    ) -> str:
        """
        保存FastAPI上传的文件到临时目录

        Save an uploaded file from FastAPI to the temporary directory.

        :param file: FastAPI上传的文件对象或字节内容 | File object or byte content uploaded from FastAPI.
        :param file_name: 原始文件名 | Original file name.
        :return: 保存的文件路径 | Path to the saved file.
        """
        if type(file).__name__ == "UploadFile":
            # 读取文件内容 | Read content of UploadFile
            content = await file.read()
        else:
            # 如果已经是字节内容，直接使用 | If already bytes, use as is
            content = file

        return await self.save_file(content, file_name)

    def _generate_safe_file_name(self, original_name: str) -> str:
        """
        生成安全且唯一的文件名

        Generate a safe and unique file name.

        :param original_name: 原始文件名 | Original file name.
        :return: 安全且唯一的文件名 | Safe and unique file name.
        """
        # 获取文件的扩展名，并限制为合法字符 | Get file extension and allow only safe characters
        _, ext = os.path.splitext(original_name)
        ext = re.sub(r"[^\w\.]", "", ext)
        ext = ext.lower()
        if len(ext) > 10:
            ext = ext[:10]

        unique_name = f"{uuid.uuid4().hex}{ext}"
        self.logger.debug(f"Generated unique file name: {unique_name}")
        return unique_name

    def is_allowed_file_type(self, file_path: str) -> bool:
        """
        检查文件是否为允许的类型

        Check if the file is of an allowed type.

        :param file_path: 文件路径 | Path to the file.
        :return: 如果文件类型被允许则返回True，否则返回False | True if the file type is allowed, False otherwise.
        """
        try:
            # 如果 ALLOWED_EXTENSIONS 为空，则不限制文件类型 | If ALLOWED_EXTENSIONS is empty, do not restrict file types
            if not self.ALLOWED_EXTENSIONS:
                return True
            # 使用 filetype 库检测文件类型 | Detect file type using filetype library
            kind = filetype.guess(file_path)
            if kind is None:
                self.logger.error("Unable to determine file type.")
                return False

            ext = f".{kind.extension}".lower()
            if ext in self.ALLOWED_EXTENSIONS:
                return True
            else:
                self.logger.error(f"File type: {ext} is not supported.")
                return False
        except Exception as e:
            self.logger.error(f"Unable to determine file type: {str(e)}")
            return False

    async def get_audio_duration(self, temp_file_path: str) -> float:
        """
        获取音频文件的时长

        Get the duration of an audio file

        :param temp_file_path: 文件路径 | File path
        :return: 音频文件时长（秒） | Audio file duration (seconds)
        :raises: ValueError: 获取音频时长时发生错误 | An error occurred while getting the audio duration
        """
        # 初始化 audio 变量 | Initialize audio variable
        audio = None
        try:
            self.logger.debug(f"Getting duration of audio file: {temp_file_path}")
            audio = await asyncio.get_running_loop().run_in_executor(
                _executor, lambda: AudioSegment.from_file(temp_file_path)
            )
            # len(audio_segment) returns milliseconds
            duration = len(audio) / 1000.0
            self.logger.debug(f"Audio file duration: {duration:.2f} seconds")
            return duration
        except Exception as e:
            self.logger.error(f"Failed to get audio duration: {str(e)}")
            raise ValueError("An error occurred while getting the audio duration.")
        finally:
            # 确保释放文件资源 | Ensure the file resource is released
            if audio is not None:
                del audio
