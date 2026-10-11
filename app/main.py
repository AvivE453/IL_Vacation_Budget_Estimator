import datetime

from flask import Flask

from app.db import PoolExhausted
from app.routes.data_quality import bp as data_quality_bp
from app.routes.estimate import bp as estimate_bp
from app.routes.history import bp as history_bp
from app.routes.home import bp as home_bp
from etl.common.config import FLASK_SECRET_KEY


def create_app():
    app = Flask(__name__)
    if not FLASK_SECRET_KEY:
        raise RuntimeError("FLASK_SECRET_KEY is not set -- see .env.example")
    app.secret_key = FLASK_SECRET_KEY
    # Anonymous per-browser session (see app/session_id.py::get_session_id)
    # survives 30 days, not just until the browser closes -- so /history stays
    # useful across separate visits, not just one sitting.
    app.permanent_session_lifetime = datetime.timedelta(days=30)

    app.register_blueprint(home_bp)
    app.register_blueprint(estimate_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(data_quality_bp)
    app.register_error_handler(PoolExhausted, lambda e: ("Server busy, try again shortly", 503, {"Retry-After": "1"}))
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
