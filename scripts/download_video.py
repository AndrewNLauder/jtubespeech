import os
import os.path
import time
import argparse
import sys
import subprocess
import shutil
import pydub
from pathlib import Path
from util import make_video_url, make_basename, vtt2txt, autovtt2txt
import pandas as pd
from tqdm import tqdm
from langdetect import detect

def parse_args():
  parser = argparse.ArgumentParser(
    description="Downloading videos with subtitle.",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
  )
  parser.add_argument("lang",         type=str, help="language code (ja, en, ...)")
  parser.add_argument("sublist",      type=str, help="filename of list of video IDs with subtitles")  
  parser.add_argument("--outdir",     type=str, default="video", help="dirname to save videos")
  parser.add_argument("--keeporg",    action='store_true', default=False, help="keep original audio file.")
  return parser.parse_args(sys.argv[1:])

def download_video(lang, fn_sub, outdir="video", wait_sec=10, keep_org=False):
  """
  Tips:
    If you want to download automatic subtitles instead of manual subtitles, please change as follows.
      1. replace "sub[sub["sub"]==True]" of for-loop with "sub[sub["auto"]==True]"
      2. replace "--write-sub" option of youtube-dl with "--write-auto-sub"
      3. replace vtt2txt() with autovtt2txt()
      4 (optional). change fn["vtt"] (path to save subtitle) to another. 
  """

  sub = pd.read_csv(fn_sub)

  for videoid in tqdm(sub[sub["sub"]==True]["videoid"]): # manual subtitle only
    print(f"download_video: {videoid}")
    check_dir1 = Path(outdir) / lang / "wav16k" / (make_basename(videoid))
    print(f"check_dir1: {check_dir1}")
    isdir1 = os.path.isdir(check_dir1)
    check_dir2 = Path(outdir) / lang / "start" / (make_basename(videoid))
    print(f"check_dir2: {check_dir2}")
    isdir2 = os.path.isdir(check_dir2)
    if isdir1:
      print(f"videoid: {videoid} already downloaded and processed, skipping")
      continue
    if isdir2:
      print(f"videoid: {videoid} tried to download but must have failed, skipping")
      continue
    os.makedirs(check_dir2, exist_ok=True) #### create "start" dir for all downloads, in case they fail we can skip them next run
    fn = {}
    for k in ["wav", "wav16k", "vtt", "txt"]:
      fn[k] = Path(outdir) / lang / k / (make_basename(videoid) + "." + k[:3])
      fn[k].parent.mkdir(parents=True, exist_ok=True)

    if not fn["wav16k"].exists() or not fn["txt"].exists():
      print(videoid)

      # get title of video
      url = make_video_url(videoid)
      title = subprocess.run(["youtube-dl", "-e", url], capture_output=True, text=True, universal_newlines=True)
      print(title.stdout.lower())
      if title.stdout == "":
        print("no title")
        continue
      langid = detect(title.stdout.lower())
      print(langid)
      if langid != lang:
        print("Video title is not " + lang)
        continue
      
      # download
      base = fn["wav"].parent.joinpath(fn["wav"].stem)
      cp = subprocess.run(f"youtube-dl --sub-lang {lang} --extract-audio --audio-format wav --write-sub {url} -o {base}.\%\(ext\)s", shell=True,universal_newlines=True)
      if cp.returncode != 0:
        print(f"Failed to download the video: url = {url}")
        continue
      try:
        shutil.move(f"{base}.{lang}.vtt", fn["vtt"])
      except Exception as e:
        print(f"Failed to rename subtitle file. The download may have failed: url = {url}, filename = {base}.{lang}.vtt, error = {e}")
        continue

      # vtt -> txt (reformatting)
      try:
        txt = vtt2txt(open(fn["vtt"], "r").readlines())
        with open(fn["txt"], "w") as f:
          f.writelines([f"{t[0]:1.3f}\t{t[1]:1.3f}\t\"{t[2]}\"\n" for t in txt])
      except Exception as e:
        print(f"Falied to convert subtitle file to txt file: url = {url}, filename = {fn['vtt']}, error = {e}")
        continue

      # wav -> wav16k (resampling to 16kHz, 1ch)
      try:
        wav = pydub.AudioSegment.from_file(fn["wav"], format = "wav")
        wav = pydub.effects.normalize(wav, 5.0).set_frame_rate(16000).set_channels(1)
        wav.export(fn["wav16k"], format="wav", bitrate="16k")
      except Exception as e:
        print(f"Failed to normalize or resample downloaded audio: url = {url}, filename = {fn['wav']}, error = {e}")
        continue

      # remove original wav
      if not keep_org:
        fn["wav"].unlink()

      # wait
      if wait_sec > 0.01:
        time.sleep(wait_sec)

  print("download_video finished")
  os.mknod('.finished') #### create .finished file
 
  return Path(outdir) / lang

if __name__ == "__main__":
  args = parse_args()

  dirname = download_video(args.lang, args.sublist, args.outdir)
  print(f"save {args.lang.upper()} videos to {dirname}.")

