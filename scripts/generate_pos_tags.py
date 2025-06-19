import re
import os
from tqdm import tqdm

# --- CKIP Tagger Initialization ---
# Make sure you have run "pip install -U ckiptagger[tf,gdown]"
# and downloaded the model data into the 'ckiptagger/data' directory.
try:
    from ckiptagger import WS, POS
    print("Loading CkipTagger models...")
    ws = WS("./ckiptagger/data", disable_cuda=True)
    pos = POS("./ckiptagger/data", disable_cuda=True)
    print("CkipTagger models loaded successfully.")
except (ImportError, FileNotFoundError) as e:
    print("="*40)
    print("ERROR: CkipTagger is not available or model data is missing.")
    print("Please make sure you have installed it (`pip install -U ckiptagger[tf,gdown]`)")
    print("and downloaded the model files to the './ckiptagger/data' directory.")
    print(f"Details: {e}")
    print("="*40)
    exit()

# --- POS Tag Mapping ---
# This dictionary maps CKIP's detailed POS tags to the 11-tag set used by G2PW.
# The mapping is based on CKIP's documentation and the G2PW model's requirements.
# CKIP tags starting with these prefixes will be mapped to the corresponding G2PW tag.
CKIP_TO_G2PW_MAPPING = {
    'A': 'A',     # Adjective
    'C': 'C',     # Conjunction
    'D': 'D',     # Adverb
    'I': 'I',     # Interjection
    'N': 'N',     # Noun
    'P': 'P',     # Preposition
    'T': 'T',     # Particle
    'V': 'V',     # Verb
    'DE': 'DE',   # "的"
    'SHI': 'SHI', # "是"
    # Anything else will be mapped to UNK
}

def get_g2pw_pos_tag(ckip_tag):
    """Maps a detailed CKIP POS tag to one of the 11 G2PW POS tags."""
    if ckip_tag == 'DE':
        return 'DE'
    if ckip_tag == 'SHI':
        return 'SHI'
    # Check prefixes for major categories
    for prefix, g2pw_tag in CKIP_TO_G2PW_MAPPING.items():
        if ckip_tag.startswith(prefix):
            return g2pw_tag
    # Default to UNK if no match is found
    return 'UNK'


def generate_pos_for_file(txt_path, sent_path, pos_path):
    """
    Generates a .pos file for a given .txt and .sent file pair.
    """
    print(f"\nProcessing {txt_path}...")

    if not os.path.exists(txt_path) or not os.path.exists(sent_path):
        print(f"Warning: Skipping POS generation for {os.path.basename(txt_path)} because source file is missing.")
        return

    with open(txt_path, 'r', encoding='utf-8') as f:
        txt_lines = f.readlines()
    with open(sent_path, 'r', encoding='utf-8') as f:
        sent_lines = f.readlines()
        
    if len(txt_lines) != len(sent_lines):
        print(f"Warning: Line count mismatch between {txt_path} and {sent_path}. POS generation might be inaccurate.")

    # Clean the source text lines by removing pinyin annotations
    pinyin_pattern = r'_[a-z0-9]+_'
    clean_txt_lines = [re.sub(pinyin_pattern, '', line.strip()) for line in txt_lines]

    print("Running Word Segmentation (WS) and Part-of-Speech (POS) tagging...")
    word_sentence_list = ws(clean_txt_lines, batch_size=128)
    pos_sentence_list = pos(word_sentence_list, batch_size=128)

    print("Extracting and mapping POS tags...")
    final_pos_tags = []
    for i in tqdm(range(len(sent_lines)), desc="Mapping tags"):
        sent_line = sent_lines[i].strip()
        
        # Find the polyphonic character marked with underscores
        poly_char_match = re.search(r'_([^_]+)_', sent_line)
        if not poly_char_match:
            final_pos_tags.append('UNK')
            continue
        
        poly_char = poly_char_match.group(1)
        poly_char_index = poly_char_match.start(0)

        # Find which word the polyphonic character belongs to
        words = word_sentence_list[i]
        tags = pos_sentence_list[i]
        
        char_cursor = 0
        found_tag = False
        for word, tag in zip(words, tags):
            word_start_index = char_cursor
            word_end_index = char_cursor + len(word)
            
            # Check if the polyphonic character's index falls within this word's span
            if word_start_index <= poly_char_index < word_end_index:
                g2pw_tag = get_g2pw_pos_tag(tag)
                final_pos_tags.append(g2pw_tag)
                found_tag = True
                break
            
            char_cursor = word_end_index
        
        if not found_tag:
            final_pos_tags.append('UNK')

    print(f"Writing {len(final_pos_tags)} tags to {pos_path}...")
    with open(pos_path, 'w', encoding='utf-8') as f:
        for tag in final_pos_tags:
            f.write(f"{tag}\n")


if __name__ == '__main__':
    data_dir = 'data'
    datasets = ['train', 'dev', 'test']

    for name in datasets:
        txt_file = os.path.join(data_dir, f'{name}.txt')
        sent_file = os.path.join(data_dir, f'{name}.sent')
        pos_file = os.path.join(data_dir, f'{name}.pos')
        
        generate_pos_for_file(txt_file, sent_file, pos_file)

    print("\nPOS tag generation complete for all datasets.") 