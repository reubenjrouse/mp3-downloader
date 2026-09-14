<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/e5e0b2c6-dc96-4f85-837d-aa48b5336dad">
    <img src="https://github.com/user-attachments/assets/e5e0b2c6-dc96-4f85-837d-aa48b5336dad" width="300" alt="mp3-player">
  </picture>
</p>

# mp3-downloader

A CLI tool that downloads, tags, and renames MP3s from artist/song or album
names. I built this because manually downloading-converting-tagging-renaming every song by hand got old fast.
Feel free to use it if you've run into the same problem.

## Requirements

- Python 3
- [ffmpeg](https://ffmpeg.org/) on PATH
- Python packages: `pip install -r requirements.txt`

## Usage

```
# single songs
python run_workflow.py "Radiohead - Karma Police" "Daft Punk - One More Time"

# whole album (own subfolder, ordered tracklist, track numbers embedded)
python run_workflow.py "album:Daft Punk - Discovery"

# mix songs and albums, or use a file (one entry per line, # = comment)
python run_workflow.py --file songs.txt

# custom output folder (default: ./mp3s)
python run_workflow.py "Bohemian Rhapsody" -o ~/Music/mp3-player
```

## Notes

- YouTube's top search hit isn't always the "correct" studio version —
worth spot-checking anything unusual (covers, remixes, live albums).
