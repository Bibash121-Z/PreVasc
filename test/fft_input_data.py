import serial
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from scipy.signal import find_peaks
import time

# -----------------------------

PORT = "COM5"      # Change
BAUD = 115200

BLOCK = 1024

# -----------------------------

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)

fig,(ax1,ax2)=plt.subplots(2,1,figsize=(12,8))

time_plot, = ax1.plot([],[],lw=1)
fft_plot, = ax2.plot([],[],lw=1)

txt=ax2.text(
    0.98,
    0.98,
    "",
    transform=ax2.transAxes,
    ha="right",
    va="top",
    family="monospace"
)

ax1.set_title("Signal")
ax2.set_title("Spectrum")

def get_block():

    data=[]

    t0=time.perf_counter()

    while len(data)<BLOCK:

        try:
            line=ser.readline().decode(errors="ignore").strip()

            if line=="":
                continue

            value=int(line)

            if 0<=value<=1023:
                data.append(value)

        except:
            pass

    t1=time.perf_counter()

    fs=BLOCK/(t1-t0)

    return np.array(data,dtype=float),fs


def update(frame):

    y,fs=get_block()

    x=np.arange(len(y))

    time_plot.set_data(x,y)

    ax1.set_xlim(0,BLOCK)
    ax1.set_ylim(0,1023)

    y=y-np.mean(y)

    window=np.hanning(BLOCK)

    Y=np.fft.rfft(y*window)

    mag=np.abs(Y)

    freq=np.fft.rfftfreq(BLOCK,1/fs)

    fft_plot.set_data(freq,mag)

    ax2.set_xlim(0,fs/2)
    ax2.set_ylim(0,max(mag)*1.05+1)

    peaks,_=find_peaks(mag,height=max(mag)*0.15)

    if len(peaks):

        order=np.argsort(mag[peaks])[::-1][:8]

        s=""

        for i in order:
            s+=f"{freq[peaks[i]]:7.1f} Hz\n"

        txt.set_text(s)

    else:

        txt.set_text("No peaks")

    return time_plot,fft_plot,txt

ani=FuncAnimation(fig,update,interval=1,blit=False)

plt.tight_layout()
plt.show()

ser.close()