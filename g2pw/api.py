import os
import json
import requests
import zipfile
from io import BytesIO
import shutil

import torch
from torch.utils.data import DataLoader
from transformers import BertTokenizer
from tqdm import tqdm
import numpy as np

from g2pw.dataset import TextDataset, get_phoneme_labels, get_char_phoneme_labels
from g2pw.utils import load_config
from g2pw.module import G2PW

MODEL_URL = 'https://storage.googleapis.com/esun-ai/g2pW/G2PWModel-v2-onnx.zip'

# --- PyTorch-based prediction function ---
def predict_pytorch(model, dataloader, labels, device, turnoff_tqdm=False):
    model.eval()
    all_preds = []
    all_confidences = []

    with torch.no_grad():
        for batch in tqdm(dataloader, disable=turnoff_tqdm):
            input_ids = batch['input_ids'].to(device)
            token_type_ids = batch['token_type_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            phoneme_mask = batch['phoneme_mask'].to(device)
            char_ids = batch['char_ids'].to(device)
            position_ids = batch['position_ids'].to(device)
            pos_ids = batch.get('pos_ids')
            if pos_ids is not None:
                pos_ids = pos_ids.to(device)

            probs = model(
                input_ids=input_ids,
                token_type_ids=token_type_ids,
                attention_mask=attention_mask,
                phoneme_mask=phoneme_mask,
                char_ids=char_ids,
                position_ids=position_ids,
                pos_ids=pos_ids
            )
            
            # Get predictions and confidences
            preds = torch.argmax(probs, dim=-1)
            max_probs = probs.gather(1, preds.unsqueeze(1)).squeeze(1)

            all_preds += [labels[pred] for pred in preds.tolist()]
            all_confidences += max_probs.cpu().tolist()
            
    return all_preds, all_confidences


# --- ONNX-based prediction (original) ---
def predict_onnx(onnx_session, dataloader, labels, turnoff_tqdm=False):
    all_preds = []
    all_confidences = []

    generator = dataloader if turnoff_tqdm else tqdm(dataloader, desc='predict')
    for data in generator:
        input_ids, token_type_ids, attention_mask, phoneme_mask, char_ids, position_ids = \
            [data[name] for name in ('input_ids', 'token_type_ids', 'attention_mask', 'phoneme_mask', 'char_ids', 'position_ids')]

        probs = onnx_session.run(
            [],
            {
                'input_ids': input_ids.numpy(),
                'token_type_ids': token_type_ids.numpy(),
                'attention_mask': attention_mask.numpy(),
                'phoneme_mask': phoneme_mask.numpy(),
                'char_ids': char_ids.numpy(),
                'position_ids': position_ids.numpy()
            }
        )[0]

        preds = np.argmax(probs, axis=-1)
        max_probs = probs[np.arange(probs.shape[0]), preds]

        all_preds += [labels[pred] for pred in preds.tolist()]
        all_confidences += max_probs.tolist()

    return all_preds, all_confidences


def download_model(model_dir):
    root = os.path.dirname(os.path.abspath(model_dir))

    r = requests.get(MODEL_URL, allow_redirects=True)
    zip_file = zipfile.ZipFile(BytesIO(r.content))
    zip_file.extractall(root)
    source_dir = os.path.join(root, zip_file.namelist()[0].split('/')[0])
    shutil.move(source_dir, model_dir)


class G2PWConverter:
    def __init__(self, model_dir='G2PWModel/', style='bopomofo', model_source=None, num_workers=None, batch_size=None,
                 turnoff_tqdm=True, enable_non_tradional_chinese=False, 
                 use_onnx=True, checkpoint_path=None, use_compile=True, use_pos=True):

        self.use_onnx = use_onnx
        self.use_pos = use_pos
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Shared setup
        self.config = load_config(os.path.join(model_dir, 'config.py'), use_default=True)
        if not hasattr(self.config, 'param_conditional'):
            self.config.param_conditional = {'affect_location': 'emb', 'char-linear': True, 'pos-linear': True, 'char+pos-second': True, 'bias': True}
        if not hasattr(self.config, 'param_pos'):
            self.config.param_pos = {'pos_joint_training': False}
        self.num_workers = num_workers if num_workers is not None else self.config.num_workers
        self.batch_size = batch_size if batch_size else self.config.batch_size
        self.turnoff_tqdm = turnoff_tqdm
        
        # The original logic incorrectly prioritized model_source from config over the local checkpoint.
        # We now use the provided checkpoint_path to load the model directly,
        # and model_source is only used for loading the correct tokenizer.
        # This ensures we are using our specific, fine-tuned model.
        if model_source:
             self.tokenizer = BertTokenizer.from_pretrained(model_source)
        else:
             self.tokenizer = BertTokenizer.from_pretrained(self.config.model_source)

        polyphonic_chars_path = os.path.join(model_dir, 'POLYPHONIC_CHARS.txt')
        monophonic_chars_path = os.path.join(model_dir, 'MONOPHONIC_CHARS.txt')
        self.polyphonic_chars = [line.split('\t') for line in open(polyphonic_chars_path, 'r', encoding='utf-8').read().strip().split('\n')]
        self.monophonic_chars = [line.split('\t') for line in open(monophonic_chars_path, 'r', encoding='utf-8').read().strip().split('\n')]
        self.labels, self.char2phonemes = get_char_phoneme_labels(self.polyphonic_chars) if self.config.use_char_phoneme else get_phoneme_labels(self.polyphonic_chars)
        self.chars = sorted(list(self.char2phonemes.keys()))

        if self.use_onnx:
            import onnxruntime
            if not os.path.exists(os.path.join(model_dir, 'g2pw.onnx')):
                # Original download logic for onnx model
                download_model(model_dir)
            sess_options = onnxruntime.SessionOptions()
            self.session_g2pw = onnxruntime.InferenceSession(os.path.join(model_dir, 'g2pw.onnx'), sess_options=sess_options)
            self.predict_func = predict_onnx
        else:
            # PyTorch model loading
            if checkpoint_path is None:
                raise ValueError("checkpoint_path must be provided when use_onnx is False.")

            # Correct initialization: Use from_pretrained to build the model structure,
            # then immediately load our specific weights from the checkpoint_path.
            self.model = G2PW.from_pretrained(
                self.config.model_source,  # Use model_source to define the architecture
                labels=self.labels,
                chars=self.chars,
                pos_tags=TextDataset.POS_TAGS,
                use_conditional=self.config.use_conditional,
                param_conditional=self.config.param_conditional,
                use_pos=self.use_pos,
                param_pos=self.config.param_pos # Pass the pos params as well
            )
            
            # Load state dict with strict=False to ignore unexpected keys like 'pos_classifier'
            self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device, weights_only=True), strict=False)
            self.model.to(self.device)
            
            # Add torch.compile() for optimization
            if use_compile and self.device.type == 'cuda':
                try:
                    # This requires PyTorch 2.0+
                    self.model = torch.compile(self.model)
                    print("Model successfully compiled with torch.compile() for optimized performance.")
                except Exception as e:
                    print(f"Warning: Failed to apply torch.compile(). The model will run without this optimization. Error: {e}")
            elif use_compile:
                print("Info: torch.compile() is only applied for CUDA devices. Running on CPU without compilation.")

            self.predict_func = predict_pytorch

        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'bopomofo_to_pinyin_wo_tune_dict.json'), 'r', encoding='utf-8') as fr:
            self.bopomofo_convert_dict = json.load(fr)
        self.style_convert_func = {
            'bopomofo': lambda x: x,
            'pinyin': self._convert_bopomofo_to_pinyin,
        }[style]

        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'char_bopomofo_dict.json'), 'r', encoding='utf-8') as fr:
            self.char_bopomofo_dict = json.load(fr)

        self.enable_non_tradional_chinese = enable_non_tradional_chinese
        if self.enable_non_tradional_chinese:
            self.s2t_dict = {}
            for line in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    'bert-base-chinese_s2t_dict.txt'), 'r', encoding='utf-8').read().strip().split('\n'):
                s_char, t_char = line.split('\t')
                self.s2t_dict[s_char] = t_char

    def _convert_bopomofo_to_pinyin(self, bopomofo):
        tone = bopomofo[-1]
        assert tone in '12345'
        component = self.bopomofo_convert_dict.get(bopomofo[:-1])
        if component:
            return component + tone
        else:
            print(f'Warning: "{bopomofo}" cannot convert to pinyin')
            return None

    def _convert_s2t(self, sentence):
        return ''.join([self.s2t_dict.get(char, char) for char in sentence])

    def __call__(self, sentences):
        if isinstance(sentences, str):
            sentences = [sentences]

        if self.enable_non_tradional_chinese:
            translated_sentences = []
            for sent in sentences:
                translated_sent = self._convert_s2t(sent)
                assert len(translated_sent) == len(sent)
                translated_sentences.append(translated_sent)
            sentences = translated_sentences

        texts, query_ids, sent_ids, partial_results = self._prepare_data(sentences)
        if len(texts) == 0:
            # sentences no polyphonic words
            return partial_results

        dataset = TextDataset(self.tokenizer, self.labels, self.char2phonemes, self.chars, texts, query_ids,
                              use_mask=self.config.use_mask, use_char_phoneme=self.config.use_char_phoneme,
                              window_size=self.config.window_size, for_train=False, use_pos=self.use_pos)

        dataloader = DataLoader(
            dataset=dataset,
            batch_size=self.batch_size,
            collate_fn=dataset.create_mini_batch,
            num_workers=self.num_workers
        )

        # Use the appropriate prediction function
        if self.use_onnx:
            preds, confidences = self.predict_func(self.session_g2pw, dataloader, self.labels, turnoff_tqdm=self.turnoff_tqdm)
        else: # PyTorch
            preds, confidences = self.predict_func(self.model, dataloader, self.labels, self.device, turnoff_tqdm=self.turnoff_tqdm)

        if self.config.use_char_phoneme:
            preds = [pred.split(' ')[1] for pred in preds]

        results = partial_results
        for sent_id, query_id, pred in zip(sent_ids, query_ids, preds):
            results[sent_id][query_id] = self.style_convert_func(pred)

        return results

    def _prepare_data(self, sentences):
        polyphonic_chars = set(self.chars)
        monophonic_chars_dict = {
            char: phoneme for char, phoneme in self.monophonic_chars
        }
        texts, query_ids, sent_ids, partial_results = [], [], [], []
        for sent_id, sent in enumerate(sentences):
            partial_result = [None] * len(sent)
            for i, char in enumerate(sent):
                if char in polyphonic_chars:
                    texts.append(sent)
                    query_ids.append(i)
                    sent_ids.append(sent_id)
                elif char in monophonic_chars_dict:
                    partial_result[i] =  self.style_convert_func(monophonic_chars_dict[char])
                elif char in self.char_bopomofo_dict:
                    partial_result[i] =  self.style_convert_func(self.char_bopomofo_dict[char][0])
            partial_results.append(partial_result)
        return texts, query_ids, sent_ids, partial_results
