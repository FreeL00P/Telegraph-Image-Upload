import os
import requests
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import logging
import colorlog

# 配置日志记录
log_format = '%(log_color)s[%(levelname)s] %(message)s'
formatter = colorlog.ColoredFormatter(log_format)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def upload_image(url, session, upload_url_base):
    """ 上传单张图片 """
    try:
        files = {'file': requests.get(url).content}
        response = session.post(upload_url_base + '/upload', files=files)
        if response.status_code == 200:
            data = response.json()
            src = data[0]['src']
            final_url = upload_url_base + src
            logger.info(f"[INFO] {url} 上传成功！URL: {final_url}")
            return final_url
        else:
            logger.error(f"上传过程中发生错误: {response.status_code}, {response.text}")
            error_url(url)  # 记录错误的URL
            return None
    except Exception as e:
        logger.error(f"上传过程中发生错误: {e}")
        error_url(url)  # 记录错误的URL
        return None

def upload_images_from_file(file_path, upload_url_base, proxies, max_workers=4):
    """ 从文件中读取 URL 并批量上传图片 """
    src_values = []
    count = 0  # 用于计数成功上传的URL数量

    with open(file_path, 'r') as f:
        urls = [url.strip() for url in f]  # 移除每行首尾的空格和换行符

    # 配置请求会话
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5)  # 增加退避时间
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)  # 增加连接池
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.proxies.update(proxies)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(upload_image, url, session, upload_url_base): url for url in urls}

        for future in as_completed(futures):
            result = future.result()
            if result:
                src_values.append(result)
                count += 1
                if count == 30:  # 每30个URL写入一次文件并清空列表和计数器
                    save_to_file(src_values)
                    src_values = []
                    count = 0

        # 处理剩余不足30个的URL
        if src_values:
            save_to_file(src_values)

    # 手动关闭会话
    session.close()

def save_to_file(src_values):
    """ 将 URL 列表保存到文件 """
    time_str = datetime.datetime.now().strftime('%Y-%m-%d')
    with open(f"{time_str}_urlUpload_urls.txt", 'a', encoding='utf-8') as f:
        for src in src_values:
            f.write(src + '\n')

def error_url(url):
    """ 记录上传错误的 URL """
    with open('error.txt', 'a', encoding='utf-8') as f:
        f.write(url + '\n')

def main():
    """ 主函数 """
    file_path = "your_file_with_urls.txt"  # 请替换为你的文件路径
    upload_url_base = ""  # 请替换为你的上传链接
    proxies = {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890"
    }
    max_workers = 4  # 并发数

    upload_images_from_file(file_path, upload_url_base, proxies, max_workers)

if __name__ == "__main__":
    main()
