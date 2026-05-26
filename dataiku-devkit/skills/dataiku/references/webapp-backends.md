# Webapp Backends

Backend patterns for DSS plugin webapps. DSS injects the Flask `app`; do not create your own Flask app.

## Standard Backend (Flask)

> **CRITICAL**: DSS injects a pre-configured `app` (Flask instance) into the global scope of `backend.py`.
> Do **NOT** create your own `app = Flask(__name__)` — this breaks DSS health checks (`/__ping`)
> and the `dataiku.customwebapp` module won't be available in your context.
> This applies only to plugin webapps (HTML/JS tab mode). Dash/Streamlit backends define their own app object.

### backend.py Template

```python
"""
My Dashboard Backend

Flask-based backend for the webapp.
DSS provides 'app' (Flask instance) in global scope — do NOT create your own.
"""
import json
import logging
from flask import request, jsonify
from concurrent.futures import ThreadPoolExecutor
import dataiku
from dataiku.customwebapp import get_webapp_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get webapp configuration (available because DSS injects the context)
webapp_config = get_webapp_config()
input_dataset = webapp_config.get("input_dataset")
llm_id = webapp_config.get("llm_id")

# 'app' is provided by DSS — just use @app.route() directly
# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=4)


@app.route("/api/data")
def get_data():
    """Fetch data from the configured dataset."""
    try:
        if not input_dataset:
            return jsonify({"error": "No dataset configured"}), 400

        ds = dataiku.Dataset(input_dataset)
        df = ds.get_dataframe()

        # Apply optional filters from query params
        limit = request.args.get("limit", type=int)
        if limit:
            df = df.head(limit)

        return jsonify({
            "data": df.to_dict(orient="records"),
            "columns": list(df.columns),
            "total": len(df)
        })
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyze data using LLM."""
    try:
        payload = request.get_json()
        query = payload.get("query", "")
        context = payload.get("context", "")

        if not llm_id:
            return jsonify({"error": "No LLM configured"}), 400

        client = dataiku.api_client()
        project = client.get_default_project()
        llm = project.get_llm(llm_id)

        completion = llm.new_completion()
        completion.with_message(f"Context: {context}\n\nQuery: {query}", role="user")
        response = completion.execute()

        return jsonify({
            "analysis": response.text,
            "model": llm_id
        })
    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/schema")
def get_schema():
    """Get dataset schema."""
    try:
        if not input_dataset:
            return jsonify({"error": "No dataset configured"}), 400

        ds = dataiku.Dataset(input_dataset)
        schema = ds.read_schema()

        return jsonify({"schema": schema})
    except Exception as e:
        logger.error(f"Error fetching schema: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/config")
def get_config():
    """Return webapp configuration to frontend."""
    return jsonify({
        "dataset": input_dataset,
        "llm": llm_id,
        "refresh_interval": webapp_config.get("refresh_interval", 60),
        "chart_type": webapp_config.get("chart_type", "line")
    })
```

### Socket.IO for Real-Time Updates

```python
from flask_socketio import SocketIO, emit

# Initialize Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*", path="/stream")


@socketio.on("connect")
def handle_connect():
    logger.info("Client connected")
    emit("status", {"connected": True})


@socketio.on("subscribe")
def handle_subscribe(data):
    """Subscribe to data updates."""
    channel = data.get("channel", "default")
    emit("subscribed", {"channel": channel})


@socketio.on("query")
def handle_query(data):
    """Handle streaming LLM query."""
    query = data.get("query", "")

    try:
        client = dataiku.api_client()
        project = client.get_default_project()
        llm = project.get_llm(llm_id)

        completion = llm.new_completion()
        completion.with_message(query, role="user")

        # Stream response chunks
        for chunk in completion.execute_streamed():
            emit("response_chunk", {"text": chunk.text})

        emit("response_complete", {"status": "done"})
    except Exception as e:
        emit("error", {"message": str(e)})


@socketio.on("disconnect")
def handle_disconnect():
    logger.info("Client disconnected")
```

---
