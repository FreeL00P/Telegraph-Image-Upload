import os
import requests
import datetime
from concurrent.futures import ThreadPoolExecutor

def upload_image(url):
    try:
        files = {'file': requests.get(url).content}
        upload_url = '' # # 请替换为你的上传链接
        response = requests.post(upload_url+'/upload', files=files)
        if response.status_code == 200:
            data = response.json()
            src = data[0]['src']
            finally_url=upload_url+src
            print("[INFO]", url, "上传成功！URL: ", finally_url)
            return finally_url
        else:
            print("Error occurred during upload:", response.text)
            error_url(url)  # 记录错误的URL
            return None
    except Exception as e:
        print("Error occurred during upload:", e)
        error_url(url)  # 记录错误的URL
        return None

def upload_images_from_file(file_path):
    src_values = []
    count = 0  # 用于计数成功上传的URL数量
    with open(file_path, 'r') as f:
        urls = [url.strip() for url in f]  # 移除每行首尾的空格和换行符

    with ThreadPoolExecutor() as executor:
        for result in executor.map(upload_image, urls):
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

def save_to_file(src_values):
    time = datetime.datetime.now().strftime('%Y-%m-%d')
    with open(time + '_urlUpload_urls.txt', 'a') as f:
        for src in src_values:
            f.write(src + '\n')

def error_url(url):
    with open('error.txt', 'a') as f:
        f.write(url + '\n')

def main():
    file_path = "       "  
    upload_images_from_file(file_path)

if __name__ == "__main__":
    main()
