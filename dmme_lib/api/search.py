# --- dmme_lib/api/search.py ---
import logging
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint("search", __name__)
log = logging.getLogger("dmme.api")


@bp.route("/", methods=["GET"])
def search():
    """
    Performs a vector search across one or all knowledge bases.
    Query Parameters:
        q (str): The search query text.
        scope (str): The knowledge base to search in, or 'all'.
    """
    query_text = request.args.get("q")
    scope = request.args.get("scope", "all")

    if not query_text:
        return jsonify({"error": "Missing required query parameter 'q'"}), 400

    log.info("Performing search for '%s' in scope '%s'", query_text, scope)
    try:
        results = current_app.vector_store.search_collections(query_text, scope)
        return jsonify(results)
    except Exception as e:
        log.error("Search failed for query '%s': %s", query_text, e, exc_info=True)
        return jsonify({"error": "An internal error occurred during search."}), 500
