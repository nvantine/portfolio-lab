"""Container-only protocol. Never execute this module on the host."""
import contextlib
import json
import os
import random
import sys
import tempfile

import numpy as np
import pandas as pd


def notebook(payload):
    import nbformat
    from nbclient import NotebookClient
    # .ipynb files serialize multiline sources as arrays; reads rejoins them.
    book = nbformat.reads(json.dumps(payload["notebook"]), as_version=4)
    nbformat.validate(book)
    # Remove all pre-existing outputs, including executable HTML/JS.
    for cell in book.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        pd.DataFrame(payload["prices"], index=payload["dates"], columns=payload["tickers"]).to_csv(directory + "/prices.csv", index_label="date")
        client = NotebookClient(book, timeout=60, kernel_name="python3", resources={"metadata": {"path": directory}}, allow_errors=False)
        client.execute()
    # The host receives plain text only. Arbitrary rich outputs are discarded.
    cells = []
    for cell in book.cells:
        outputs = []
        for output in cell.get("outputs", []):
            value = output.get("text", output.get("data", {}).get("text/plain", ""))
            outputs.append(str(value)[:20000])
        cells.append({"type": cell.cell_type, "source": cell.source[:20000], "outputs": outputs})
    return {"cells": cells, "note": "Training data only. HTML, JavaScript, and rich output discarded."}


def main():
    protocol = sys.stdout
    namespace = {}
    with open(os.devnull, "w") as sink:
        for line in sys.stdin:
            try:
                payload = json.loads(line)
                with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                    action = payload["action"]
                    if action == "load":
                        random.seed(payload["seed"])
                        np.random.seed(payload["seed"])
                        exec(compile(payload["source"], "strategy.py", "exec"), namespace)
                        if not callable(namespace.get("target_weights")):
                            raise ValueError("Missing strategy entrypoint")
                        result = "loaded"
                    elif action == "weights":
                        frame = pd.DataFrame(payload["prices"], index=pd.to_datetime(payload["dates"]), columns=payload["tickers"])
                        result = namespace["target_weights"](frame, payload["current"], payload["parameters"])
                    elif action == "notebook":
                        result = notebook(payload)
                    else:
                        raise ValueError("Unknown action")
                response = json.dumps({"ok": True, "result": result}, allow_nan=False)
            except Exception:
                response = '{"ok":false,"result":null}'
            protocol.write(response + "\n")
            protocol.flush()


if __name__ == "__main__":
    main()
