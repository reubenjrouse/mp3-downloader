#!/usr/bin/env python3
"""
run_workflow.py — fetch, tag, and rename MP3s from artist/song or album names.

No API keys required:
  - YouTube search + download via yt-dlp's keyless `ytsearch:` prefix.
  - Metadata + cover art via Apple's public iTunes Search/Lookup API.

Requires: yt-dlp, mutagen, requests, and ffmpeg on PATH.
"""

import argparse
import re
import sys
from pathlib import Path

import requests
import yt_dlp
from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TDRC, TRCK, APIC

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"


# ---------------------------------------------------------------------------
# Metadata lookup (iTunes)
# ---------------------------------------------------------------------------

def lookup_itunes(query):
    """Look up a single track on iTunes. Returns a metadata dict or None."""
    try:
        resp = requests.get(
            ITUNES_SEARCH_URL,
            params={"term": query, "media": "music", "entity": "song", "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except requests.RequestException as exc:
        print(f"  [!] iTunes lookup failed: {exc}")
        return None

    if not results:
        return None

    r = results[0]
    return {
        "title": r.get("trackName"),
        "artist": r.get("artistName"),
        "album": r.get("collectionName"),
        "year": (r.get("releaseDate") or "")[:4],
        "track_number": r.get("trackNumber"),
        "artwork_url": r.get("artworkUrl100"),
    }


def lookup_itunes_album(query):
    """Look up an album on iTunes and return its full, ordered tracklist."""
    try:
        resp = requests.get(
            ITUNES_SEARCH_URL,
            params={"term": query, "media": "music", "entity": "album", "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except requests.RequestException as exc:
        print(f"  [!] iTunes album search failed: {exc}")
        return None

    if not results:
        return None

    collection_id = results[0].get("collectionId")
    album_name = results[0].get("collectionName")
    artist_name = results[0].get("artistName")

    try:
        resp = requests.get(
            ITUNES_LOOKUP_URL,
            params={"id": collection_id, "entity": "song"},
            timeout=10,
        )
        resp.raise_for_status()
        entries = resp.json().get("results", [])
    except requests.RequestException as exc:
        print(f"  [!] iTunes album lookup failed: {exc}")
        return None

    tracks = []
    for e in entries:
        if e.get("wrapperType") != "track":
            continue
        tracks.append({
            "title": e.get("trackName"),
            "artist": e.get("artistName", artist_name),
            "album": e.get("collectionName", album_name),
            "year": (e.get("releaseDate") or "")[:4],
            "track_number": e.get("trackNumber"),
            "artwork_url": e.get("artworkUrl100"),
        })

    tracks.sort(key=lambda t: t.get("track_number") or 0)
    return tracks


# ---------------------------------------------------------------------------
# Download (yt-dlp)
# ---------------------------------------------------------------------------

def sanitize_filename(name):
    """Strip characters that are illegal in filenames on common filesystems."""
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


def download_audio(query, outdir, base_filename):
    """Search YouTube (keyless) for `query`, download best audio, convert to MP3.

    Returns the path to the resulting MP3 file, or None on failure.
    """
    outtmpl = str(outdir / f"{base_filename}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch1",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])
    except yt_dlp.utils.DownloadError as exc:
        print(f"  [!] Download failed: {exc}")
        return None

    mp3_path = outdir / f"{base_filename}.mp3"
    if mp3_path.exists():
        return mp3_path

    print(f"  [!] Expected output not found: {mp3_path}")
    return None


# ---------------------------------------------------------------------------
# Tag + rename (mutagen)
# ---------------------------------------------------------------------------

def fetch_artwork(artwork_url):
    """Fetch cover art bytes, bumping iTunes' default 100x100 URL to 600x600."""
    if not artwork_url:
        return None
    hi_res_url = artwork_url.replace("100x100bb", "600x600bb")
    try:
        resp = requests.get(hi_res_url, timeout=10)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException:
        return None


def tag_and_rename(mp3_path, metadata, outdir):
    """Write ID3 tags and rename the file to 'Artist - Title.mp3'
    (or 'NN - Artist - Title.mp3' for album tracks with a track number).
    """
    try:
        tags = ID3(mp3_path)
    except ID3NoHeaderError:
        tags = ID3()

    title = metadata.get("title") or mp3_path.stem
    artist = metadata.get("artist")
    album = metadata.get("album")
    year = metadata.get("year")
    track_number = metadata.get("track_number")

    tags.setall("TIT2", [TIT2(encoding=3, text=title)])
    if artist:
        tags.setall("TPE1", [TPE1(encoding=3, text=artist)])
    if album:
        tags.setall("TALB", [TALB(encoding=3, text=album)])
    if year:
        tags.setall("TDRC", [TDRC(encoding=3, text=year)])
    if track_number:
        tags.setall("TRCK", [TRCK(encoding=3, text=str(track_number))])

    artwork = fetch_artwork(metadata.get("artwork_url"))
    if artwork:
        tags.setall("APIC", [APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=artwork,
        )])

    tags.save(mp3_path, v2_version=3)

    if artist:
        new_name = f"{artist} - {title}.mp3"
    else:
        new_name = f"{title}.mp3"
    if track_number:
        new_name = f"{int(track_number):02d} - {new_name}"

    new_name = sanitize_filename(new_name)
    new_path = outdir / new_name

    if new_path != mp3_path:
        counter = 1
        while new_path.exists():
            stem = sanitize_filename(new_name[:-4])
            new_path = outdir / f"{stem} ({counter}).mp3"
            counter += 1
        mp3_path.rename(new_path)

    return new_path


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def process_track(query, outdir, metadata=None, index=None):
    """Download, tag, and rename a single track. `metadata` may be pre-fetched
    (e.g. from an album lookup); otherwise it is looked up here.
    """
    print(f"-> {query}")

    if metadata is None:
        metadata = lookup_itunes(query)
        if metadata is None:
            print("  [!] No iTunes match found, using raw query as title.")
            metadata = {"title": query, "artist": None, "album": None,
                        "year": None, "track_number": None, "artwork_url": None}

    search_query = query
    if metadata.get("artist") and metadata.get("title"):
        search_query = f"{metadata['artist']} - {metadata['title']}"

    base_filename = sanitize_filename(f"track_{index if index is not None else 0}_{search_query}")[:150]

    mp3_path = download_audio(search_query, outdir, base_filename)
    if mp3_path is None:
        print("  [!] Skipped.")
        return

    final_path = tag_and_rename(mp3_path, metadata, outdir)
    print(f"  [ok] {final_path.name}")


def process_album(query, outdir):
    print(f"=> Album: {query}")
    tracks = lookup_itunes_album(query)
    if not tracks:
        print("  [!] Album not found on iTunes. Skipping.")
        return

    album_name = tracks[0].get("album", query)
    album_artist = tracks[0].get("artist", "")
    print(f"  Found: {album_name} ({len(tracks)} tracks)")

    folder_name = sanitize_filename(f"{album_artist} - {album_name}" if album_artist else album_name)
    album_dir = outdir / folder_name
    album_dir.mkdir(parents=True, exist_ok=True)

    for i, track_meta in enumerate(tracks, start=1):
        title = track_meta.get("title") or "Unknown"
        artist = track_meta.get("artist") or ""
        process_track(f"{artist} - {title}", album_dir, metadata=track_meta, index=i)


def parse_entries(args_entries, file_path):
    entries = list(args_entries)
    if file_path:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                entries.append(line)
    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Download, tag, and rename MP3s from artist/song or album names."
    )
    parser.add_argument("entries", nargs="*", help="Song queries, or 'album:Name' for whole albums.")
    parser.add_argument("--file", "-f", help="File with one entry per line (# = comment).")
    parser.add_argument("--outdir", "-o", default="./mp3s", help="Output directory (default: ./mp3s).")
    args = parser.parse_args()

    entries = parse_entries(args.entries, args.file)
    if not entries:
        parser.error("No entries given. Provide song/album queries as arguments or via --file.")

    outdir = Path(args.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        if entry.lower().startswith("album:"):
            process_album(entry[len("album:"):].strip(), outdir)
        else:
            process_track(entry, outdir)


if __name__ == "__main__":
    sys.exit(main())
