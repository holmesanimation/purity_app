import tkinter as tk
import random
import time
import threading
import math
import datetime
import json
import copy
from pathlib import Path
import os
import subprocess
from PIL import Image, ImageDraw

from shane_common.config.json_config import JsonConfigStore
from shane_common.events.jsonl import JsonlEventWriter

# -----------------------------
# CONFIG / DATA
# -----------------------------
REGULAR_INTERVAL_MINUTES = 50
LONG_BREAK_EVERY_MINUTES = 120

REGULAR_BREAK_SECONDS = 120
LONG_BREAK_SECONDS = 300

DAILY_WATER_GLASSES = 12
WAKE_HOUR = 7
SLEEP_HOUR = 22
LUNCH_HOUR = 12

LOG_DIR = Path.home() / "focus_guard_logs"
CONFIG_DIR = Path.home() / ".focus_guard"
CONFIG_PATH = CONFIG_DIR / "belief_scriptures.json"

# Chrome-open trigger settings (app may also expose these)
CHROME_TRIGGER_ENABLED = True
CHROME_CHECK_SECONDS = 2
CHROME_TRIGGER_COOLDOWN_SECONDS = 15 * 60

SCRIPTURES = [
    ("Psalm 51:10", "Create in me a clean heart, O God."),
    ("1 Corinthians 10:13", "God is faithful; He will not let you be tempted beyond what you can bear."),
    ("Galatians 5:16", "Walk by the Spirit, and you will not gratify the desires of the flesh."),
    ("2 Timothy 2:22", "Flee youthful passions and pursue righteousness."),
    ("Matthew 5:8", "Blessed are the pure in heart, for they shall see God."),
]

DEFAULT_BELIEF_SCRIPTURE_MAP = [
    {
        "name": "shame_identity",
        "keywords": ["dirty", "disgusting", "failure", "worthless", "hopeless", "too far gone", "ashamed"],
        "scriptures": [
            ("Romans 8:1", "There is therefore now no condemnation for those who are in Christ Jesus."),
            ("1 John 1:9", "If we confess our sins, he is faithful and just to forgive us our sins."),
            ("Psalm 103:12", "As far as the east is from the west, so far does he remove our transgressions from us."),
        ],
    },
    {
        "name": "god_is_distant",
        "keywords": ["god is far", "god doesn't care", "alone", "abandoned", "forgotten", "unseen"],
        "scriptures": [
            ("Hebrews 13:5", "I will never leave you nor forsake you."),
            ("Psalm 34:18", "The Lord is near to the brokenhearted."),
            ("Matthew 28:20", "I am with you always, to the end of the age."),
        ],
    },
    {
        "name": "i_deserve_escape",
        "keywords": ["deserve", "need relief", "i earned it", "comfort", "escape", "reward"],
        "scriptures": [
            ("1 Corinthians 6:19-20", "You are not your own, for you were bought with a price."),
            ("Matthew 11:28", "Come to me, all who labor and are heavy laden, and I will give you rest."),
            ("Psalm 16:11", "In your presence there is fullness of joy."),
        ],
    },
    {
        "name": "too_weak",
        "keywords": ["weak", "can't resist", "i can't", "powerless", "too tired", "no strength"],
        "scriptures": [
            ("2 Corinthians 12:9", "My grace is sufficient for you, for my power is made perfect in weakness."),
            ("Philippians 4:13", "I can do all things through him who strengthens me."),
            ("Isaiah 40:29", "He gives power to the faint, and to him who has no might he increases strength."),
        ],
    },
    {
        "name": "hidden_sin",
        "keywords": ["secret", "hide", "no one knows", "private", "darkness"],
        "scriptures": [
            ("1 John 1:7", "If we walk in the light, as he is in the light, we have fellowship with one another."),
            ("John 8:12", "Whoever follows me will not walk in darkness, but will have the light of life."),
            ("Psalm 139:23-24", "Search me, O God, and know my heart."),
        ],
    },
]


def default_belief_scripture_map():
    return copy.deepcopy(DEFAULT_BELIEF_SCRIPTURE_MAP)


def normalize_belief_config(raw_config):
    normalized = []

    if not isinstance(raw_config, list):
        return default_belief_scripture_map()

    for index, category in enumerate(raw_config):
        if not isinstance(category, dict):
            continue

        name = str(category.get("name", f"belief_{index + 1}")).strip()
        if not name:
            name = f"belief_{index + 1}"

        raw_keywords = category.get("keywords", [])
        if isinstance(raw_keywords, str):
            keywords = [item.strip().lower() for item in raw_keywords.split(",") if item.strip()]
        elif isinstance(raw_keywords, list):
            keywords = [str(item).strip().lower() for item in raw_keywords if str(item).strip()]
        else:
            keywords = []

        raw_scriptures = category.get("scriptures", [])
        scriptures = []
        if isinstance(raw_scriptures, list):
            for scripture in raw_scriptures:
                if isinstance(scripture, dict):
                    ref = str(scripture.get("ref", "")).strip()
                    text = str(scripture.get("text", "")).strip()
                elif isinstance(scripture, (list, tuple)) and len(scripture) >= 2:
                    ref = str(scripture[0]).strip()
                    text = str(scripture[1]).strip()
                else:
                    continue

                if ref and text:
                    scriptures.append((ref, text))

        if keywords and scriptures:
            normalized.append({
                "name": name,
                "keywords": keywords,
                "scriptures": scriptures,
            })

    return normalized if normalized else default_belief_scripture_map()


def config_to_json_ready(config):
    return [
        {
            "name": category["name"],
            "keywords": list(category["keywords"]),
            "scriptures": [
                {"ref": ref, "text": text}
                for ref, text in category["scriptures"]
            ],
        }
        for category in config
    ]


_config_store = JsonConfigStore(
    CONFIG_PATH,
    default_belief_scripture_map,
    normalize=normalize_belief_config,
    to_json_ready=config_to_json_ready,
)


def load_belief_scripture_config():
    return _config_store.load()


def save_belief_scripture_config(config):
    return _config_store.save(config)


BELIEF_SCRIPTURE_MAP = load_belief_scripture_config()

ACTIONS = [
    "Stand and stretch",
    "Walk for 2 minutes",
    "Look away from the screen",
    "Drink water",
    "Pray out loud for 20 seconds",
]

PRAYERS = [
    "Lord, strengthen me in this moment.",
    "Jesus, help me choose what is pure.",
    "God, reset my mind and body.",
    "Holy Spirit, lead me right now.",
    "Father, give me discipline and clarity.",
]

# -----------------------------
# STATE
# -----------------------------
water_glasses_today = 0
last_water_reset_date = datetime.date.today()

vitamins_taken_today = False
last_vitamin_reset_date = datetime.date.today()

# Prevent two popup triggers from opening dialogs at the same time
popup_lock = threading.Lock()


# -----------------------------
# LOGGING
# -----------------------------
def get_log_path():
    today = datetime.date.today()
    return LOG_DIR / f"focus_guard_{today:%Y_%m}.jsonl"


_focus_log_writer = JsonlEventWriter(get_log_path, sanitize=False, ensure_ascii=False)


def append_focus_log(record):
    _focus_log_writer.append(record)


# -----------------------------
# HELPERS
# -----------------------------
def reset_water_if_new_day():
    global water_glasses_today, last_water_reset_date

    today = datetime.date.today()
    if today != last_water_reset_date:
        water_glasses_today = 0
        last_water_reset_date = today


def reset_vitamins_if_new_day():
    global vitamins_taken_today, last_vitamin_reset_date

    today = datetime.date.today()
    if today != last_vitamin_reset_date:
        vitamins_taken_today = False
        last_vitamin_reset_date = today


def expected_glasses_by_now():
    now = datetime.datetime.now()
    start = now.replace(hour=WAKE_HOUR, minute=0, second=0, microsecond=0)
    end = now.replace(hour=SLEEP_HOUR, minute=0, second=0, microsecond=0)

    if now <= start:
        return 0

    if now >= end:
        return DAILY_WATER_GLASSES

    total = (end - start).total_seconds()
    elapsed = (now - start).total_seconds()
    return math.ceil(DAILY_WATER_GLASSES * (elapsed / total))


def vitamins_required_by_now():
    return datetime.datetime.now().hour >= LUNCH_HOUR


def select_scripture_for_belief(belief_text):
    normalized = belief_text.lower().strip()

    if not normalized:
        ref, text = random.choice(SCRIPTURES)
        return {
            "match_type": "default",
            "category": None,
            "matched_keywords": [],
            "scripture_ref": ref,
            "scripture_text": text,
        }

    best_match = None
    best_keywords = []

    for category in BELIEF_SCRIPTURE_MAP:
        matched_keywords = [
            keyword for keyword in category["keywords"]
            if keyword in normalized
        ]

        if len(matched_keywords) > len(best_keywords):
            best_match = category
            best_keywords = matched_keywords

    if best_match is None:
        ref, text = random.choice(SCRIPTURES)
        return {
            "match_type": "fallback",
            "category": None,
            "matched_keywords": [],
            "scripture_ref": ref,
            "scripture_text": text,
        }

    ref, text = random.choice(best_match["scriptures"])
    return {
        "match_type": "belief_keyword",
        "category": best_match["name"],
        "matched_keywords": best_keywords,
        "scripture_ref": ref,
        "scripture_text": text,
    }


# -----------------------------
# CONFIG WINDOW & POPUP
# -----------------------------
def open_belief_config_window(parent=None):
    global BELIEF_SCRIPTURE_MAP

    window = tk.Toplevel(parent) if parent is not None else tk.Tk()
    window.title("Focus Guard Belief + Scripture Config")
    window.attributes("-topmost", True)

    w, h = 1000, 760
    sw, sh = window.winfo_screenwidth(), window.winfo_screenheight()
    x, y = int(sw / 2 - w / 2), int(sh / 2 - h / 2)
    window.geometry(f"{w}x{h}+{x}+{y}")

    categories = copy.deepcopy(BELIEF_SCRIPTURE_MAP)
    selected_index = tk.IntVar(value=0)

    outer = tk.Frame(window, padx=18, pady=14)
    outer.pack(expand=True, fill="both")

    tk.Label(
        outer,
        text="Map untrue beliefs to Scripture",
        font=("Arial", 20, "bold")
    ).pack(anchor="w")

    tk.Label(
        outer,
        text=f"Saved config: {CONFIG_PATH}",
        font=("Arial", 10),
        fg="gray"
    ).pack(anchor="w", pady=(0, 8))

    body = tk.Frame(outer)
    body.pack(expand=True, fill="both")

    left = tk.Frame(body)
    left.pack(side="left", fill="y", padx=(0, 12))

    right = tk.Frame(body)
    right.pack(side="left", expand=True, fill="both")

    category_list = tk.Listbox(left, width=30, height=26, font=("Arial", 12))
    category_list.pack(fill="y", expand=True)

    status_label = tk.Label(outer, text="", font=("Arial", 11), fg="green")
    status_label.pack(anchor="w", pady=(8, 0))

    name_var = tk.StringVar()

    tk.Label(right, text="Belief category name", font=("Arial", 12, "bold")).pack(anchor="w")
    name_entry = tk.Entry(right, textvariable=name_var, font=("Arial", 12))
    name_entry.pack(fill="x", pady=(0, 8))

    tk.Label(
        right,
        text="Keywords / phrases to match — one per line",
        font=("Arial", 12, "bold")
    ).pack(anchor="w")
    keywords_text = tk.Text(right, height=7, wrap="word", font=("Arial", 12))
    keywords_text.pack(fill="x", pady=(0, 8))

    tk.Label(
        right,
        text="Scriptures — one per line as: Reference | Scripture text",
        font=("Arial", 12, "bold")
    ).pack(anchor="w")
    scriptures_text = tk.Text(right, height=14, wrap="word", font=("Arial", 12))
    scriptures_text.pack(expand=True, fill="both", pady=(0, 8))

    def refresh_category_list():
        category_list.delete(0, "end")
        for category in categories:
            category_list.insert("end", category["name"])

        if categories:
            index = min(selected_index.get(), len(categories) - 1)
            selected_index.set(index)
            category_list.selection_clear(0, "end")
            category_list.selection_set(index)
            category_list.activate(index)

    def load_selected_category():
        if not categories:
            name_var.set("")
            keywords_text.delete("1.0", "end")
            scriptures_text.delete("1.0", "end")
            return

        category = categories[selected_index.get()]
        name_var.set(category["name"])

        keywords_text.delete("1.0", "end")
        keywords_text.insert("1.0", "\n".join(category["keywords"]))

        scriptures_text.delete("1.0", "end")
        scripture_lines = [
            f"{ref} | {text}"
            for ref, text in category["scriptures"]
        ]
        scriptures_text.insert("1.0", "\n".join(scripture_lines))

    def read_form_category():
        name = name_var.get().strip()
        keywords = [
            line.strip().lower()
            for line in keywords_text.get("1.0", "end").splitlines()
            if line.strip()
        ]

        scriptures = []
        for line in scriptures_text.get("1.0", "end").splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" not in line:
                raise ValueError("Each Scripture line must use: Reference | Scripture text")
            ref, text = [part.strip() for part in line.split("|", 1)]
            if not ref or not text:
                raise ValueError("Each Scripture line needs both a reference and text.")
            scriptures.append((ref, text))

        if not name:
            raise ValueError("Belief category name is required.")
        if not keywords:
            raise ValueError("Add at least one keyword or phrase.")
        if not scriptures:
            raise ValueError("Add at least one Scripture.")

        return {
            "name": name,
            "keywords": keywords,
            "scriptures": scriptures,
        }

    def save_current_category(show_status=False):
        if not categories:
            return True
        try:
            categories[selected_index.get()] = read_form_category()
        except ValueError as exc:
            status_label.config(text=str(exc), fg="red")
            return False

        refresh_category_list()
        if show_status:
            status_label.config(text="Category updated. Click Save Config to persist it.", fg="green")
        return True

    def on_category_select(event=None):
        selection = category_list.curselection()
        if not selection:
            return

        old_index = selected_index.get()
        if categories and old_index != selection[0]:
            if not save_current_category():
                category_list.selection_clear(0, "end")
                category_list.selection_set(old_index)
                return

        selected_index.set(selection[0])
        load_selected_category()
        status_label.config(text="", fg="green")

    def add_category():
        if categories and not save_current_category():
            return

        categories.append({
            "name": "new_belief",
            "keywords": ["example thought"],
            "scriptures": [("John 8:32", "You will know the truth, and the truth will set you free.")],
        })
        selected_index.set(len(categories) - 1)
        refresh_category_list()
        load_selected_category()
        status_label.config(text="New category added. Rename it, then save config.", fg="green")

    def delete_category():
        if not categories:
            return
        del categories[selected_index.get()]
        selected_index.set(max(0, selected_index.get() - 1))
        refresh_category_list()
        load_selected_category()
        status_label.config(text="Category removed. Click Save Config to persist it.", fg="green")

    def reset_defaults():
        nonlocal categories
        categories = default_belief_scripture_map()
        selected_index.set(0)
        refresh_category_list()
        load_selected_category()
        status_label.config(text="Defaults restored in the editor. Click Save Config to persist them.", fg="green")

    def save_config():
        global BELIEF_SCRIPTURE_MAP
        if categories and not save_current_category():
            return

        BELIEF_SCRIPTURE_MAP = save_belief_scripture_config(categories)
        status_label.config(text="Saved. Future belief matches will use this config.", fg="green")

    category_list.bind("<<ListboxSelect>>", on_category_select)

    button_row = tk.Frame(outer)
    button_row.pack(fill="x", pady=(10, 0))

    tk.Button(button_row, text="Add Belief", font=("Arial", 12, "bold"), command=add_category).pack(side="left", padx=(0, 8))
    tk.Button(button_row, text="Delete Belief", font=("Arial", 12, "bold"), command=delete_category).pack(side="left", padx=(0, 8))
    tk.Button(button_row, text="Update Category", font=("Arial", 12, "bold"), command=lambda: save_current_category(True)).pack(side="left", padx=(0, 8))
    tk.Button(button_row, text="Reset Defaults", font=("Arial", 12, "bold"), command=reset_defaults).pack(side="left", padx=(0, 8))
    tk.Button(button_row, text="SAVE CONFIG", font=("Arial", 13, "bold"), command=save_config).pack(side="right")

    refresh_category_list()
    load_selected_category()

    if parent is None:
        window.mainloop()


# Windows helpers to disable chrome windows while popup active
from shane_common.processes.windows import (
    list_process_pids,
    enum_visible_windows_for_pids as _enum_windows_for_pids,
    disable_windows,
    enable_windows,
)


def get_chrome_pids():
    """Return the set of PIDs for running Chrome processes."""
    return list_process_pids("chrome.exe")



def show_popup(is_long_break):
    global water_glasses_today, vitamins_taken_today

    reset_water_if_new_day()
    reset_vitamins_if_new_day()

    default_ref, default_text = random.choice(SCRIPTURES)
    action = random.choice(ACTIONS)
    prayer = random.choice(PRAYERS)

    break_seconds = LONG_BREAK_SECONDS if is_long_break else REGULAR_BREAK_SECONDS
    break_title = "5 MIN RESET BREAK" if is_long_break else "2 MIN RESET BREAK"

    # If running on Windows, try to disable clicking in Chrome windows while
    # the popup is active so the user can't interact with Chrome until they
    # finish the reset. We collect any disabled HWNDs and re-enable them
    # after the popup closes.
    disabled_chrome_hwnds = []
    if os.name == "nt":
        try:
            chrome_pids = get_chrome_pids()
            if chrome_pids:
                hwnds = _enum_windows_for_pids(chrome_pids)
                disabled_chrome_hwnds = disable_windows(hwnds)
        except Exception:
            disabled_chrome_hwnds = []

    root = tk.Tk()
    root.title("Focus Guard")
    root.attributes("-topmost", True)

    w, h = 950, 820
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = int(sw / 2 - w / 2), int(sh / 2 - h / 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    frame = tk.Frame(root, padx=30, pady=20)
    frame.pack(expand=True, fill="both")

    tk.Label(
        frame,
        text=f"⚠️ {break_title}",
        font=("Arial", 26, "bold")
    ).pack()

    countdown_label = tk.Label(frame, font=("Arial", 26, "bold"))
    countdown_label.pack()

    scripture_ref_label = tk.Label(
        frame,
        text=default_ref,
        font=("Arial", 14, "italic")
    )
    scripture_ref_label.pack()

    scripture_text_label = tk.Label(
        frame,
        text=f"“{default_text}”",
        font=("Arial", 16),
        wraplength=850
    )
    scripture_text_label.pack()

    scripture_match_label = tk.Label(
        frame,
        text="Scripture will update when you write an untrue belief.",
        font=("Arial", 11),
        fg="gray",
        wraplength=850
    )
    scripture_match_label.pack(pady=2)

    tk.Button(
        frame,
        text="⚙️ Configure Beliefs + Scriptures",
        font=("Arial", 12, "bold"),
        command=lambda: open_belief_config_window(root)
    ).pack(pady=5)

    tk.Label(
        frame,
        text=f"Prayer: {prayer}",
        fg="blue",
        wraplength=850
    ).pack()

    tk.Label(
        frame,
        text=f"Action: {action}",
        fg="green"
    ).pack()

    # Water
    expected_glasses = expected_glasses_by_now()
    vitamin_required = vitamins_required_by_now()

    water_label = tk.Label(frame, font=("Arial", 14, "bold"))
    water_label.pack(pady=4)

    def update_water():
        water_label.config(
            text=f"💧 Water: {water_glasses_today}/{expected_glasses} expected by now"
        )

    def drink_water():
        global water_glasses_today
        water_glasses_today += 1
        update_water()
        update_button()

    tk.Button(
        frame,
        text="🥛 I DRANK WATER",
        font=("Arial", 13, "bold"),
        command=drink_water
    ).pack(pady=3)

    # Vitamins
    vitamin_label = tk.Label(frame, font=("Arial", 14, "bold"))
    vitamin_label.pack(pady=4)

    def update_vitamin():
        if not vitamin_required:
            vitamin_label.config(text="💊 Vitamins: not required yet", fg="gray")
        elif vitamins_taken_today:
            vitamin_label.config(text="💊 Vitamins: taken", fg="green")
        else:
            vitamin_label.config(text="💊 Vitamins: needed after lunch", fg="red")

    def take_vitamins():
        global vitamins_taken_today
        vitamins_taken_today = True
        update_vitamin()
        update_button()

    vitamin_button = tk.Button(
        frame,
        text="💊 I TOOK MY VITAMINS",
        font=("Arial", 13, "bold"),
        command=take_vitamins
    )
    vitamin_button.pack(pady=3)

    if not vitamin_required:
        vitamin_button.config(state="disabled")

    # Self report
    energy = tk.IntVar(value=50)
    temptation = tk.IntVar(value=1)

    tk.Scale(
        frame,
        from_=1,
        to=100,
        label="Energy right now",
        orient="horizontal",
        variable=energy,
        length=750
    ).pack()

    tk.Scale(
        frame,
        from_=1,
        to=100,
        label="Temptation toward sexual sin right now",
        orient="horizontal",
        variable=temptation,
        length=750
    ).pack()

    tk.Label(
        frame,
        text="What am I believing about myself or God that may be untrue?",
        font=("Arial", 12, "bold")
    ).pack(pady=3)

    belief = tk.Text(frame, height=4, width=95, wrap="word")
    belief.pack()

    selected_scripture = {
        "match_type": "default",
        "category": None,
        "matched_keywords": [],
        "scripture_ref": default_ref,
        "scripture_text": default_text,
    }

    def refresh_scripture_from_belief():
        nonlocal selected_scripture

        belief_value = belief.get("1.0", "end").strip()
        selected_scripture = select_scripture_for_belief(belief_value)

        scripture_ref_label.config(text=selected_scripture["scripture_ref"])
        scripture_text_label.config(text=f"“{selected_scripture['scripture_text']}”")

        if selected_scripture["match_type"] == "belief_keyword":
            keywords = ", ".join(selected_scripture["matched_keywords"])
            scripture_match_label.config(
                text=f"Matched belief category: {selected_scripture['category']} | keywords: {keywords}",
                fg="purple"
            )
        elif selected_scripture["match_type"] == "fallback":
            scripture_match_label.config(
                text="No belief keyword matched yet. Showing a general reset Scripture.",
                fg="gray"
            )
        else:
            scripture_match_label.config(
                text="Scripture will update when you write an untrue belief.",
                fg="gray"
            )

    def on_belief_key_release(event):
        refresh_scripture_from_belief()

    belief.bind("<KeyRelease>", on_belief_key_release)

    # Done button
    done = tk.Button(
        frame,
        text="RESET COMPLETE",
        font=("Arial", 16, "bold"),
        state="disabled"
    )
    done.pack(pady=12)

    remaining = break_seconds
    timer_done = False

    def can_close():
        water_ok = water_glasses_today >= expected_glasses
        vitamins_ok = (not vitamin_required) or vitamins_taken_today
        return timer_done and water_ok and vitamins_ok

    def update_button():
        done.config(state="normal" if can_close() else "disabled")

    def close():
        if not can_close():
            return

        refresh_scripture_from_belief()

        record = {
            "schema_version": 2,
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "event_type": "focus_guard_popup",

            "break": {
                "is_long_break": is_long_break,
                "duration_seconds": break_seconds,
                "timer_completed": timer_done,
            },

            "water": {
                "glasses_today": water_glasses_today,
                "expected_glasses_by_now": expected_glasses,
                "daily_target_glasses": DAILY_WATER_GLASSES,
            },

            "vitamins": {
                "required_by_now": vitamin_required,
                "taken_today": vitamins_taken_today,
            },

            "self_report": {
                "energy_1_to_100": energy.get(),
                "sexual_temptation_1_to_100": temptation.get(),
                "untrue_belief": belief.get("1.0", "end").strip(),
            },

            "spiritual_prompt": {
                "scripture_ref": selected_scripture["scripture_ref"],
                "scripture_text": selected_scripture["scripture_text"],
                "match_type": selected_scripture["match_type"],
                "belief_category": selected_scripture["category"],
                "matched_keywords": selected_scripture["matched_keywords"],
                "prayer": prayer,
                "action": action,
            },

            "extra": {}
        }

        append_focus_log(record)
        root.destroy()

    done.config(command=close)

    def tick():
        nonlocal remaining, timer_done

        countdown_label.config(text=f"{remaining // 60:02d}:{remaining % 60:02d}")

        if remaining <= 0:
            timer_done = True
            update_button()
            return

        remaining -= 1
        root.after(1000, tick)

    update_water()
    update_vitamin()
    refresh_scripture_from_belief()
    tick()

    try:
        root.mainloop()
    finally:
        if os.name == "nt" and disabled_chrome_hwnds:
            try:
                enable_windows(disabled_chrome_hwnds)
            except Exception:
                pass


def trigger_focus_popup(is_long_break=False):
    with popup_lock:
        show_popup(is_long_break=is_long_break)
