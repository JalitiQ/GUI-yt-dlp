import customtkinter as ctk
import threading
import os
import sys
import yt_dlp


def _bundled_ffmpeg_dir():
    """Répertoire contenant le ffmpeg embarqué quand l'app est packagée
    par PyInstaller. Renvoie None si on tourne depuis les sources
    (yt-dlp utilisera alors le ffmpeg du système)."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        for name in ("ffmpeg", "ffmpeg.exe"):
            if os.path.exists(os.path.join(base, name)):
                return base
    return None


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DownloaderYT")
        self.geometry("620x480")
        self.minsize(480, 400)
        self._output_dir = os.path.expanduser("~/Téléchargements")
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 20, "pady": (10, 0)}

        # URL
        ctk.CTkLabel(self, text="URL YouTube", anchor="w").pack(fill="x", **pad)
        self._url_entry = ctk.CTkEntry(self, placeholder_text="https://www.youtube.com/watch?v=...")
        self._url_entry.pack(fill="x", padx=20, pady=(4, 0))

        # Format + qualité
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(12, 0))

        ctk.CTkLabel(row, text="Format").pack(side="left")
        self._fmt = ctk.CTkSegmentedButton(row, values=["MP4 (vidéo)", "MP3 (audio)"])
        self._fmt.set("MP4 (vidéo)")
        self._fmt.pack(side="left", padx=(8, 20))

        ctk.CTkLabel(row, text="Qualité").pack(side="left")
        self._quality = ctk.CTkOptionMenu(row, values=["Meilleure", "1080p", "720p", "480p", "360p"])
        self._quality.pack(side="left", padx=(8, 0))

        # Dossier de sortie
        dir_row = ctk.CTkFrame(self, fg_color="transparent")
        dir_row.pack(fill="x", padx=20, pady=(12, 0))

        ctk.CTkLabel(dir_row, text="Dossier :").pack(side="left")
        self._dir_label = ctk.CTkLabel(dir_row, text=self._output_dir, anchor="w", text_color="gray")
        self._dir_label.pack(side="left", padx=8, fill="x", expand=True)
        ctk.CTkButton(dir_row, text="Choisir", width=80, command=self._pick_dir).pack(side="right")

        # Bouton télécharger
        self._dl_btn = ctk.CTkButton(self, text="Télécharger", command=self._start_download)
        self._dl_btn.pack(pady=(18, 0))

        # Barre de progression
        self._progress = ctk.CTkProgressBar(self)
        self._progress.set(0)
        self._progress.pack(fill="x", padx=20, pady=(14, 0))

        # Log
        self._log = ctk.CTkTextbox(self, state="disabled", height=160)
        self._log.pack(fill="both", expand=True, padx=20, pady=(12, 16))

    def _pick_dir(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(initialdir=self._output_dir)
        if path:
            self._output_dir = path
            self._dir_label.configure(text=path)

    def _log_write(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _start_download(self):
        url = self._url_entry.get().strip()
        if not url:
            self._log_write("⚠  Entre une URL avant de télécharger.")
            return
        self._dl_btn.configure(state="disabled", text="Téléchargement…")
        self._progress.set(0)
        threading.Thread(target=self._download, args=(url,), daemon=True).start()

    def _download(self, url: str):
        fmt = self._fmt.get()
        quality = self._quality.get()
        is_audio = fmt.startswith("MP3")

        quality_map = {
            "Meilleure": "bestvideo+bestaudio",
            "1080p": "bestvideo[height<=1080]+bestaudio",
            "720p": "bestvideo[height<=720]+bestaudio",
            "480p": "bestvideo[height<=480]+bestaudio",
            "360p": "bestvideo[height<=360]+bestaudio",
        }

        def progress_hook(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                if total:
                    ratio = downloaded / total
                    self.after(0, lambda v=ratio: self._progress.set(v))
                speed = d.get("_speed_str", "")
                eta = d.get("_eta_str", "")
                msg = f"  {d.get('_percent_str', '').strip()}  {speed}  ETA {eta}"
                self.after(0, lambda m=msg: self._log_write(m))
            elif d["status"] == "finished":
                # Ce hook se déclenche AVANT la conversion ffmpeg : d["filename"]
                # pointe encore sur le fichier source (.webm/.m4a). On affiche
                # l'extension finale réelle pour ne pas induire en erreur.
                self.after(0, lambda: self._progress.set(1))
                base = os.path.splitext(os.path.basename(d["filename"]))[0]
                ext = "mp3" if is_audio else "mp4"
                self.after(0, lambda n=f"{base}.{ext}": self._log_write(f"✓  Fichier : {n}"))

        opts = {
            "outtmpl": os.path.join(self._output_dir, "%(title)s.%(ext)s"),
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            # Ne télécharger que la vidéo de l'URL, jamais la playlist/radio
            # (ex. les liens "&list=RD..." générés par YouTube).
            "noplaylist": True,
        }

        ffmpeg_dir = _bundled_ffmpeg_dir()
        if ffmpeg_dir:
            opts["ffmpeg_location"] = ffmpeg_dir

        if is_audio:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
        else:
            opts["format"] = quality_map.get(quality, "bestvideo+bestaudio")
            opts["merge_output_format"] = "mp4"

        self.after(0, lambda: self._log_write(f"→ Début : {url}"))
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self.after(0, lambda: self._log_write("✅ Téléchargement terminé !"))
        except Exception as e:
            self.after(0, lambda err=e: self._log_write(f"❌ Erreur : {err}"))
        finally:
            self.after(0, lambda: self._dl_btn.configure(state="normal", text="Télécharger"))


if __name__ == "__main__":
    App().mainloop()
