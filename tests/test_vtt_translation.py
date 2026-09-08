"""
Unit tests for tools/vtt_translate.py
Tests parsing, de-rolling (eliminating YouTube rolling sentence overlap),
micro-cue filtering, and WebVTT sanitation.
"""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from vtt_translate import parse_vtt, clean_cue_text, clean_vtt_file

class TestVttTranslation(unittest.TestCase):
    def test_clean_cue_text(self):
        self.assertEqual(clean_cue_text('<c>hello</c> world'), 'hello world')
        self.assertEqual(clean_cue_text('<00:00:01.234> test <00:00:02.000>'), 'test')
        self.assertEqual(clean_cue_text('normal text'), 'normal text')

    def test_de_rolling_eliminates_overlap(self):
        # Simulated YouTube ASR rolling teleprompter WebVTT
        sample_vtt = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000
I told him at the time, what do you want?

00:00:03.000 --> 00:00:05.000
I told him at the time, what do you want?
At this time, Germany is collapsing

00:00:05.000 --> 00:00:07.000
At this time, Germany is collapsing
Germany is on the brink of economic crisis
"""
        cues = parse_vtt(sample_vtt)
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[0]['lines'], ['I told him at the time, what do you want?'])
        self.assertEqual(cues[1]['lines'], ['At this time, Germany is collapsing'])
        self.assertEqual(cues[2]['lines'], ['Germany is on the brink of economic crisis'])

    def test_filter_micro_flash_cues(self):
        # 30ms flash cue should be dropped
        sample_vtt = """WEBVTT

00:00:01.000 --> 00:00:01.030
Flash

00:00:02.000 --> 00:00:05.000
Real sentence
"""
        cues = parse_vtt(sample_vtt)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0]['lines'], ['Real sentence'])

    def test_consecutive_duplicate_merging(self):
        # Same text consecutive cues should merge into single prolonged cue
        sample_vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
Hold this sentence

00:00:03.000 --> 00:00:05.000
Hold this sentence
"""
        cues = parse_vtt(sample_vtt)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0]['timing'], '00:00:01.000 --> 00:00:05.000')
        self.assertEqual(cues[0]['lines'], ['Hold this sentence'])

if __name__ == '__main__':
    unittest.main()
