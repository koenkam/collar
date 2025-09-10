#import simpleNamespace
from types import SimpleNamespace   

#fulldaydata is a list of simpleNamespace objects with fields: date, open, high, low, close
#for each fulldaydata list entry (from position 26 onward), calculate macd and signal
#and store the end-result as fields of fulldaydata elemenents
def macd(fulldaydata, short=12, long=26, signal=9):
    ema_short = []
    ema_long = []
    macd = []
    signal_line = []
    histogram = []

    k_short = 2 / (short + 1)
    k_long = 2 / (long + 1)
    k_signal = 2 / (signal + 1)

    for i in range(len(fulldaydata)):
        close_price = fulldaydata[i].close

        if i == 0:
            ema_short.append(close_price)
            ema_long.append(close_price)
            macd.append(0)
            signal_line.append(0)
            histogram.append(0)
        else:
            new_ema_short = (close_price - ema_short[-1]) * k_short + ema_short[-1]
            new_ema_long = (close_price - ema_long[-1]) * k_long + ema_long[-1]
            ema_short.append(new_ema_short)
            ema_long.append(new_ema_long)

            new_macd = new_ema_short - new_ema_long
            macd.append(new_macd)

            if i < long + signal - 1:
                signal_line.append(0)
                histogram.append(0)
            elif i == long + signal - 1:
                signal_line.append(new_macd)
                histogram.append(new_macd - new_macd)
            else:
                new_signal = (new_macd - signal_line[-1]) * k_signal + signal_line[-1]
                signal_line.append(new_signal)
                histogram.append(new_macd - new_signal)

        # Store the calculated values in the fulldaydata object
        fulldaydata[i].ema_short = ema_short[-1]
        fulldaydata[i].ema_long = ema_long[-1]
        fulldaydata[i].macd = macd[-1]
        fulldaydata[i].signal_line = signal_line[-1]
        fulldaydata[i].histogram = histogram[-1]
    return fulldaydata

def rsi(fulldaydata, period=14):
    gains = []
    losses = []

    for i in range(len(fulldaydata)):
        if i == 0:
            gains.append(0)
            losses.append(0)
            fulldaydata[i].rsi = 0
        else:
            change = fulldaydata[i].close - fulldaydata[i-1].close
            gain = max(change, 0)
            loss = max(-change, 0)
            gains.append(gain)
            losses.append(loss)

            if i < period:
                fulldaydata[i].rsi = 0
            elif i == period:
                avg_gain = sum(gains[1:period+1]) / period
                avg_loss = sum(losses[1:period+1]) / period
                rs = avg_gain / avg_loss if avg_loss != 0 else 0
                fulldaydata[i].rsi = 100 - (100 / (1 + rs))
            else:
                avg_gain = (gains[i] + (period - 1) * (fulldaydata[i-1].avg_gain if hasattr(fulldaydata[i-1], 'avg_gain') else 0)) / period
                avg_loss = (losses[i] + (period - 1) * (fulldaydata[i-1].avg_loss if hasattr(fulldaydata[i-1], 'avg_loss') else 0)) / period
                rs = avg_gain / avg_loss if avg_loss != 0 else 0
                fulldaydata[i].rsi = 100 - (100 / (1 + rs))
                fulldaydata[i].avg_gain = avg_gain
                fulldaydata[i].avg_loss = avg_loss

    return fulldaydata

def slow_stochastic(fulldaydata, k_period=14, d_period=3):
    for i in range(len(fulldaydata)):
        if i < k_period - 1:
            fulldaydata[i].slow_k = 0
            fulldaydata[i].slow_d = 0
        else:
            lowest_low = min(fulldaydata[j].low for j in range(i - k_period + 1, i + 1))
            highest_high = max(fulldaydata[j].high for j in range(i - k_period + 1, i + 1))
            fulldaydata[i].slow_k = ((fulldaydata[i].close - lowest_low) / (highest_high - lowest_low)) * 100 if highest_high != lowest_low else 0

            if i < k_period - 1 + d_period - 1:
                fulldaydata[i].slow_d = 0
            else:
                fulldaydata[i].slow_d = sum(fulldaydata[j].slow_k for j in range(i - d_period + 1, i + 1)) / d_period

    return fulldaydata

def powerx(fulldaydata):
    for day in fulldaydata:
        if day.macd > day.signal_line and day.rsi > 50 and day.slow_k > 50:
            day.powerx_signal = "BUY"
        elif day.macd < day.signal_line and day.rsi < 50 and day.slow_k < 50:
            day.powerx_signal = "SELL"
        else:
            day.powerx_signal = "HOLD"
    return fulldaydata

fulldayfilename = "SPX_full_1day.csv"
#read fulldayfilename into a list of simpleNamespace objects
# each line has the format:2000-11-27,1341.77,1362.5,1341.77,1348.97
# date, open, high, low, close
with open(fulldayfilename, 'r') as f:
    lines = f.readlines()
    fulldaydata = []
    for line in lines[1:]:
        date, open_, high, low, close = line.strip().split(',')
        fulldaydata.append(SimpleNamespace(date=date, open=float(open_), high=float(high), low=float(low), close=float(close)))

print(f"Read {len(fulldaydata)} days of data from {fulldayfilename}")

macd(fulldaydata)
rsi(fulldaydata)
slow_stochastic(fulldaydata)
powerx(fulldaydata)

for day in fulldaydata:
    print(f"{day.date}: MACD={day.macd:.2f}, Signal={day.signal_line:.2f}, RSI={day.rsi:.2f}, SlowK={day.slow_k:.2f}, PowerX Signal={day.powerx_signal}, Close={day.close}")


def plot_powerx_analysis(fulldaydata, filename='powerx_analysis.png'):
    """
    Create a comprehensive plot of PowerX trading analysis with 4 subplots:
    1. Close price with buy/sell signals
    2. MACD and Signal Line
    3. RSI (Relative Strength Index)
    4. Slow Stochastic %K
    
    Args:
        fulldaydata: List of SimpleNamespace objects containing trading data
        filename: Output filename for the plot (default: 'powerx_analysis.png')
    """
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import numpy as np
    
    # Extract data for plotting
    dates = [day.date for day in fulldaydata]
    closes = [day.close for day in fulldaydata]
    macds = [day.macd for day in fulldaydata]
    signals = [day.signal_line for day in fulldaydata]
    rsis = [day.rsi for day in fulldaydata]
    slow_ks = [day.slow_k for day in fulldaydata]
    powerx_signals = [day.powerx_signal for day in fulldaydata]
    x = np.arange(len(dates))

    # Create the figure with 4 subplots
    fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(15, 10), sharex=True)
    
    # Plot 1: Close price with PowerX signals
    ax1.plot(x, closes, label='Close Price', color='blue')
    for i in range(len(powerx_signals)):
        if powerx_signals[i] == "BUY":
            ax1.annotate('↑', (x[i], closes[i]), textcoords="offset points", xytext=(0,10), ha='center', color='green')
        elif powerx_signals[i] == "SELL":
            ax1.annotate('↓', (x[i], closes[i]), textcoords="offset points", xytext=(0,-15), ha='center', color='red')
    ax1.set_title('Close Price with PowerX Signals')
    ax1.legend()
    ax1.grid()  
    
    # Plot 2: MACD and Signal Line
    ax2.plot(x, macds, label='MACD', color='orange')
    ax2.plot(x, signals, label='Signal Line', color='purple')
    ax2.set_title('MACD and Signal Line')
    ax2.legend()
    ax2.grid()  
    
    # Plot 3: RSI
    ax3.plot(x, rsis, label='RSI', color='green')
    ax3.axhline(70, color='red', linestyle='--')
    ax3.axhline(30, color='red', linestyle='--')
    ax3.set_title('Relative Strength Index (RSI)')
    ax3.legend()
    ax3.grid()  
    
    # Plot 4: Slow Stochastic %K
    ax4.plot(x, slow_ks, label='Slow %K', color='brown')
    ax4.axhline(80, color='red', linestyle='--')
    ax4.axhline(20, color='red', linestyle='--')
    ax4.set_title('Slow Stochastic %K')
    ax4.legend()
    ax4.grid()  
    
    # Format x-axis with dates
    plt.xticks(x[::len(x)//10], [dates[i] for i in range(0, len(dates), len(dates)//10)], rotation=45)
    plt.tight_layout()
    
    # Save the plot
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"Plot saved as {filename}")
    plt.close()


# Generate the PowerX analysis plot
plot_powerx_analysis(fulldaydata)