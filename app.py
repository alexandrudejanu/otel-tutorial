from flask import Flask
import requests
import logging

app = Flask(__name__)

logger = logging.getLogger(__name__)

@app.route("/")
def index():
    r = requests.get("https://httpstatus.io")
    logger.info(f"Fetched example.com: {r.status_code}")
    return f"Fetched example.com: {r.status_code}"

if __name__ == "__main__":
    print("Starting Flask server on port 8080...")
    app.run(port=8080)