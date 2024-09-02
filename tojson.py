import os
import json
import logging

import colorlog
from colorama import init, Fore

# 初始化 Colorama
init(autoreset=True)

def read_urls_from_file(file_path):
    """从文件中读取 URL，每行一个 URL"""
    with open(file_path, 'r') as file:
        return [line.strip() for line in file if line.strip()]

def convert_txt_to_json(base_dir):
    """将指定目录下的 TXT 文件转换为 JSON 格式"""
    data = {f"{os.path.basename(base_dir)}": {"urls": {}}}

    # 遍历 base_directory 目录中的文件
    for file_name in sorted(os.listdir(base_dir)):
        if file_name.endswith('.txt'):
            file_path = os.path.join(base_dir, file_name)

            urls = read_urls_from_file(file_path)
            index = os.path.splitext(file_name)[0]

            # 处理序号
            count = 1
            while len(urls) >= 200:
                if count != 1:
                    new_key = f"{index} -{count}"
                    data[f"{os.path.basename(base_dir)}"]["urls"][new_key] = urls[:200]
                    urls = urls[200:]  # 剩余 URL
                    count += 1
                else:
                    new_key = f"{index}"
                    data[f"{os.path.basename(base_dir)}"]["urls"][new_key] = urls[:200]
                    urls = urls[200:]  # 剩余 URL
                    count += 1
            # 添加剩余的 URL（如果有）
            if urls:
                if count != 1:
                    data[f"{os.path.basename(base_dir)}"]["urls"][f"{index} -{count}"] = urls
                else:
                    data[f"{os.path.basename(base_dir)}"]["urls"][f"{index}"] = urls
            logging.info(f"{Fore.GREEN}Processed {file_name}: {len(urls) + 200 * (count - 1)} URLs")

    return data
def save_to_json(data, output_file):
    """将数据保存为 JSON 文件"""
    with open(output_file, 'w' ,encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4, ensure_ascii=False)
    logging.info(f"{Fore.CYAN}Data saved to {output_file}")
def merge_txt_files(folder_path,output_file):
    """
    将指定文件夹内所有 .txt 文件中的链接合并到一个以文件夹名称命名的新 .txt 文件中。
    """
    # 打开新文件用于写入
    with open(output_file, 'w') as outfile:
        # 遍历文件夹中的所有 .txt 文件
        for file_name in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file_name)
            # 确保文件是 .txt 文件
            if os.path.isfile(file_path) and file_name.endswith('.txt'):
                with open(file_path, 'r') as infile:
                    # 读取每行内容并写入到新文件中
                    for line in infile:
                        outfile.write(line)

    logging.info(f"所有链接已合并到 {output_file} 文件中。")

if __name__ == "__main__":
    # 配置日志记录
    log_format = '%(log_color)s[%(levelname)s] %(message)s'
    formatter = colorlog.ColoredFormatter(log_format)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    base_directory = r''  # 替换为你的目录路径
    output_json_file = f'{os.path.basename(base_directory)}.json'  # 替换为你想要的输出文件名
    output_txt_file = f'{os.path.basename(base_directory)}.txt'
    data = convert_txt_to_json(base_directory)
    save_to_json(data, output_json_file)
    merge_txt_files(base_directory,output_txt_file)
