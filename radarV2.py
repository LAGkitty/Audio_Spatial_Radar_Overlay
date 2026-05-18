import tkinter as tk
import threading
import soundcard as sc
import numpy as np
import sys
import math
import ctypes
import time

print("[SYSTEM] High-Refresh-Rate Optimized Trail Radar Initialized.")

class AudioRadarApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Radar Controls")
        self.root.geometry("340x290")
        self.root.attributes("-topmost", True)
        self.root.config(bg="#121212")
        
        self.running = False
        self.audio_thread = None
        
        # --- MODE TOGGLE ---
        self.overlay_mode = tk.StringVar(value="dots")  # "dots" or "ring"
        
        # --- TRACKING POOL ---
        # Format: [current_x, current_y, target_x, target_y, active_frames, base_color_name, relative_vol, history_list, current_opacity, current_size]
        self.max_slots = 10
        self.tracking_slots = {}
        for i in range(self.max_slots):
            self.tracking_slots[i] = [0.5, 0.5, 0.5, 0.5, 0, "center", 0.0, [], 0.0, 3.0]

        self.text_current_x = 0.5
        self.text_target_x = 0.5
        self.text_active = False

        # --- NOISE FLOOR & AUDIO SETTINGS ---
        self.noise_floor = 0.0035       
        self.adaptive_noise_floor = 0.0035  # Dynamically adapts to quiet areas
        self.current_live_rms = 0.0
        self.smooth_live_rms = 0.0     
        self.rolling_peak_rms = 0.010  
        self.current_samplerate = 44100 
        
        self.last_click_time = 0
        self.click_streak = 0
        self.last_frame_time = time.perf_counter()

        # --- GUI DASHBOARD ---
        tk.Label(root, text="NEON AUDIO SPATIAL RADAR", font=("Trebuchet MS", 11, "bold"), fg="#00ffcc", bg="#121212").pack(pady=8)
        
        self.panel_canvas = tk.Canvas(root, width=140, height=44, bg="#1a1a1a", highlightthickness=1, highlightbackground="#333333")
        self.panel_canvas.pack(pady=2)
        
        self.panel_canvas.create_oval(10, 3, 130, 41, outline="#222222", width=1)
        self.panel_canvas.create_line(70, 3, 70, 41, fill="#222222", width=1)
        self.gui_text_tracker = self.panel_canvas.create_text(70, 22, text="SYSTEM READY", fill="#888888", font=("Impact", 10, "normal"))

        tk.Label(root, text="Live Spectrum Intensity vs Threshold Cutoff", font=("Arial", 8, "italic"), fg="#777777", bg="#121212").pack()
        self.bar_canvas = tk.Canvas(root, width=280, height=14, bg="#1a1a1a", highlightthickness=1, highlightbackground="#2d2d2d")
        self.bar_canvas.pack(pady=2)
        self.fill_bar = self.bar_canvas.create_rectangle(0, 0, 0, 14, fill="#00ffcc", outline="")
        self.line_cutoff = self.bar_canvas.create_line(0, 0, 0, 14, fill="#ff3333", width=2)

        # Sensitivity Frame
        ctrl_frame = tk.Frame(root, bg="#121212")
        ctrl_frame.pack(pady=4)
        
        self.btn_less = tk.Button(ctrl_frame, text="◀ Less Sensitive", command=lambda: self.adjust_floor(True), 
                                  bg="#222222", fg="#ff5555", activebackground="#332222", activeforeground="#ff5555",
                                  font=("Arial", 9, "bold"), width=12, bd=0, relief="flat", cursor="hand2")
        self.btn_less.grid(row=0, column=0, padx=6)
        
        self.floor_lbl = tk.Label(ctrl_frame, text=f"{self.noise_floor:.4f}", fg="#00ffcc", bg="#1a1a1a", 
                                  font=("Courier New", 11, "bold"), width=10, relief="sunken", bd=1, highlightbackground="#333333")
        self.floor_lbl.grid(row=0, column=1, padx=6)
        
        self.btn_more = tk.Button(ctrl_frame, text="More Sensitive ▶", command=lambda: self.adjust_floor(False), 
                                  bg="#222222", fg="#33ff99", activebackground="#223322", activeforeground="#33ff99",
                                  font=("Arial", 9, "bold"), width=12, bd=0, relief="flat", cursor="hand2")
        self.btn_more.grid(row=0, column=2, padx=6)

        # Mode Selector Frame
        mode_frame = tk.Frame(root, bg="#121212")
        mode_frame.pack(pady=4)
        tk.Radiobutton(mode_frame, text="Horizontal Dots", variable=self.overlay_mode, value="dots",
                       bg="#121212", fg="#ffffff", selectcolor="#1a1a1a", activebackground="#121212", activeforeground="#ffffff",
                       font=("Arial", 9), command=self.on_mode_change).grid(row=0, column=0, padx=12)
        tk.Radiobutton(mode_frame, text="Directional HUD Ring", variable=self.overlay_mode, value="ring",
                       bg="#121212", fg="#00ffcc", selectcolor="#1a1a1a", activebackground="#121212", activeforeground="#00ffcc",
                       font=("Arial", 9), command=self.on_mode_change).grid(row=0, column=1, padx=12)

        # Start button
        self.start_btn = tk.Button(root, text="START MONITOR", command=self.start_radar, 
                                   bg="#00ffcc", fg="#121212", activebackground="#00cc99",
                                   font=("Arial", 10, "bold"), height=2, bd=0, relief="flat", cursor="hand2")
        self.start_btn.pack(fill=tk.X, padx=24, pady=6)

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
        
        # Geometry for Sound Ring Mode
        self.ring_center_x = self.screen_width // 2
        self.ring_center_y = self.screen_height // 2
        self.ring_radius = 110  
        
        # Restricted radius defaults to prevent dots from getting too large
        self.BASE_RADIUS = 3.2
        self.MAX_BONUS_RADIUS = 4.2  
        
        # Pre-create Canvas elements including motion trail indicators
        self.dot_ui_items = {}
        for i in range(self.max_slots):
            self.dot_ui_items[i] = {
                'trail2': self.canvas.create_oval(-100, -100, -100, -100, fill="", outline="", width=0),
                'trail1': self.canvas.create_oval(-100, -100, -100, -100, fill="", outline="", width=0),
                'halo': self.canvas.create_oval(-100, -100, -100, -100, fill="", outline="#00ffff", width=1),
                'core': self.canvas.create_oval(-100, -100, -100, -100, fill="#00ffff", outline="", width=0)
            }
        
        # Pre-create Ring elements (hidden initially)
        self.radar_center_circle = self.canvas.create_oval(
            self.ring_center_x - self.ring_radius, self.ring_center_y - self.ring_radius,
            self.ring_center_x + self.ring_radius, self.ring_center_y + self.ring_radius,
            outline="#1a1a1a", width=2, state="hidden"
        )
        self.radar_slots = {}
        for i in range(self.max_slots):
            self.radar_slots[i] = {
                'arc': self.canvas.create_arc(
                    self.ring_center_x - self.ring_radius - 8, self.ring_center_y - self.ring_radius - 8,
                    self.ring_center_x + self.ring_radius + 8, self.ring_center_y + self.ring_radius + 8,
                    start=0, extent=24, outline="#00ffff", width=4, style="arc", state="hidden"
                )
            }
        
        self.behind_text = self.canvas.create_text(
            self.screen_width // 2, self.screen_height - 32, 
            text="▲ BEHIND ▲", fill="#ff2222", font=("Impact", 30, "bold")
        )
        self.canvas.itemconfigure(self.behind_text, state='hidden')
        
        self.overlay.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.make_overlay_completely_unclickable()
        self.animate_loop()

    def make_overlay_completely_unclickable(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.overlay.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            style |= 0x00000020 | 0x00080000 | 0x08000000  
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception as e:
            print(f"[SYSTEM WARNING] Window hook failed: {e}")

    def adjust_floor(self, increase):
        now = time.time()
        time_diff = now - self.last_click_time
        self.last_click_time = now
        
        if time_diff < 0.35:
            self.click_streak = min(5, self.click_streak + 1)
        else:
            self.click_streak = 0
            
        step = 0.0002 if self.click_streak < 2 else 0.0010
        
        if increase:
            self.noise_floor = min(0.0300, self.noise_floor + step)
        else:
            self.noise_floor = max(0.0005, self.noise_floor - step)
            
        self.floor_lbl.config(text=f"{self.noise_floor:.4f}")

    def on_mode_change(self):
        self.hide_all()

    def start_radar(self):
        if not self.running:
            self.running = True
            self.start_btn.config(text="SHUTDOWN MONITOR", bg="#ff3333", fg="white")
            self.panel_canvas.config(bg="#12251d")
            self.overlay.deiconify()
            self.last_frame_time = time.perf_counter()
            self.audio_thread = threading.Thread(target=self.audio_loop, daemon=True)
            self.audio_thread.start()
        else:
            self.running = False
            self.start_btn.config(text="START RADAR OVERLAY", bg="#00ffcc", fg="#121212")
            self.panel_canvas.config(bg="#1a1a1a")
            self.panel_canvas.itemconfigure(self.gui_text_tracker, text="STOPPED", fill="#555555")
            self.overlay.withdraw()
            self.hide_all()

    def hide_all(self):
        # Reset standard dot items
        for item in self.dot_ui_items.values():
            self.canvas.coords(item['trail2'], -100, -100, -100, -100)
            self.canvas.coords(item['trail1'], -100, -100, -100, -100)
            self.canvas.coords(item['halo'], -100, -100, -100, -100)
            self.canvas.coords(item['core'], -100, -100, -100, -100)
            
        # Reset ring mode items
        self.canvas.itemconfigure(self.radar_center_circle, state="hidden")
        for item in self.radar_slots.values():
            self.canvas.itemconfigure(item['arc'], state="hidden")
            
        self.canvas.itemconfigure(self.behind_text, state='hidden')

    def audio_loop(self):
        try:
            default_speaker = sc.default_speaker()
            mics = sc.all_microphones(include_loopback=True)
            
            selected_mic = None
            for mic in mics:
                if default_speaker.name in mic.name:
                    selected_mic = mic
                    break
            
            if selected_mic is None and len(mics) > 0:
                selected_mic = mics[0]
                
            if not selected_mic:
                print("[ERROR] No active loopback audio channels found.")
                return

            print(f"[SYSTEM] Listening to device: {selected_mic.name}")
            
            self.current_samplerate = int(default_speaker.id.get('latency', 44100) if isinstance(default_speaker.id, dict) else 44100)
            if self.current_samplerate not in [44100, 48000, 96000]:
                self.current_samplerate = 44100 

            with selected_mic.recorder(samplerate=self.current_samplerate, channels=2) as recorder:
                while self.running:
                    data = recorder.record(numframes=512)
                    if len(data) > 0:
                        self.process_spatial_audio(data)
        except Exception as e:
            print(f"[ERROR] Speaker Sync Lost: {e}")
            self.root.after(1000, self.start_radar)

    def process_spatial_audio(self, data):
        left = data[:, 0]
        right = data[:, 1]
        
        raw_left_rms = np.sqrt(np.mean(left**2))
        raw_right_rms = np.sqrt(np.mean(right**2))
        
        fft_l = np.fft.rfft(left)
        fft_r = np.fft.rfft(right)
        freqs = np.fft.rfftfreq(len(left), d=1/self.current_samplerate)
        
        kill_indices = np.where((freqs < 45) | (freqs > 750))[0]
        fft_l[kill_indices] = 0
        fft_r[kill_indices] = 0
        
        left_clean = np.fft.irfft(fft_l)
        right_clean = np.fft.irfft(fft_r)
        
        total_rms = np.sqrt(np.mean(left_clean**2)) + np.sqrt(np.mean(right_clean**2))
        self.current_live_rms = total_rms

        self.rolling_peak_rms = max(self.rolling_peak_rms * 0.995, total_rms, 0.004)

        # --- ADAPTIVE NOISE FLOOR TRACKING ---
        # Slowly decay the adaptive noise floor toward current RMS when quiet, allowing
        # extreme sensitivity in silent areas but keeping high thresholds in loud zones.
        if total_rms < self.adaptive_noise_floor:
            self.adaptive_noise_floor = self.adaptive_noise_floor * 0.90 + total_rms * 0.10
        else:
            self.adaptive_noise_floor = self.adaptive_noise_floor * 0.998 + total_rms * 0.002
        self.adaptive_noise_floor = max(0.0002, self.adaptive_noise_floor)

        # In quiet areas, let the threshold automatically lower to 1.5x the ambient floor
        effective_noise_floor = min(self.noise_floor, self.adaptive_noise_floor * 1.5)

        if total_rms < effective_noise_floor:
            self.text_active = False
            return

        # 1. --- LOGARITHMIC SPREAD MATRIX ---
        correlation = np.correlate(left_clean - np.mean(left_clean), right_clean - np.mean(right_clean), mode='full')
        delay_sample = np.argmax(correlation) - (len(left_clean) - 1)
        max_delay = int(24 * (self.current_samplerate / 44100)) 
        clamped_delay = max(-max_delay, min(max_delay, delay_sample))
        
        base_x = ((clamped_delay / max_delay) + 1.0) / 2.0 

        centered_x = 0.5 - base_x
        if centered_x != 0:
            expanded_x = math.copysign(math.pow(abs(centered_x) * 2.0, 0.65) * 0.5, centered_x)
            target_x = max(0.02, min(0.98, (expanded_x * 1.55) + 0.5))
        else:
            target_x = 0.5

        if 0.42 < target_x < 0.58:
            return

        # 2. --- Vertically Compressed Y-Axis Plane ---
        fft_combined = np.abs(fft_l + fft_r)
        
        raw_detected_points = []
        dom_idx = np.argmax(fft_combined)
        freq = freqs[dom_idx]
        
        if freq >= 40:
            # --- ADAPTIVE SPECTRAL ANOMALY FILTER ---
            mean_spectral_energy = np.mean(fft_combined[fft_combined > 0]) if np.any(fft_combined > 0) else 1e-5
            peak_energy = fft_combined[dom_idx]
            
            # FOOTSTEP BAND ENHANCEMENT: Slashes required prominence to 2.0x within key step frequency bands
            is_step_band = (60.0 <= freq <= 300.0)
            prominence_gate = 2.0 if is_step_band else 3.5
            
            if peak_energy > (mean_spectral_energy * prominence_gate):
                base_y = 1.0 - (math.log10(freq) / 3.8)
                target_y = 0.45 + (max(0.1, min(0.9, base_y)) - 0.5) * 0.25
                
                denom = max(0.002, min(0.015, total_rms * 1.8))
                signal_strength = min(1.0, (total_rms - effective_noise_floor) / denom)
                
                # Slashes minimum signal barrier in quiet environments to grab very faint steps
                min_gate = 0.04 if is_step_band else 0.12
                if signal_strength > min_gate:
                    raw_detected_points.append((target_x, target_y, signal_strength))

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
                
                if tx < 0.42: 
                    self.tracking_slots[assigned_slot][5] = "left"
                elif tx > 0.58: 
                    self.tracking_slots[assigned_slot][5] = "right"
                else: 
                    self.tracking_slots[assigned_slot][5] = "center"

        # 5. --- ISOLATED REAR TEXT CONTEXT (HIGHLY SENSITIVE) ---
        is_real_rear_sound = False
        if total_rms > effective_noise_floor:
            phase_corr = np.corrcoef(left_clean, right_clean)[0, 1] if total_rms > 0.002 else 0
            if phase_corr < -0.15:  
                is_real_rear_sound = True
                
            if not is_real_rear_sound and total_rms > 0.005:  
                rms_ratio = min(raw_left_rms, raw_right_rms) / max(raw_left_rms, raw_right_rms + 1e-6)
                high_freq_cutoff = np.where(freqs > 1800)[0]
                high_freq_energy = np.sum(np.abs(fft_l[high_freq_cutoff]) + np.abs(fft_r[high_freq_cutoff]))
                if rms_ratio > 0.85 and high_freq_energy < 0.015:  
                    is_real_rear_sound = True

        if is_real_rear_sound: 
            self.text_target_x = target_x  
            self.text_active = True
        else:
            self.text_active = False

    def animate_loop(self):
        now = time.perf_counter()
        dt = now - self.last_frame_time
        self.last_frame_time = now
        
        dt = min(0.1, dt)

        # --- TRUE EXPONENTIAL SMOOTHING COEFFICIENTS ---
        move_coef = 1.0 - math.exp(-15.0 * dt)    
        opacity_coef = 1.0 - math.exp(-9.0 * dt)  
        size_coef = 1.0 - math.exp(-12.0 * dt)    
        bar_coef = 1.0 - math.exp(-15.0 * dt)     

        # Update Dashboard Visuals
        self.smooth_live_rms += (self.current_live_rms - self.smooth_live_rms) * bar_coef
        val_percentage = min(1.0, self.smooth_live_rms / (self.rolling_peak_rms + 1e-6))
        cutoff_percentage = min(1.0, self.noise_floor / (self.rolling_peak_rms + 1e-6))
        
        self.bar_canvas.coords(self.fill_bar, 0, 0, int(280 * val_percentage), 14)
        self.bar_canvas.coords(self.line_cutoff, int(260 * cutoff_percentage), 0, int(260 * cutoff_percentage), 14)

        if self.running:
            # Active indicator updates
            self.panel_canvas.itemconfigure(self.gui_text_tracker, text="ACTIVE", fill="#00ffcc")
            
            mode = self.overlay_mode.get()

            # Behind flag activation (Only used/rendered in classic "dots" mode to prevent ring mode clutter)
            if self.text_active and mode != "ring":
                self.panel_canvas.itemconfigure(self.gui_text_tracker, text=f"ALARM REAR: {int(self.text_target_x*100)}%", fill="#ff3333")
                self.text_current_x += (self.text_target_x - self.text_current_x) * move_coef
                
                # Render behind text overlay
                text_pix_x = int(self.screen_width * self.text_current_x)
                self.canvas.coords(self.behind_text, text_pix_x, self.screen_height - 32)
                self.canvas.itemconfigure(self.behind_text, state='normal')
            else:
                self.canvas.itemconfigure(self.behind_text, state='hidden')

            # --- RENDER LOGIC FOR DIRECTIONAL HUD RING MODE ---
            if mode == "ring":
                # Ensure central anchor circle is visible
                self.canvas.itemconfigure(self.radar_center_circle, state="normal", outline="#222222")
                
                # Make sure normal dots are moved off-screen/hidden
                for item in self.dot_ui_items.values():
                    self.canvas.coords(item['trail2'], -100, -100, -100, -100)
                    self.canvas.coords(item['trail1'], -100, -100, -100, -100)
                    self.canvas.coords(item['halo'], -100, -100, -100, -100)
                    self.canvas.coords(item['core'], -100, -100, -100, -100)

                for i in range(self.max_slots):
                    coords = self.tracking_slots[i]
                    arc_item = self.radar_slots[i]['arc']
                    
                    if coords[4] > 0:
                        coords[4] -= 22.0 * dt
                        target_opacity_factor = 1.0
                    else:
                        target_opacity_factor = 0.0

                    coords[8] += (target_opacity_factor - coords[8]) * opacity_coef

                    if coords[8] > 0.01:
                        # Smooth directional coordinate interpolation
                        coords[0] += (coords[2] - coords[0]) * move_coef
                        
                        # Calculate angle:
                        # 1.0 (far left) -> 180 degrees
                        # 0.5 (center)   -> 90 degrees (facing up/neutral)
                        # 0.0 (far right) -> 0 degrees
                        current_x_normalized = coords[0]
                        angle_deg = current_x_normalized * 180.0
                        
                        # Setup color signature matching threat sector
                        if coords[5] == "left":
                            base_r, base_g, base_b = 255, 68, 68
                        elif coords[5] == "right":
                            base_r, base_g, base_b = 0, 238, 247
                        else:
                            base_r, base_g, base_b = 68, 255, 68
                            
                        # If behind is triggered globally, highlight slot as threat
                        if self.text_active and abs(current_x_normalized - self.text_target_x) < 0.15:
                            base_r, base_g, base_b = 255, 34, 34
                            angle_deg = 270.0 # Point direct down toward the behind threat zone

                        opacity_factor = 0.5 * coords[8]
                        faded_r = int(base_r * opacity_factor)
                        faded_g = int(base_g * opacity_factor)
                        faded_b = int(base_b * opacity_factor)
                        arc_color = f"#{faded_r:02x}{faded_g:02x}{faded_b:02x}"
                        
                        # Dynamically width scale of arcs based on threat distance/volume
                        arc_extent = 15 + int(coords[6] * 20)
                        arc_start = angle_deg - (arc_extent / 2)
                        
                        self.canvas.itemconfigure(arc_item, start=arc_start, extent=arc_extent, outline=arc_color, state="normal")
                    else:
                        self.canvas.itemconfigure(arc_item, state="hidden")

            # --- RENDER LOGIC FOR CLASSIC HORIZONTAL DOTS MODE ---
            else:
                # Ensure central anchor circle and arcs are hidden
                self.canvas.itemconfigure(self.radar_center_circle, state="hidden")
                for item in self.radar_slots.values():
                    self.canvas.itemconfigure(item['arc'], state="hidden")

                mouse_x = self.root.winfo_pointerx()
                mouse_y = self.root.winfo_pointery()

                for i in range(self.max_slots):
                    coords = self.tracking_slots[i]
                    
                    if coords[4] > 0:
                        coords[4] -= 22.0 * dt  
                        target_opacity_factor = 1.0
                    else:
                        target_opacity_factor = 0.0

                    coords[8] += (target_opacity_factor - coords[8]) * opacity_coef

                    if coords[8] > 0.01:
                        prev_pix_x = int(self.screen_width * coords[0])
                        prev_pix_y = int(self.screen_height * coords[1])
                        
                        coords[0] += (coords[2] - coords[0]) * move_coef
                        coords[1] += (coords[3] - coords[1]) * move_coef
                        
                        pix_x = int(self.screen_width * coords[0])
                        pix_y = int(self.screen_height * coords[1])
                        
                        if math.sqrt((pix_x - mouse_x)**2 + (pix_y - mouse_y)**2) < 15:
                            coords[8] = 0.0  
                            self.canvas.coords(self.dot_ui_items[i]['halo'], -100, -100, -100, -100)
                            self.canvas.coords(self.dot_ui_items[i]['core'], -100, -100, -100, -100)
                            self.canvas.coords(self.dot_ui_items[i]['trail1'], -100, -100, -100, -100)
                            self.canvas.coords(self.dot_ui_items[i]['trail2'], -100, -100, -100, -100)
                            coords[7] = []  
                            continue

                        dist_from_center = abs(coords[0] - 0.5)  
                        edge_growth_factor = 1.0 + (dist_from_center * 0.8) 
                        
                        target_radius = (self.BASE_RADIUS + (coords[6] * self.MAX_BONUS_RADIUS)) * edge_growth_factor
                        coords[9] += (target_radius - coords[9]) * size_coef  
                        core_radius = int(coords[9])
                        halo_radius = core_radius + 4
                        
                        if coords[5] == "left":
                            base_r, base_g, base_b = 255, 68, 68
                        elif coords[5] == "right":
                            base_r, base_g, base_b = 0, 238, 247
                        else:
                            base_r, base_g, base_b = 68, 255, 68

                        opacity_factor = 0.5 * coords[8]

                        if opacity_factor > 0.01:
                            faded_r = int(base_r * opacity_factor)
                            faded_g = int(base_g * opacity_factor)
                            faded_b = int(base_b * opacity_factor)
                            core_color = f"#{faded_r:02x}{faded_g:02x}{faded_b:02x}"

                            history = coords[7]
                            history.insert(0, (pix_x, pix_y))
                            if len(history) > 3:
                                history.pop()

                            speed_px = math.sqrt((pix_x - prev_pix_x)**2 + (pix_y - prev_pix_y)**2)
                            
                            if len(history) > 1 and speed_px > 3:
                                t1_x, t1_y = history[1]
                                t1_radius = int(core_radius * 0.7)
                                t1_opacity = opacity_factor * 0.5
                                t1_color = f"#{int(base_r * t1_opacity):02x}{int(base_g * t1_opacity):02x}{int(base_b * t1_opacity):02x}"
                                self.canvas.itemconfigure(self.dot_ui_items[i]['trail1'], fill=t1_color, outline="")
                                self.canvas.coords(self.dot_ui_items[i]['trail1'], t1_x - t1_radius, t1_y - t1_radius, t1_x + t1_radius, t1_y + t1_radius)
                            else:
                                self.canvas.coords(self.dot_ui_items[i]['trail1'], -100, -100, -100, -100)

                            if len(history) > 2 and speed_px > 5:
                                t2_x, t2_y = history[2]
                                t2_radius = int(core_radius * 0.45)
                                t2_opacity = opacity_factor * 0.25
                                t2_color = f"#{int(base_r * t2_opacity):02x}{int(base_g * t2_opacity):02x}{int(base_b * t2_opacity):02x}"
                                self.canvas.itemconfigure(self.dot_ui_items[i]['trail2'], fill=t2_color, outline="")
                                self.canvas.coords(self.dot_ui_items[i]['trail2'], t2_x - t2_radius, t2_y - t2_radius, t2_x + t2_radius, t2_y + t2_radius)
                            else:
                                self.canvas.coords(self.dot_ui_items[i]['trail2'], -100, -100, -100, -100)

                            self.canvas.itemconfigure(self.dot_ui_items[i]['core'], fill=core_color)
                            self.canvas.itemconfigure(self.dot_ui_items[i]['halo'], outline=core_color)
                            
                            self.canvas.coords(self.dot_ui_items[i]['core'], pix_x - core_radius, pix_y - core_radius, pix_x + core_radius, pix_y + core_radius)
                            self.canvas.coords(self.dot_ui_items[i]['halo'], pix_x - halo_radius, pix_y - halo_radius, pix_x + halo_radius, pix_y + halo_radius)
                        else:
                            self.canvas.coords(self.dot_ui_items[i]['halo'], -100, -100, -100, -100)
                            self.canvas.coords(self.dot_ui_items[i]['core'], -100, -100, -100, -100)
                            self.canvas.coords(self.dot_ui_items[i]['trail1'], -100, -100, -100, -100)
                            self.canvas.coords(self.dot_ui_items[i]['trail2'], -100, -100, -100, -100)
                    else:
                        self.canvas.coords(self.dot_ui_items[i]['halo'], -100, -100, -100, -100)
                        self.canvas.coords(self.dot_ui_items[i]['core'], -100, -100, -100, -100)
                        self.canvas.coords(self.dot_ui_items[i]['trail1'], -100, -100, -100, -100)
                        self.canvas.coords(self.dot_ui_items[i]['trail2'], -100, -100, -100, -100)
                        coords[7] = []  
        else:
            self.bar_canvas.coords(self.fill_bar, 0, 0, 0, 14)

        self.root.after(4, self.animate_loop)

    def on_close(self):
        self.running = False
        self.root.destroy()
        sys.exit()

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioRadarApp(root)
    root.mainloop()
