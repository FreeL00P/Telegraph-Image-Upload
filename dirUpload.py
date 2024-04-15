import os
import requests
import datetime

def upload_file(file_path):
    url = 'https://sample.com/upload'
    files = {'file': open(file_path, 'rb')}
    response = requests.post(url, files=files)
    if response.status_code == 200:
        data = response.json()
        src = data[0]['src']
        src=url+src
        src = src.replace('/upload', '')
        print("[INFO]", file_path, "上传成功！URL: ", src)
        return src
    else:
        print("Error occurred during upload:", response.text)
        return None

def upload_files_in_directory(directory):
    src_values = []
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            src = upload_file(file_path)
            if src:
                src_values.append(src)
    return src_values

def main():
    upload_directory = "uploadDirectory"
    src_values = upload_files_in_directory(upload_directory)

    time=datetime.datetime.now().strftime('%Y-%m-%d')

    # Save src values to a file
    with open(time+'.txt', 'a') as f:
        for src in src_values:
            f.write(src + '\n')

if __name__ == "__main__":
    main()
