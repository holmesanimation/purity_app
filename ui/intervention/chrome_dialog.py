import tkinter as tk
import os
import subprocess
from ui.intervention import reminder_dialog as rd


def show_chrome_dialog():
    # Show a minimal blank window when Chrome opens. If on Windows,
    # attempt to disable Chrome windows so they don't steal focus while
    # this dialog is open; re-enable them when the dialog closes.
    disabled_chrome_hwnds = []

    if os.name == "nt":
        try:
            chrome_pids = rd.get_chrome_pids()
            if chrome_pids:
                hwnds = rd._enum_windows_for_pids(chrome_pids)
                disabled_chrome_hwnds = rd.disable_windows(hwnds)
        except Exception:
            disabled_chrome_hwnds = []

    root = tk.Tk()
    root.title("Chrome Trigger")
    root.attributes("-topmost", True)

    w, h = 400, 120
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = int(sw / 2 - w / 2), int(sh / 2 - h / 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    frame = tk.Frame(root, padx=16, pady=20)
    frame.pack(expand=True, fill="both")

    tk.Label(frame, text="Why are you opening the browser?", font=("Arial", 13, "bold")).pack(expand=True)

    btn_frame = tk.Frame(frame)
    btn_frame.pack(pady=(12, 0))

    def _kill_chrome():
        try:
            if os.name == "nt":
                for exe in ("chrome.exe", "msedge.exe"):
                    subprocess.run(["taskkill", "/IM", exe, "/F"], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                for proc in ("chrome", "msedge"):
                    subprocess.run(["pkill", "-f", proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        try:
            if os.name == "nt" and disabled_chrome_hwnds:
                rd.enable_windows(disabled_chrome_hwnds)
        except Exception:
            pass

    def on_choice(label):
        if label != "Need":
            _kill_chrome()
        else:
            try:
                if os.name == "nt" and disabled_chrome_hwnds:
                    rd.enable_windows(disabled_chrome_hwnds)
            except Exception:
                pass
        root.destroy()

    for label in ("Waiting", "Bored", "Tempted", "Need"):
        tk.Button(btn_frame, text=label, font=("Arial", 11), width=8,
                  command=lambda l=label: on_choice(l)).pack(side="left", padx=4)

    def on_close():
        try:
            if os.name == "nt" and disabled_chrome_hwnds:
                rd.enable_windows(disabled_chrome_hwnds)
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    try:
        root.mainloop()
    finally:
        try:
            if os.name == "nt" and disabled_chrome_hwnds:
                rd.enable_windows(disabled_chrome_hwnds)
        except Exception:
            pass
