import io
import os
import sys
import tempfile
import threading
from pathlib import Path

import requests
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

from PIL import Image
from PIL.Image import Resampling
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import logging
import colorlog
import signal
import time

# 配置日志记录
log_format = '%(log_color)s[%(levelname)s] %(message)s'
formatter = colorlog.ColoredFormatter(log_format)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# 用于保存链接时的锁
save_file_lock = threading.Lock()

def sanitize_text(text):
    """ 清理文本，尝试使用 GBK 编码 """
    try:
        return text.encode('gbk', errors='ignore').decode('gbk')
    except Exception:
        return text

def ensure_temp_directory(temp_dir):
    """
    确保当前目录下存在指定的临时文件夹。如果不存在，则创建它。

    :param temp_dir: 临时文件夹的路径，默认为'./temp'
    """
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        logging.info(f"已创建临时文件夹: {temp_dir}")

def clean_temp_directory(temp_dir='temp', max_files=30):
    """
    清理指定临时文件夹中的所有文件，如果文件数量超过max_files。

    :param temp_dir: 临时文件夹的路径，默认为'./temp'
    :param max_files: 临时文件夹中允许的最大文件数量，超过此数量将进行清理
    """
    files = os.listdir(temp_dir)

    if len(files) > max_files:
        logging.info(f"临时文件夹 '{temp_dir}' 文件超过 {max_files} 个，正在清理...")
        for file_name in files:
            file_path = os.path.join(temp_dir, file_name)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    logging.info(f"已删除临时文件: {file_path}")
            except Exception as e:
                logging.error(f"删除临时文件 {file_path} 时发生错误: {e}")
# 创建一个全局锁
lock = threading.Lock()
def compress_image(image_path, temp_dir='temp', max_size=5 * 1024 * 1024, quality=85):
    """
    压缩图片至指定大小以下并保存到指定的临时目录中，同时调整图片尺寸。

    :param image_path: 原始图片的路径
    :param temp_dir: 临时文件夹的路径，默认为'./temp'
    :param max_size: 图片的最大字节数，默认为5MB
    :param max_width: 最大宽度，默认为3840像素
    :param max_height: 最大高度，默认为2160像素
    :param quality: JPEG压缩质量，默认值为85
    :return: 压缩后的图片路径
    """

    with lock:
        temp_dir="temp/"+list(Path(image_path).parts)[-2] if len(image_path) >= 2 else None
        ensure_temp_directory(temp_dir)

    with Image.open(image_path) as img:
        img = resize_image(img, quality)
        img_bytes = io.BytesIO()

        while True:
            img.save(img_bytes, format='JPEG', quality=quality)
            size = img_bytes.tell()

            if size <= max_size or quality <= 10:
                break

            img_bytes.seek(0)
            img_bytes.truncate(0)
            quality -= 5

        img_bytes.seek(0)

        # 将压缩后的字节流写入指定的临时目录中的文件
        temp_file_path = os.path.join(temp_dir, os.path.basename(image_path))
        with open(temp_file_path, 'wb') as f:
            f.write(img_bytes.read())

        # logging.info(f"图片已压缩并保存至临时文件: {temp_file_path}")
    return temp_file_path
def resize_image(img, scale_percentage):
    """
    按照给定的百分比缩放图片，同时确保缩放后的图片尺寸小于4000x6000像素。

    :param img: PIL.Image对象
    :param scale_percentage: 缩放比例（百分比），例如50表示缩小为原始尺寸的50%
    :return: 缩放后的PIL.Image对象
    """
    original_width, original_height = img.size
    new_width = int(original_width * scale_percentage / 100)
    new_height = int(original_height * scale_percentage / 100)

    # 确保缩放后的尺寸小于4000x6000
    max_width, max_height = 4000, 6000
    if new_width > max_width:
        scale_percentage = max_width / original_width * 100
        new_width = max_width
        new_height = int(original_height * scale_percentage / 100)
    if new_height > max_height:
        scale_percentage = max_height / original_height * 100
        new_height = max_height
        new_width = int(original_width * scale_percentage / 100)

    img = img.resize((new_width, new_height), Image.LANCZOS)
    return img
def upload_file(file_path, session, url_base):
    """ 上传单个文件 """
    file_name = os.path.basename(file_path)
    try:
        # 检查文件大小并在必要时进行压缩
        if os.path.getsize(file_path) > 5 * 1024 * 1024:  # 大于5MB
            logging.info(f"{file_name} 大于5MB，正在压缩...并缩放85%")
            compressed_file_path = compress_image(file_path)
            file_to_upload = compressed_file_path
        else:
            file_to_upload = file_path

        with open(file_to_upload, 'rb') as f:
            files = {'file': (file_name, f)}

            response = session.post(url_base + '/upload', files=files)

        if response.status_code == 200:
            data = response.json()
            src = data[0]['src']
            final_url = url_base + src
            logging.info(f"{file_name} 上传成功！URL: {final_url}")
            return final_url
        else:
            logging.error(f"{file_name} 上传过程中发生错误: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"{file_name} 上传过程中发生错误: {e.args}")
        return None

def upload_files_in_directory(directory):
    """ 上传目录中的所有文件 """

    src_values = []

    # 配置请求会话
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5)  # 增加退避时间
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)  # 增加连接池
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.proxies.update(proxies)

    failed_files = []  # 存储上传失败的文件

    all_files = [filename for filename in os.listdir(directory) if os.path.isfile(os.path.join(directory, filename))]

    num_batches = (len(all_files) + batch_size - 1) // batch_size  # 计算需要的批次数

    for batch_num in range(num_batches):
        batch_files = all_files[batch_num * batch_size: (batch_num + 1) * batch_size]
        logging.info(f"开始上传第 {batch_num + 1}/{num_batches} 批文件...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(upload_file, os.path.join(directory, filename), session, url_base): filename
                for filename in batch_files
            }

            # 处理上传结果
            for future in as_completed(futures):
                file_name = futures[future]
                try:
                    src = future.result(timeout=60)  # 增加超时设置
                    if src:
                        src_values.append(src)
                        if len(src_values) == 30:
                            save_urls_to_file(src_values)
                            src_values = []
                    else:
                        failed_files.append(file_name)
                except TimeoutError:
                    logging.error(f"{file_name} 上传超时")
                    failed_files.append(file_name)
                except Exception as e:
                    logging.error(f"处理 {file_name} 时发生异常: {e}")
                    failed_files.append(file_name)

            executor.shutdown(wait=True)  # 确保所有线程已完成

        # 暂停一段时间以释放资源
        logging.info(f"第 {batch_num + 1} 批文件上传完成，暂停 1 秒...")
        time.sleep(1)

    # 手动关闭会话
    session.close()

    # 检查是否有失败的文件需要重试
    if failed_files:
        logging.info("正在重试上传失败的文件...")
        retry_failed_files(failed_files, url_base, src_values)
    else:
        logging.info("没有需要重试的文件。")

    # 保存剩余的 URL 到文件
    if src_values:
        save_urls_to_file(src_values)

    # 最后打印日志，确认所有任务已完成
    logging.info("所有文件上传任务已完成。")

def retry_failed_files(failed_files, url_base, src_values):
    """ 重新尝试上传失败的文件 """
    max_workers = 2  # 减少并发数量

    logging.info("开始重试上传失败的文件...")

    # 重新打开会话
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5)  # 增加退避时间
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(upload_file, os.path.join(upload_directory, filename), session, url_base): filename
            for filename in failed_files
        }

        # 处理重试结果
        for future in as_completed(futures):
            file_name = futures[future]
            try:
                src = future.result(timeout=60)  # 增加超时设置
                if src:
                    src_values.append(src)
                    if len(src_values) == 30:
                        save_urls_to_file(src_values)
                        src_values = []
            except TimeoutError:
                logging.error(f"{file_name} 上传超时")
            except Exception as e:
                logging.error(f"处理 {file_name} 时发生异常: {e}")

        executor.shutdown(wait=True)  # 确保所有线程已完成

    # 手动关闭会话
    session.close()

    logging.info("重试上传任务已完成。")

def save_urls_to_file(urls):
    """ 将 URL 列表保存到文件 """
    time_str = datetime.datetime.now().strftime('%Y-%m-%d')
    with save_file_lock:  # 确保线程安全
        with open(f"{time_str}_dirUpload_urls.txt", 'a', encoding='utf-8') as f:
            for url in urls:
                f.write(url + '\n')

def upload_files_in_directory_with_subfolders(directory):
    """ 上传目录中的所有文件，包括子文件夹，并且采用分组多线程上传 """
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5)
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.proxies.update(proxies)

    for root, dirs, files in os.walk(directory):
        if not files:
            continue

        src_values = []
        failed_files = []
        folder_name = os.path.basename(root)
        num_batches = (len(files) + batch_size - 1) // batch_size  # 计算需要的批次数

        for batch_num in range(num_batches):
            batch_files = files[batch_num * batch_size: (batch_num + 1) * batch_size]
            logging.info(f"开始上传文件夹 {folder_name} 中的第 {batch_num + 1}/{num_batches} 批文件...")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(upload_file, os.path.join(root, file), session, url_base): file
                    for file in batch_files
                }

                for future in as_completed(futures):
                    file_name = futures[future]
                    filepath=directory+"\\"+file_name
                    try:
                        src = future.result(timeout=60)
                        if src:
                            src_values.append(src)
                        else:
                            failed_files.append(filepath)
                    except TimeoutError:
                        logging.error(f"{file_name} 上传超时")
                        failed_files.append(filepath)
                    except Exception as e:
                        logging.error(f"处理 {file_name} 时发生异常: {e}")
                        failed_files.append(filepath)
                executor.shutdown(wait=True)

            # 保存已上传的 URL 到文件
            if len(src_values) >= 30:
                save_urls_to_file_by_folder(src_values, folder_name)
                src_values = []

            # 暂停一段时间以释放资源
            logging.info(f"文件夹 {folder_name} 中的第 {batch_num + 1} 批文件上传完成，暂停 1 秒...")
            time.sleep(1)

        # 保存剩余的 URL 到文件
        if src_values:
            save_urls_to_file_by_folder(src_values, folder_name)

        # 检查是否有失败的文件需要重试
        if failed_files:
            logging.info(f"正在重试文件夹 {folder_name} 中的失败文件...")
            retry_failed_files(failed_files, url_base, src_values)
        else:
            logging.info(f"文件夹 {folder_name} 中没有失败的文件。")

    session.close()

def save_urls_to_file_by_folder(urls, folder_name):
    """ 将 URL 列表保存到以文件夹命名的文件中 """
    file_path = f"{folder_name}.txt"
    with save_file_lock:  # 确保线程安全
        with open(file_path, 'a', encoding='utf-8') as f:
            for url in urls:
                f.write(url + '\n')

def main():
    """ 主函数 """
    global upload_directory
    upload_directory = 'D:/test'  # 上传目录
    global url_base
    url_base = 'http://'
    global proxies
    proxies = {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    }
    global max_workers
    max_workers= 4  # 并发数
    global   batch_size
    batch_size = 50  # 每次处理文件数
    # 捕获 SIGINT 信号 (Ctrl+C)
    def signal_handler(sig, frame):
        logging.info("程序终止，正在关闭...")
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    # 启动上传任务
    start_time = time.time()
    # upload_files_in_directory(upload_directory)
    upload_files_in_directory_with_subfolders(upload_directory)
    end_time = time.time()
    logging.info(f"任务完成，总用时: {end_time - start_time:.2f} 秒")
    # 所有任务完成后退出程序
    logging.info("程序执行完毕，正在退出...")
    sys.exit(0)
if __name__ == "__main__":
    main()





