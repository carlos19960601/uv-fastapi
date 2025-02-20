import os
import re
import tempfile
import uuid
from typing import Union

from fastapi import UploadFile

from app.utils.logging_utils import configure_logging


class FileUtils:
    """
    一个高性能且注重安全的文件工具类，支持异步操作，用于保存、删除和清理临时文件。

    A high-performance and security-focused file utility class that supports asynchronous operations for saving, deleting, and cleaning up temporary files.
    """

    def __init__(
        self,
        chunk_size: int = 1024 * 1024,
        batch_size: int = 10,
        temp_dir: str = "./temp_files",
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

        # 将 temp_dir 转换为基于当前工作目录的绝对路径 | Convert temp_dir to an absolute path
        if temp_dir:
            # 创建临时目录 | Create temporary directory
            os.makedirs(temp_dir, exist_ok=True)
            self.TEMP_DIR = os.path.abspath(temp_dir)
            self.temp_dir_obj = None
        else:
            self.temp_dir_obj = tempfile.TemporaryDirectory()
            self.TEMP_DIR = self.temp_dir_obj.name

    async def save_file(
        self,
        files: bytes,
        file_name: str,
        generate_safe_file_name: bool = True,
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
