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

import concurrent.futures

def clean_cue_text(text):
    # Strip inline timestamp tags like <00:00:19.039> or formatting tags like <c>, </c>
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()

def parse_vtt(content):
    blocks = re.split(r'\r?\n\r?\n+', content.strip())
    cues = []
    last_text = None
    
    def is_overlap(line1, prev_text):
        if not line1 or not prev_text:
            return False
        l1 = line1.strip()
        p = prev_text.strip()
        return l1 == p or l1.endswith(p) or p.endswith(l1) or l1.startswith(p)
    
    for block in blocks:
        lines = block.strip().splitlines()
        timing_idx = None
        for i, line in enumerate(lines):
            if '-->' in line:
                timing_idx = i
                break
        if timing_idx is None:
            continue
            
        timing_line = lines[timing_idx].strip()
        m = re.search(r'((\d{2}:)?\d{2}:\d{2}[.,]\d{3}\s*-->\s*(\d{2}:)?\d{2}:\d{2}[.,]\d{3})', timing_line)
        if not m:
            continue
            
        # Clean timing line to standard START --> END (stripping fragile align:start position:0% tags)
        clean_timing = m.group(1).replace(',', '.')
        
        # Calculate duration to filter out microscopic karaoke flash cues (< 80ms)
        tm = re.search(r'(\d{2}:)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}:)?(\d{2}):(\d{2})\.(\d{3})', clean_timing)
        if tm:
            def to_secs(h, m, s, ms):
                hrs = int(h[:-1]) if h else 0
                return hrs * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
            start_s = to_secs(tm.group(1), tm.group(2), tm.group(3), tm.group(4))
            end_s = to_secs(tm.group(5), tm.group(6), tm.group(7), tm.group(8))
            if (end_s - start_s) < 0.08:
                continue

        cue_lines = []
        for line in lines[timing_idx + 1:]:
            cleaned = clean_cue_text(line)
            if cleaned:
                cue_lines.append(cleaned)
                
        if not cue_lines:
            continue

        # De-roll: if line 0 overlaps the previous cue, it's YouTube rolling ASR teleprompter
        if len(cue_lines) >= 2 and is_overlap(cue_lines[0], last_text):
            final_lines = [cue_lines[-1]]
        else:
            final_lines = cue_lines

        full_text = ' '.join(final_lines)
        # Avoid duplicate identical text right after each other
        if cues and cues[-1]['lines'] == final_lines:
            # Extend previous cue duration instead of creating a duplicate flash
            prev_m = re.search(r'((\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->', cues[-1]['timing'])
            curr_end_m = re.search(r'-->\s*((\d{2}:)?\d{2}:\d{2}\.\d{3})', clean_timing)
            if prev_m and curr_end_m:
                cues[-1]['timing'] = f"{prev_m.group(1)} --> {curr_end_m.group(1)}"
            continue

        cues.append({'timing': clean_timing, 'lines': final_lines})
        last_text = final_lines[-1]
            
    return cues

def batch_translate(texts, src='en', dst='ar'):
    if not texts:
        return []
    delimiter = '\n=====\n'
    combined = delimiter.join(texts)
    url = f'https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl={src}&tl={dst}'
    data = urllib.parse.urlencode({'q': combined}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/130.0.0.0 Safari/537.36'
            )
        }
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        res_text = res[0] if isinstance(res, list) else str(res)
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
    chunks = [unique_phrases[i:i + chunk_size] for i in range(0, len(unique_phrases), chunk_size)]

    def translate_worker(chunk):
        try:
            translated = batch_translate(chunk, src=source_lang, dst=target_lang)
            return chunk, translated
        except Exception as e:
            sys.stderr.write(f"Warning: batch translation error: {e}\n")
            return chunk, chunk

    max_workers = min(8, max(1, len(chunks)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(translate_worker, chunk) for chunk in chunks]
        for f in concurrent.futures.as_completed(futures):
            orig_chunk, trans_chunk = f.result()
            for orig, trans in zip(orig_chunk, trans_chunk):
                translations[orig] = trans

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

def clean_vtt_file(input_path, output_path, lang=''):
    with open(input_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    cues = parse_vtt(content)
    if not cues:
        raise ValueError("No subtitle cues found in input file.")

    out_lines = [
        'WEBVTT\n',
        'Kind: captions\n',
    ]
    if lang:
        out_lines.append(f'Language: {lang}\n\n')
    else:
        out_lines.append('\n')

    for cue in cues:
        out_lines.append(cue['timing'] + '\n')
        for line in cue['lines']:
            out_lines.append(line + '\n')
        out_lines.append('\n')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

def main():
    if sys.platform == 'win32':
        try:
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Translate WebVTT subtitle files")
    parser.add_argument('--input', required=True, help="Input WebVTT file path")
    parser.add_argument('--output', required=True, help="Output WebVTT file path")
    parser.add_argument('--target', default='ar', help="Target language code (default: ar)")
    parser.add_argument('--source', default='en', help="Source language code (default: en)")
    parser.add_argument('--clean-only', action='store_true', help="Only clean and sanitize VTT without translating")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        sys.stderr.write(f"Error: input file '{args.input}' not found.\n")
        sys.exit(1)

    try:
        if args.clean_only or args.source == args.target:
            clean_vtt_file(args.input, args.output, args.target)
        else:
            translate_vtt_file(args.input, args.output, args.target, args.source)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Error processing subtitle: {e}\n")
        sys.exit(2)

if __name__ == '__main__':
    main()

