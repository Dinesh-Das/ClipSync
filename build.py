"""
Build script for creating a Windows executable of ClipSync.

Usage:
    python build.py

This script will:
1. Install PyInstaller if missing.
2. Package the application with the icon and assets included.
3. Output the executable to `dist/ClipSync/ClipSync.exe`.
"""

import sys
import subprocess
import os
import shutil

def install_requirements():
    """Install build requirements."""
    print("Checking build requirements...")
    required = ["pyinstaller", "pillow"]
    for package in required:
        try:
            __import__(package)
        except ImportError:
            print(f"{package} not found. Installing...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

def find_ffmpeg():
    """Find ffmpeg/ffprobe executables."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe
        
    # Search common locations if not in PATH
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    search_patterns = [
        r"C:\Program Files\ffmpeg\bin",
        r"C:\ffmpeg\bin",
        os.path.join(local_app_data, r"Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin"),
        os.path.join(local_app_data, r"Microsoft\WinGet\Links"), 
    ]
    
    found_ffmpeg = None
    found_ffprobe = None
    
    import glob
    for pattern in search_patterns:
        for d in glob.glob(pattern):
            if not found_ffmpeg and os.path.exists(os.path.join(d, "ffmpeg.exe")):
                found_ffmpeg = os.path.join(d, "ffmpeg.exe")
            if not found_ffprobe and os.path.exists(os.path.join(d, "ffprobe.exe")):
                found_ffprobe = os.path.join(d, "ffprobe.exe")
    
    return found_ffmpeg, found_ffprobe

def clean_build_artifacts():
    """Clean previous build artifacts."""
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"Warning: Could not clean {folder}: {e}")
    
    spec_file = "ClipSync.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)

def build():
    install_requirements()
    
    # Ensure asset path is correct for --add-data
    sep = ";" if os.name == 'nt' else ":"
    assets_arg = f"assets{sep}assets"
    
    print("\nStarting build process...")
    
    import PyInstaller.__main__

    PyInstaller.__main__.run([
        'main.py',
        '--name=ClipSync',
        '--windowed',
        '--onedir',
        '--icon=assets/OP.jpg',
        f'--add-data={assets_arg}',
        '--clean',
        '--noconfirm',
        '--exclude-module=tkinter',
        '--exclude-module=matplotlib',
        '--exclude-module=notebook',
        '--exclude-module=scipy',
        '--exclude-module=pandas',
        '--exclude-module=numpy',
    ])
    
    # Copy FFmpeg if found
    ffmpeg, ffprobe = find_ffmpeg()
    dist_dir = os.path.abspath(os.path.join('dist', 'ClipSync'))
    
    if ffmpeg and ffprobe:
        print(f"\nFound FFmpeg at: {ffmpeg}")
        print("Copying FFmpeg binaries to output directory...")
        try:
            shutil.copy2(ffmpeg, dist_dir)
            shutil.copy2(ffprobe, dist_dir)
            print("✔ FFmpeg bundled successfully.")
        except Exception as e:
            print(f"⚠ Failed to copy FFmpeg: {e}")
    else:
        print("\n⚠ WARNING: FFmpeg not found on this system.")
        print("   The executable will be created, but video merging/conversion may fail.")
        print("   Please convert `ffmpeg.exe` and `ffprobe.exe` to the 'ClipSync' folder manually.")

    print("\n" + "="*50)
    print("Build Complete!")
    print("="*50)
    print(f"Your executable is located at:\n{dist_dir}\\ClipSync.exe")
    print("You can zip the 'dist/ClipSync' folder to share the application.")

if __name__ == "__main__":
    build()
