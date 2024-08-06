import os
import requests
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import logging

# 设置日志记录
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

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
    url_base = ''
    src_values = []
    max_workers = 32  # 设置并发数量

    proxies = {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    }

    # 配置请求会话
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.1)
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)  # 增加连接池
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.proxies.update(proxies)

    failed_files = []  # 存储上传失败的文件

    # 使用线程池并发上传文件
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(upload_file, os.path.join(directory, filename), session, url_base): filename
            for filename in os.listdir(directory) if os.path.isfile(os.path.join(directory, filename))
        }

        # 处理上传结果
        for future in as_completed(futures):
            file_name = futures[future]
            try:
                src = future.result()
                if src:
                    src_values.append(src)
                    if len(src_values) == 30:
                        save_urls_to_file(src_values)
                        src_values = []
                else:
                    failed_files.append(file_name)
            except Exception as e:
                logging.error(f"处理 {file_name} 时发生异常: {e}")
                failed_files.append(file_name)

    # 重新尝试上传失败的文件
    if failed_files:
        logging.info("正在重试上传失败的文件...")
        retry_failed_files(failed_files, session, url_base, src_values)

    # 保存剩余的 URL 到文件
    if src_values:
        save_urls_to_file(src_values)

def retry_failed_files(failed_files, session, url_base, src_values):
    """ 重新尝试上传失败的文件 """
    max_workers = 32  # 设置并发数量

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(upload_file, os.path.join(upload_directory, filename), session, url_base): filename
            for filename in failed_files
        }

        # 处理重试结果
        for future in as_completed(futures):
            file_name = futures[future]
            try:
                src = future.result()
                if src:
                    src_values.append(src)
                    if len(src_values) == 30:
                        save_urls_to_file(src_values)
                        src_values = []
            except Exception as e:
                logging.error(f"处理 {file_name} 时发生异常: {e}")

def save_urls_to_file(urls):
    """ 将 URL 列表保存到文件 """
    time_str = datetime.datetime.now().strftime('%Y-%m-%d')
    with open(f"{time_str}_dirUpload_urls.txt", 'a', encoding='utf-8') as f:
        for url in urls:
            f.write(url + '\n')

def log_error(file_name):
    """ 记录上传错误的文件名 """
    with open('error.txt', 'a', encoding='utf-8') as f:
        f.write(file_name + '\n')

def main():
    """ 主函数 """
    global upload_directory
    upload_directory = ""
    upload_files_in_directory(upload_directory)

if __name__ == "__main__":
    main()
