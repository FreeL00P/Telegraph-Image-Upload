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
                new_key = f"{index} -{count}"
                data[f"{os.path.basename(base_dir)}"]["urls"][new_key] = urls[:200]
                urls = urls[200:]  # 剩余 URL
                count += 1

            # 添加剩余的 URL（如果有）
            if urls:
                data[f"{os.path.basename(base_dir)}"]["urls"][f"{index} -{count}"] = urls

            logging.info(f"{Fore.GREEN}Processed {file_name}: {len(urls) + 200 * (count - 1)} URLs")

    return data

def save_to_json(data, output_file):
    """将数据保存为 JSON 文件"""
    with open(output_file, 'w') as json_file:
        json.dump(data, json_file, indent=4, ensure_ascii=False)
    logging.info(f"{Fore.CYAN}Data saved to {output_file}")

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

    data = convert_txt_to_json(base_directory)
    save_to_json(data, output_json_file)
