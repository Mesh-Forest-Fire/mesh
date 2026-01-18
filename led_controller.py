import RPi.GPIO as GPIO
import time
import atexit

LED_PIN = 17   # GPIO17

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)

def flash_led(seconds):
    # print("Turning LED ON")
    GPIO.output(LED_PIN, GPIO.HIGH)
    time.sleep(seconds)

    # print("Turning LED OFF")
    GPIO.output(LED_PIN, GPIO.LOW)

def cleanup():
    GPIO.cleanup()

atexit.register(cleanup)
    
