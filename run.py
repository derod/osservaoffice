import os
from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_ENV", "development") != "production"
    socketio.run(app, debug=debug, host="0.0.0.0", port=port)
