import os
import sys
import threading
import requests
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
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

def sanitize_text(text):
    """ 清理文本，尝试使用 GBK 编码 """
    try:
        return text.encode('gbk', errors='ignore').decode('gbk')
    except Exception:
        return text

def upload_file(file_path, session, url_base):
    """ 上传单个文件 """
    file_name = os.path.basename(file_path)
    try:
        with open(file_path, 'rb') as f:
            files = {'file': f.read()}
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
        logging.error(f"{file_name} 上传过程中发生错误: {e}")
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
                    try:
                        src = future.result(timeout=60)
                        if src:
                            src_values.append(src)
                        else:
                            failed_files.append(file_name)
                    except TimeoutError:
                        logging.error(f"{file_name} 上传超时")
                        failed_files.append(file_name)
                    except Exception as e:
                        logging.error(f"处理 {file_name} 时发生异常: {e}")
                        failed_files.append(file_name)

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
            logging.info(f"正在重试文件夹 {folder_name} 中上传失败的文件...")
            retry_failed_files_with_floder(failed_files, url_base, src_values, root, folder_name)

    session.close()
    logging.info("所有文件上传任务已完成。")

def save_urls_to_file_by_folder(urls, folder_name):
    """ 将 URL 列表保存到以文件夹名称命名的文件 """
    time_str = datetime.datetime.now().strftime('%Y-%m-%d')
    file_path = f"{time_str}_{folder_name}_urls.txt"
    with open(file_path, 'a', encoding='utf-8') as f:
        for url in urls:
            f.write(url + '\n')

def retry_failed_files_with_floder(failed_files, url_base, src_values, root, folder_name):
    """ 重新尝试上传失败的文件 """
    logging.info(f"开始重试文件夹 {folder_name} 中的失败文件...")

    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5)
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(upload_file, os.path.join(root, file), session, url_base): file
            for file in failed_files
        }

        for future in as_completed(futures):
            file_name = futures[future]
            try:
                src = future.result(timeout=60)
                if src:
                    src_values.append(src)
            except TimeoutError:
                logging.error(f"{file_name} 上传超时")
            except Exception as e:
                logging.error(f"处理 {file_name} 时发生异常: {e}")

        executor.shutdown(wait=True)

    session.close()

    if src_values:
        save_urls_to_file_by_folder(src_values, folder_name)

    logging.info(f"文件夹 {folder_name} 中的重试上传任务已完成。")


def log_error(file_name):
    """ 记录上传错误的文件名 """
    with open('error.txt', 'a', encoding='utf-8') as f:
        f.write(file_name + '\n')

def signal_handler(signum, frame):
    logging.warning("接收到中断信号，正在退出...")
    sys.exit(0)

def main():
    """ 主函数 """
    global upload_directory
    upload_directory = ''
    global url_base
    url_base = ''
    global proxies
    proxies = {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    }
    global max_workers
    max_workers= 4  # 并发数
    global   batch_size
    batch_size = 20  # 每次处理文件数
    # 处理信号中断
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # upload_files_in_directory(upload_directory)
    upload_files_in_directory_with_subfolders(upload_directory)
    # 打印当前活动线程列表
    logging.info("当前活动线程列表:")
    for thread in threading.enumerate():
        logging.info(f"线程名: {thread.name}，守护线程: {thread.daemon}")

    # 所有任务完成后退出程序
    logging.info("程序执行完毕，正在退出...")
    sys.exit(0)

if __name__ == "__main__":
    main()
