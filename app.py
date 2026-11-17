from flask import Flask
import requests
import logging

app = Flask(__name__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@app.route("/")
def index():
    r = requests.get("https://httpstatus.io")
    logger.info(f"text_filter fetched httpstatus.io: {r.status_code}")
    return f"text_filter fetched httpstatus.io: {r.status_code}"

if __name__ == "__main__":
    print("Starting Flask server on port 8080...")
    # 0.0.0.0 so a published container port is reachable from the host.
    app.run(host="0.0.0.0", port=8080)