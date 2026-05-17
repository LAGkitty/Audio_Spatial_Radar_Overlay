import tkinter as tk
import threading
import soundcard as sc
import numpy as np
import sys
import math
import ctypes

print("[SYSTEM] High-Sensitivity Manual Control Radar Initialized.")

class AudioRadarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Radar Controls")
        self.root.geometry("320x260")
        self.root.attributes("-topmost", True)
        self.root.config(bg="#1e1e1e")
        
        self.running = False
        self.audio_thread = None
        
        # --- TRACKING POOL ---
        self.max_slots = 10
        self.tracking_slots = {}
        for i in range(self.max_slots):
            self.tracking_slots[i] = [0.5, 0.5, 0.5, 0.5, 0, "#00ffff", 0.0]

        self.text_current_x = 0.5
        self.text_target_x = 0.5
        self.text_active = False

        # --- MANUAL HIGH-SENSITIVITY NOISE FLOOR ---
        # No more auto-ambient damping. This is a direct manual threshold.
        self.noise_floor = 0.0035       
        self.current_live_rms = 0.0
        self.rolling_peak_rms = 0.010  # Dynamically auto-scales the visual bar range

        # --- GUI DASHBOARD ---
        tk.Label(root, text="RADAR MONITOR CONTROL", font=("Arial", 10, "bold"), fg="#ffffff", bg="#1e1e1e").pack(pady=6)
        
        self.panel_canvas = tk.Canvas(root, width=120, height=50, bg="#2d2d2d", highlightthickness=1, highlightbackground="#444444")
        self.panel_canvas.pack(pady=4)
        self.gui_text_tracker = self.panel_canvas.create_text(60, 25, text="READY", fill="#666666", font=("Arial", 9, "bold"))

        tk.Label(root, text="Live Signal / Dynamic Cutoff (Red)", font=("Arial", 8), fg="#aaaaaa", bg="#1e1e1e").pack()
        self.bar_canvas = tk.Canvas(root, width=260, height=14, bg="#111111", highlightthickness=0)
        self.bar_canvas.pack(pady=4)
        self.fill_bar = self.bar_canvas.create_rectangle(0, 0, 0, 14, fill="#00ff66")
        self.line_cutoff = self.bar_canvas.create_line(0, 0, 0, 14, fill="#ff2222", width=2)

        # Controls Frame
        ctrl_frame = tk.Frame(root, bg="#1e1e1e")
        ctrl_frame.pack(pady=6)
        
        tk.Button(ctrl_frame, text="- Less Sensitive", command=self.increase_floor, bg="#444444", fg="white", font=("Arial", 9, "bold"), width=12).grid(row=0, column=0, padx=5)
        self.floor_lbl = tk.Label(ctrl_frame, text=f"Floor: {self.noise_floor:.4f}", fg="#00ffff", bg="#1e1e1e", font=("Courier", 9, "bold"))
        self.floor_lbl.grid(row=0, column=1, padx=5)
        tk.Button(ctrl_frame, text="+ More Sensitive", command=self.decrease_floor, bg="#444444", fg="white", font=("Arial", 9, "bold"), width=12).grid(row=0, column=2, padx=5)

        self.start_btn = tk.Button(root, text="START RADAR OVERLAY", command=self.start_radar, bg="#0088ff", fg="white", font=("Arial", 10, "bold"), height=2)
        self.start_btn.pack(fill=tk.X, padx=20, pady=8)

        # --- Overlay Setup ---
        self.overlay = tk.Toplevel(self.root)
        self.overlay.attributes('-fullscreen', True)
        self.overlay.attributes('-topmost', True)
        self.overlay.config(bg='black')
        self.overlay.attributes('-transparentcolor', 'black')
        self.overlay.overrideredirect(True) 
        self.overlay.attributes('-alpha', 1.0) 
        
        self.canvas = tk.Canvas(self.overlay, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        
        self.BASE_RADIUS = 3
        self.MAX_BONUS_RADIUS = 7  
        
        self.dot_ui_items = {}
        for i in range(self.max_slots):
            self.dot_ui_items[i] = self.canvas.create_oval(-100, -100, -100, -100, fill="#00ffff", outline="white", width=1)
        
        self.behind_text = self.canvas.create_text(
            self.screen_width // 2, self.screen_height - 32, 
            text="▲ BEHIND ▲", fill="#ff2222", font=("Impact", 30, "bold")
        )
        self.canvas.itemconfigure(self.behind_text, state='hidden')
        
        self.overlay.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.make_overlay_completely_unclickable()
        self.animate_loop()

    def increase_floor(self):
        # Manually raise threshold (makes it less sensitive to noise)
        self.noise_floor = min(0.0300, self.noise_floor + 0.0005)
        self.floor_lbl.config(text=f"Floor: {self.noise_floor:.4f}")

    def decrease_floor(self):
        # Manually lower threshold (makes it more sensitive to quiet footsteps)
        self.noise_floor = max(0.0005, self.noise_floor - 0.0005)
        self.floor_lbl.config(text=f"Floor: {self.noise_floor:.4f}")

    def make_overlay_completely_unclickable(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.overlay.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            style |= 0x00000020 | 0x00080000 | 0x08000000
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception as e:
            print(f"[SYSTEM WARNING] Window hook failed: {e}")

    def start_radar(self):
        if not self.running:
            self.running = True
            self.start_btn.config(text="STOP RADAR OVERLAY", bg="#ff2222")
            self.panel_canvas.config(bg="#1a2e1a")
            self.overlay.deiconify()
            self.audio_thread = threading.Thread(target=self.audio_loop, daemon=True)
            self.audio_thread.start()
        else:
            self.running = False
            self.start_btn.config(text="START RADAR OVERLAY", bg="#0088ff")
            self.panel_canvas.config(bg="#2d2d2d")
            self.panel_canvas.itemconfigure(self.gui_text_tracker, text="STOPPED", fill="#666666")
            self.overlay.withdraw()
            self.hide_all()

    def hide_all(self):
        for item in self.dot_ui_items.values():
            self.canvas.coords(item, -100, -100, -100, -100)
        self.canvas.itemconfigure(self.behind_text, state='hidden')

    def audio_loop(self):
        try:
            mics = sc.all_microphones(include_loopback=True)
            if not mics: return
            mic = mics[0]
            with mic.recorder(samplerate=44100, channels=2) as recorder:
                while self.running:
                    data = recorder.record(numframes=512)
                    if len(data) > 0:
                        self.process_spatial_audio(data)
        except Exception as e:
            print(f"[ERROR] Audio drop: {e}")
            self.root.after(10, self.start_radar)

    def process_spatial_audio(self, data):
        left = data[:, 0]
        right = data[:, 1]
        
        raw_left_rms = np.sqrt(np.mean(left**2))
        raw_right_rms = np.sqrt(np.mean(right**2))
        
        fft_l = np.fft.rfft(left)
        fft_r = np.fft.rfft(right)
        freqs = np.fft.rfftfreq(len(left), d=1/44100)
        
        kill_indices = np.where((freqs < 60) | (freqs > 700))[0]
        fft_l[kill_indices] = 0
        fft_r[kill_indices] = 0
        
        left_clean = np.fft.irfft(fft_l)
        right_clean = np.fft.irfft(fft_r)
        
        total_rms = np.sqrt(np.mean(left_clean**2)) + np.sqrt(np.mean(right_clean**2))
        self.current_live_rms = total_rms

        # Auto-scale the sound bar dynamically so it never stays maxed out
        self.rolling_peak_rms = max(self.rolling_peak_rms * 0.995, total_rms, 0.004)

        # Active Signal Suppression Gating (Direct comparison with manual floor)
        if total_rms < self.noise_floor:
            self.text_active = False
            for i in range(self.max_slots):
                self.tracking_slots[i][4] = 0
            return

        # 1. --- LOGARITHMIC SPREAD MATRIX ---
        correlation = np.correlate(left_clean - np.mean(left_clean), right_clean - np.mean(right_clean), mode='full')
        delay_sample = np.argmax(correlation) - (len(left_clean) - 1)
        max_delay = 24
        clamped_delay = max(-max_delay, min(max_delay, delay_sample))
        
        base_x = ((clamped_delay / max_delay) + 1.0) / 2.0 
        centered_x = base_x - 0.5
        if centered_x != 0:
            expanded_x = math.copysign(math.pow(abs(centered_x) * 2.0, 0.70) * 0.5, centered_x)
            target_x = max(0.02, min(0.98, (expanded_x * 1.5) + 0.5))
        else:
            target_x = 0.5

        # Absolute Center Bubble Filter to ignore ambient mono sounds
        if 0.42 < target_x < 0.58:
            return

        # 2. --- Vertically Compressed Y-Axis Plane ---
        fft_combined = np.abs(fft_l + fft_r)
        max_fft_val = np.max(fft_combined) if np.max(fft_combined) > 0 else 1
        peaks = np.where(fft_combined > max_fft_val * 0.35)[0]
        
        raw_detected_points = []
        for peak in peaks[:4]:
            freq = freqs[peak]
            if freq < 40: continue
            
            base_y = 1.0 - (math.log10(freq) / 3.8)
            target_y = 0.45 + (max(0.1, min(0.9, base_y)) - 0.5) * 0.25
            raw_detected_points.append((target_x, target_y, fft_combined[peak] / max_fft_val))

        # 3. --- Dynamic Cluster Merging ---
        merged_points = []
        for tx, ty, r_vol in raw_detected_points:
            close_cluster = False
            for idx, (mx, my, mv) in enumerate(merged_points):
                if math.isclose(tx, mx, abs_tol=0.08) and math.isclose(ty, my, abs_tol=0.08):
                    merged_points[idx] = ((mx + tx)/2, (my + ty)/2, max(mv, r_vol))
                    close_cluster = True
                    break
            if not close_cluster:
                merged_points.append((tx, ty, r_vol))

        # 4. --- Multiplexing Allocation ---
        for tx, ty, r_vol in merged_points:
            assigned_slot = -1
            min_distance = 999.0
            for i in range(self.max_slots):
                if self.tracking_slots[i][4] > 0:
                    dist = math.sqrt((self.tracking_slots[i][2] - tx)**2 + (self.tracking_slots[i][3] - ty)**2)
                    if dist < min_distance and dist < 0.25:
                        min_distance = dist
                        assigned_slot = i
            if assigned_slot == -1:
                for i in range(self.max_slots):
                    if self.tracking_slots[i][4] <= 0:
                        assigned_slot = i
                        break
            
            if assigned_slot != -1:
                self.tracking_slots[assigned_slot][2] = tx
                self.tracking_slots[assigned_slot][3] = ty
                self.tracking_slots[assigned_slot][4] = 12 
                self.tracking_slots[assigned_slot][6] = r_vol 
                
                if tx < 0.42: self.tracking_slots[assigned_slot][5] = "#ff4444"
                elif tx > 0.58: self.tracking_slots[assigned_slot][5] = "#00eef7"
                else: self.tracking_slots[assigned_slot][5] = "#44ff44"

        # 5. --- ISOLATED REAR TEXT CONTEXT ---
        is_real_rear_sound = False
        if total_rms > self.noise_floor:
            phase_corr = np.corrcoef(left_clean, right_clean)[0, 1] if total_rms > 0.005 else 0
            if phase_corr < -0.45:  
                is_real_rear_sound = True
                
            if not is_real_rear_sound and total_rms > 0.030:
                rms_ratio = min(raw_left_rms, raw_right_rms) / max(raw_left_rms, raw_right_rms + 1e-6)
                high_freq_cutoff = np.where(freqs > 1800)[0]
                high_freq_energy = np.sum(np.abs(fft_l[high_freq_cutoff]) + np.abs(fft_r[high_freq_cutoff]))
                if rms_ratio > 0.96 and high_freq_energy < 0.0001:
                    is_real_rear_sound = True

        if is_real_rear_sound: 
            self.text_target_x = target_x  
            self.text_active = True
        else:
            self.text_active = False

    def animate_loop(self):
        # Update Dashboard Visuals Focus
        val_percentage = min(1.0, self.current_live_rms / (self.rolling_peak_rms + 1e-6))
        cutoff_percentage = min(1.0, self.noise_floor / (self.rolling_peak_rms + 1e-6))
        
        self.bar_canvas.coords(self.fill_bar, 0, 0, int(260 * val_percentage), 14)
        self.bar_canvas.coords(self.line_cutoff, int(260 * cutoff_percentage), 0, int(260 * cutoff_percentage), 14)

        if self.running:
            if self.text_active:
                self.panel_canvas.itemconfigure(self.gui_text_tracker, text=f"ALERT REAR: {int(self.text_target_x*100)}%", fill="#ff3333")
                
                # Update text on desktop transparent engine
                self.text_current_x += (self.text_target_x - self.text_current_x) * 0.20
                text_pix_x = int(self.screen_width * self.text_current_x)
                self.canvas.coords(self.behind_text, text_pix_x, self.screen_height - 32)
                self.canvas.itemconfigure(self.behind_text, state='normal')
            else:
                self.panel_canvas.itemconfigure(self.gui_text_tracker, text="TRACKING", fill="#00ff66")
                self.canvas.itemconfigure(self.behind_text, state='hidden')

            # Render overlay channel dots
            mouse_x = self.root.winfo_pointerx()
            mouse_y = self.root.winfo_pointery()
            for i in range(self.max_slots):
                coords = self.tracking_slots[i]
                if coords[4] > 0:
                    coords[4] -= 1
                    coords[0] += (coords[2] - coords[0]) * 0.25
                    coords[1] += (coords[3] - coords[1]) * 0.25
                    
                    pix_x = int(self.screen_width * coords[0])
                    pix_y = int(self.screen_height * coords[1])
                    
                    if math.sqrt((pix_x - mouse_x)**2 + (pix_y - mouse_y)**2) < 12:
                        self.canvas.coords(self.dot_ui_items[i], -100, -100, -100, -100)
                        continue

                    current_radius = int(self.BASE_RADIUS + (coords[6] * self.MAX_BONUS_RADIUS))
                    self.canvas.itemconfigure(self.dot_ui_items[i], fill=coords[5])
                    self.canvas.coords(self.dot_ui_items[i], pix_x - current_radius, pix_y - current_radius, pix_x + current_radius, pix_y + current_radius)
                else:
                    self.canvas.coords(self.dot_ui_items[i], -100, -100, -100, -100)
        else:
            self.bar_canvas.coords(self.fill_bar, 0, 0, 0, 14)

        self.root.after(16, self.animate_loop)

    def on_close(self):
        self.running = False
        self.root.destroy()
        sys.exit()

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioRadarApp(root)
    root.mainloop()