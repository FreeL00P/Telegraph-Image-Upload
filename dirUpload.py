import io
import os
import sys
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from PIL import Image
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

def compress_image(image_path, temp_dir='temp', max_size=5 * 1024 * 1024, quality=85):
    """
       压缩图像，确保其大小不超过指定的最大字节数，并返回一个 Image 对象。

       :param image_path: str - 图像文件的路径
       :param temp_dir: str - 临时文件夹的路径，默认为 'temp'
       :param max_size: int - 图像的最大字节数，默认为 5MB
       :param quality: int - 图像初始质量，默认为 85
       :return: Image - 压缩后的 Image 对象
       """

    with Image.open(image_path) as img:
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

    return Image.open(img_bytes)

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
        logging.info(f"尺寸过大！缩小至{round(scale_percentage,0)}%")
    if new_height > max_height:
        scale_percentage = max_height / original_height * 100
        new_height = max_height
        new_width = int(original_width * scale_percentage / 100)
        logging.info(f"尺寸过大！缩小至{round(scale_percentage,0)}%")
    img = img.resize((new_width, new_height), Image.LANCZOS)
    return img
def upload_file(file_path, session, url_base):
    """
    上传单个文件并返回文件的URL

    :param file_path: str - 文件路径
    :param session: requests.Session - 会话对象，用于保持连接
    :param url_base: str - 基础URL，用于构造上传请求
    :return: str or None - 上传成功返回URL，否则返回None
    """
    try:
        file_name = os.path.basename(file_path)
        final_img=Image.open(file_path)
        # 检查文件大小并在必要时进行压缩
        if os.path.getsize(file_path) > 5 * 1024 * 1024:  # 大于5MB
            logging.info(f"{file_name} 大于5MB，正在压缩...")
            final_img = compress_image(file_path)
        img_byte_arr = io.BytesIO()
        img_byte_arr.seek(0)
        # 检查图片尺寸
        resize_img=resize_image(final_img,100)
        # 将 Image 对象转换为字节流
        resize_img.save(img_byte_arr, format='JPEG')  # 使用合适的格式保存图像到字节流
        img_byte_arr.seek(0)  # 重置字节流的指针位置
        # 将图像作为文件上传
        files = {'file': ('output_image.jpg', img_byte_arr, 'image/image/jpeg')}
        response = session.post(url_base + '/upload', files=files)
        if response.status_code == 200:
            data = response.json()
            src = data[0]['src']
            final_url = url_base + src
            logging.info(f"{file_name} 上传成功！URL: {final_url}")
            return final_url
        else:
            logging.error(f"{file_name} 上传过程中发生错误: {response.status_code}{file_path}")
            return None
    except Exception as e:
        logging.error(f"{file_name} 上传过程中发生错误: {e}")
        return None

def retry_failed_files(failed_files, src_values, url_base):
    """
   重新尝试上传失败的文件

   :param failed_files: list - 需要重试的文件路径列表
   :param src_values: list - 已成功上传的文件URL列表
   :param url_base: str - 基础URL，用于构造上传请求
   """
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
            executor.submit(upload_file, filepath, session, url_base): filepath
            for filepath in failed_files  # 修改这里，直接传递完整的文件路径
        }

        # 处理重试结果
        for future in as_completed(futures):
            file_path = futures[future]
            try:
                src = future.result(timeout=60)  # 增加超时设置
                if src:
                    src_values.append(src)
                    if len(src_values) == 30:
                        save_urls_to_file_by_folder(src_values, folder_name)
                        src_values = []
            except TimeoutError:
                logging.error(f"{file_path} 上传超时")
            except Exception as e:
                logging.error(f"处理 {file_path} 时发生异常: {e}")

        executor.shutdown(wait=True)  # 确保所有线程已完成
    # 手动关闭会话
    session.close()
    logging.info("重试上传任务已完成。")

def upload_files_in_directory_with_subfolders(directory):
    """
    上传目录中的所有文件，包括子文件夹，并且采用分组多线程上传

    :param directory: str - 要上传的根目录路径
    """
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5)
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    # session.proxies.update(proxies)

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
                    filepath=os.path.join(root, file_name)
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
            retry_failed_files(failed_files, url_base,src_values)
        else:
            logging.info(f"文件夹 {folder_name} 中没有失败的文件。")

    session.close()

def save_urls_to_file_by_folder(urls, folder_name):
    """
    将上传后的URL保存到一个以文件夹名命名的文件中

    :param src_values: list - 已上传文件的URL列表
    :param folder_name: str - 保存文件时使用的文件夹名称
    """
    file_path = f"{folder_name}.txt"
    with save_file_lock:  # 确保线程安全
        with open(file_path, 'a', encoding='utf-8') as f:
            for url in urls:
                f.write(url + '\n')
    logging.info(f"URL保存到 {file_path} 完成。")
def main():
    """ 主函数 """
    global upload_directory
    upload_directory = r""
    global url_base
    url_base = ''
    # global proxies
    # proxies = {
    #     "http": "http://127.0.0.1:7890",
    #     "https": "http://127.0.0.1:7890"
    # }
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
    upload_files_in_directory_with_subfolders(upload_directory)
    end_time = time.time()
    logging.info(f"任务完成，总用时: {end_time - start_time:.2f} 秒")
    # 所有任务完成后退出程序
    logging.info("程序执行完毕，正在退出...")
    sys.exit(0)
if __name__ == "__main__":
    main()





