import os
import requests
import datetime
from concurrent.futures import ThreadPoolExecutor

def upload_file(file_path):
    try:
        url = '     '
        files = {'file': open(file_path, 'rb')}
        response = requests.post(url+'/upload', files=files)
        if response.status_code == 200:
            data = response.json()
            src = data[0]['src']
            finally_url = url + src
            print("[INFO]", file_path, "上传成功！URL: ", finally_url)
            return finally_url
        else:
            print("Error occurred during upload:", response.text)
            error_url(url)  # 记录错误的文件
            return None
    except Exception as e:
            print("Error occurred during upload:", e)
            error_url(file_path)  # 记录错误的文件
            return None
def upload_files_in_directory(directory):
    src_values = []
    success_count = 0
    with ThreadPoolExecutor() as executor:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                src = executor.submit(upload_file, file_path)
                if src.result():  # 如果上传成功，计数器加一
                    success_count += 1
                    src_values.append(src.result())
                    if success_count == 30:  # 如果成功上传30个文件，保存URL并重置计数器和列表
                        save_urls_to_file(src_values)
                        src_values = []
                        success_count = 0
    # 处理剩余不足30个的URL
    if src_values:
        save_urls_to_file(src_values)

def save_urls_to_file(urls):
    time = datetime.datetime.now().strftime('%Y-%m-%d')
    with open(time + '_dirUpload_urls.txt', 'a') as f:
        for url in urls:
            f.write(url + '\n')
def error_url(url):
    with open('error.txt', 'a') as f:
        f.write(url + '\n')
def main():
    upload_directory = "      "
    upload_files_in_directory(upload_directory)

if __name__ == "__main__":
    main()
