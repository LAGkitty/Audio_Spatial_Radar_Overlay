# Audio Spatial Radar Overlay

A high-sensitivity, real-time spatial audio visualization tool written in Python. It captures system/microphone loopback audio, extracts spatial positioning using phase correlation and FFT (Fast Fourier Transform), and renders a completely click-through visual HUD overlay directly onto your screen.

Designed to assist with directional sound tracking (such as identifying the origin of footsteps, gunshots, or environmental cues in games or simulation software).

## Features

- **Click-Through Transparent Overlay:** The HUD is completely transparent and inputs pass directly through it, meaning it won't interfere with your gameplay or desktop tasks.
- **Real-Time Spatial DSP:** Utilizes cross-correlation between left and right channels to calculate exact horizontal ($X$-axis) positioning.
- **Frequency Mapping:** Maps sound frequencies logarithmically to the vertical ($Y$-axis) plane.
- **Dynamic Cluster Merging:** Groups nearby frequencies together to prevent visual noise and isolate distinct audio sources.
- **Behind/Rear Sound Detection:** Advanced phase-inversion algorithms trigger a prominent `▲ BEHIND ▲` visual alert when a rear-configured ambient sound or echo is detected.
- **Manual Sensitivity Calibration:** Easily adjust the manual noise floor threshold using the control dashboard.

---

## Installation & Setup

### 1. Prerequisites
Ensure you have Python 3.8+ installed on your system.

### 2. Install Dependencies
This project requires several third-party libraries for audio processing and hardware interfacing. Install them via pip:

```bash
pip install soundcard numpy

```

### 3. Running the Application

```bash
python [Drag the chosen python]

```

### 4. Linux Execution Note

On Linux, you must run the application with the following environment variable to ensure the overlay displays correctly:

```bash
QT_QPA_PLATFORM=xcb python3 radarV3Linux-test.py
