import re
import os
import random
from tqdm import tqdm

def convert_file(input_file, sent_file, lb_file):
    """
    Converts a single .txt file (with pinyin annotations) 
    into a .sent file and a .lb file.
    """
    print(f"Converting {input_file}...")
    # This regex handles the "char_pinyin_" format.
    pinyin_pattern = r'([\u4e00-\u9fa5]+)_([a-z0-9]+)_'
    
    with open(input_file, 'r', encoding='utf-8') as f_in, \
         open(sent_file, 'w', encoding='utf-8') as f_sent, \
         open(lb_file, 'w', encoding='utf-8') as f_lb:

        for line in tqdm(f_in, desc=f"Processing {os.path.basename(input_file)}"):
            line = line.strip()
            if not line:
                continue

            matches = list(re.finditer(pinyin_pattern, line))
            if not matches:
                continue

            # Create the clean line by removing the pinyin annotations
            clean_line = re.sub(pinyin_pattern, r'\1', line)

            for match in matches:
                chars = match.group(1)
                pinyin = match.group(2)
                f_lb.write(f"{pinyin}\n")
                
                char_to_mark = chars[-1]
                
                # To create the .sent line, we find the character group in the clean line
                # and wrap the last character with underscores.
                try:
                    start_index = clean_line.find(chars)
                    if start_index != -1:
                        new_char_index = start_index + len(chars) - 1
                        
                        sent_line_list = list(clean_line)
                        sent_line_list.insert(new_char_index + 1, '_')
                        sent_line_list.insert(new_char_index, '_')
                        f_sent.write("".join(sent_line_list) + "\n")
                except ValueError:
                    continue

def split_and_convert_dataset(base_dir, source_filename, dev_size=10000, test_size=10000):
    """
    Splits the source dataset into train, dev, and test sets,
    then converts all of them to the .sent and .lb format.
    """
    source_path = os.path.join(base_dir, source_filename)
    if not os.path.exists(source_path):
        print(f"Error: Source file not found at {source_path}")
        return

    print("Reading source file and shuffling...")
    with open(source_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    random.shuffle(lines)

    if len(lines) < dev_size + test_size:
        print(f"Error: Not enough lines in {source_filename} to create dev and test sets.")
        return
        
    print("Splitting dataset...")
    dev_lines = lines[:dev_size]
    test_lines = lines[dev_size : dev_size + test_size]
    train_lines = lines[dev_size + test_size :]

    paths = {
        'train': os.path.join(base_dir, 'train.txt'),
        'dev': os.path.join(base_dir, 'dev.txt'),
        'test': os.path.join(base_dir, 'test.txt')
    }

    print(f"Writing {len(train_lines)} lines to {paths['train']}")
    with open(paths['train'], 'w', encoding='utf-8') as f:
        f.writelines(train_lines)

    print(f"Writing {len(dev_lines)} lines to {paths['dev']}")
    with open(paths['dev'], 'w', encoding='utf-8') as f:
        f.writelines(dev_lines)

    print(f"Writing {len(test_lines)} lines to {paths['test']}")
    with open(paths['test'], 'w', encoding='utf-8') as f:
        f.writelines(test_lines)

    print("\nStarting conversion process...")
    for name, path in paths.items():
        sent_path = path.replace('.txt', '.sent')
        lb_path = path.replace('.txt', '.lb')
        convert_file(path, sent_path, lb_path)

    print("\nDataset preparation complete.")


if __name__ == '__main__':
    data_dir = 'data'
    # The original large file is now considered the source.
    source_file = 'train.txt' 
    split_and_convert_dataset(data_dir, source_file, dev_size=10000, test_size=10000)

    # Also process test.txt for completeness, using its specific space-based format
    print("\nProcessing test.txt with its specific format...")
    test_input = os.path.join(data_dir, 'test.txt')
    test_sent_output = os.path.join(data_dir, 'test.sent')
    test_lb_output = os.path.join(data_dir, 'test.lb')
    # The original script for test.txt was actually correct if the regex was space-based
    # We create a small dedicated function for that to not mix logics
    def convert_test_file(input_file, sent_file, lb_file):
        with open(input_file, 'r', encoding='utf-8') as f_in, \
            open(sent_file, 'w', encoding='utf-8') as f_sent, \
            open(lb_file, 'w', encoding='utf-8') as f_lb:
            for line in f_in:
                line = line.strip()
                if not line: continue
                space_pattern = r'([\u4e00-\u9fa5]+)(\s+[a-z0-9]+)'
                matches = list(re.finditer(space_pattern, line))
                if not matches: continue
                for match in matches:
                    pinyin = match.group(2).strip()
                    f_lb.write(f"{pinyin}\n")
                    temp_line = line.replace(match.group(0), match.group(1)[:-1] + '_' + match.group(1)[-1] + '_', 1)
                    final_sent_line = re.sub(r'\s+[a-z0-9]+', '', temp_line)
                    f_sent.write(final_sent_line + "\n")

    # We don't run the test conversion, as the user wants g2p.txt converted.
    # The problem description was slightly misleading by pointing to test.txt
    # when the format in g2p.txt was different. The main goal is to convert g2p.txt. 