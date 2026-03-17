import json
import re
import os
import pandas as pd

def load_line_json_data(filename):
    data = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f.read().strip().split('\n'):
            unit = json.loads(line)
            data.append(unit)
    return data

def save_file(data, path):
    with open(path,'w',encoding='utf-8') as w:
        for unit in data:
            output = json.dumps(unit)
            w.write(output + "\n")
        w.close()

def extract_query_number(query_string):
    pattern = r"Query (\d+)"
    match = re.search(pattern, query_string)
    return int(match.group(1)) if match else None

def get_valid_name_city(info):
    # Adapted logic to handle various formats
    if not isinstance(info, str):
        return "-", "-"
    parts = info.rsplit(',', 1)
    if len(parts) == 2:
        name = parts[0].strip()
        city = extract_before_parenthesis(parts[1].strip())
        return name, city.strip()
    else:
        # Fallback or different format handling
        return info, "-"
    
def extract_numbers_from_filenames(directory):
    pattern = r'annotation_(\d+).json'
    files = os.listdir(directory)
    numbers = [int(re.search(pattern, file).group(1)) for file in files if re.match(pattern, file)]
    return numbers

def get_filtered_data(component,data, column_name=('Name','City')):
    name, city = get_valid_name_city(component)
    return data[(data[column_name[0]] == name) & (data[column_name[1]] == city)]

def extract_before_parenthesis(s):
    if not isinstance(s, str): return str(s)
    # Clean newlines and escaped newlines
    s = s.split('\n')[0].split('\\n')[0]
    match = re.search(r'^(.*?)\([^)]*\)', s)
    return match.group(1).strip() if match else s.strip()

def count_consecutive_values(lst):
    if not lst:
        return []

    result = []
    current_string = lst[0]
    count = 1

    for i in range(1, len(lst)):
        if lst[i] == current_string:
            count += 1
        else:
            result.append((current_string, count))
            current_string = lst[i]
            count = 1

    result.append((current_string, count))  # Add the last group of values
    return result
