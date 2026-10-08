# QISKIT INTEGRATION: renders QAOA circuits with QuantumCircuit.draw("mpl") as SVG for the dashboard.
"""Circuit diagram as an SVG string."""

import io

import matplotlib

matplotlib.use("Agg")  # no GUI; safe in server threads
import matplotlib.pyplot as plt  # noqa: E402
from qiskit import QuantumCircuit  # noqa: E402

MAX_DRAW_QUBITS = 9  # larger circuits produce unreadable multi-MB drawings


def circuit_svg(circuit: QuantumCircuit) -> str | None:
    if circuit.num_qubits > MAX_DRAW_QUBITS:
        return None
    fig = circuit.draw(output="mpl", fold=-1)
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
