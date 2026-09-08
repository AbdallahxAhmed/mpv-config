#!/usr/bin/env python3
"""
vtt_translate.py - Plug-and-play WebVTT Subtitle Translator
Translates WebVTT subtitles directly into target languages (e.g. Arabic)
without requiring cookies, API keys, or browser sessions.
"""

import sys
import os
import re
import json
import argparse
import urllib.request
import urllib.parse

def clean_cue_text(text):
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()

def parse_vtt(content):
    cues = []
    in_cue = False
    
    for line in content.splitlines():
        line_clean = line.strip()
        if '-->' in line:
            in_cue = True
            cues.append({'timing': line, 'lines': []})
        elif in_cue:
            if line_clean == '':
                in_cue = False
            else:
                cleaned = clean_cue_text(line_clean)
                if cleaned:
                    cues[-1]['lines'].append(cleaned)
            
    return cues

def batch_translate(texts, src='en', dst='ar'):
    if not texts:
        return []
    delimiter = '\n=====\n'
    combined = delimiter.join(texts)
    url = (
        'https://clients5.google.com/translate_a/t?client=dict-chrome-ex'
        f'&sl={src}&tl={dst}&q=' + urllib.parse.quote(combined)
    )
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/130.0.0.0 Safari/537.36'
            )
        }
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        res_text = data[0] if isinstance(data, list) else str(data)
        parts = res_text.split('=====')
        return [p.strip() for p in parts]

def translate_vtt_file(input_path, output_path, target_lang='ar', source_lang='en'):
    with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    cues = parse_vtt(content)
    if not cues:
        raise ValueError("No subtitle cues found in input file.")

    all_phrases = []
    for cue in cues:
        for line in cue['lines']:
            if line and not line.startswith('['):
                all_phrases.append(line)

    unique_phrases = list(dict.fromkeys(all_phrases))
    translations = {}

    chunk_size = 50
    for i in range(0, len(unique_phrases), chunk_size):
        chunk = unique_phrases[i:i + chunk_size]
        try:
            translated_chunk = batch_translate(chunk, src=source_lang, dst=target_lang)
            for orig, trans in zip(chunk, translated_chunk):
                translations[orig] = trans
        except Exception as e:
            sys.stderr.write(f"Warning: batch translation error: {e}\n")
            for orig in chunk:
                translations[orig] = orig

    out_lines = [
        'WEBVTT\n',
        'Kind: captions\n',
        f'Language: {target_lang}\n\n'
    ]
    for cue in cues:
        out_lines.append(cue['timing'] + '\n')
        for line in cue['lines']:
            out_lines.append(translations.get(line, line) + '\n')
        out_lines.append('\n')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

def main():
    parser = argparse.ArgumentParser(description="Translate WebVTT subtitle files")
    parser.add_argument('--input', required=True, help="Input WebVTT file path")
    parser.add_argument('--output', required=True, help="Output WebVTT file path")
    parser.add_argument('--target', default='ar', help="Target language code (default: ar)")
    parser.add_argument('--source', default='en', help="Source language code (default: en)")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        sys.stderr.write(f"Error: input file '{args.input}' not found.\n")
        sys.exit(1)

    try:
        translate_vtt_file(args.input, args.output, args.target, args.source)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Error translating subtitle: {e}\n")
        sys.exit(2)

if __name__ == '__main__':
    main()
