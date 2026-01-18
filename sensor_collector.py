from grove.adc import ADC
import math
import sqlite3
import time
import adafruit_dht
import board
import atexit

adc = ADC()
dhtDevice = adafruit_dht.DHT22(board.D4)  # GPIO4 (Pin 7)

# Temperature constants
B = 4275
R0 = 100000


def read_temperature():
    value = adc.read(0)   # A0
    R = 1023.0 / value - 1.0
    R = R0 * R
    temp = 1.0 / (math.log(R/R0)/B + 1/298.15) - 273.15
    return temp

def read_air_quality():
    return adc.read(4)  # A1

def read_light_level():
    return adc.read(2)  # A2

def read_humidity():
    # This ones reads from a DHT22 sensor connected to GPIO4
    try:
        humidity = dhtDevice.humidity
    except RuntimeError as error:
        humidity = None
    return humidity

def cleanup():
    """Clean up GPIO resources"""
    dhtDevice.exit()

# Register cleanup to run on exit
atexit.register(cleanup)

def main():

    while True:
        temp = read_temperature()
        air = read_air_quality()
        light = read_light_level()
        humidity = read_humidity()

        print(f"Temp: {temp:.2f}°C | Air: {air} | Light: {light} | Humidity: {humidity}")

        time.sleep(2)

if __name__ == "__main__":
    main()