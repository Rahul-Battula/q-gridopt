# QISKIT INTEGRATION: builds the QAOA circuit with qiskit.circuit.library.qaoa_ansatz and trains
# its angles (gamma, beta) with qiskit_aer.primitives.EstimatorV2 in exact mode + SciPy COBYLA.
"""QAOA circuit and training.

Plain English: QAOA starts with every battery plan equally likely, then alternates two steps p
times: a "cost" step that nudges each plan by its energy (angle gamma) and a "mixer" step that
lets plans swap probability (angle beta). Training searches for angles that make cheap plans
likely. Afterwards we sample the circuit and read off battery plans.

Technical:
- ansatz = qaoa_ansatz(H, reps=p): |+>^n, then p layers of exp(-i gamma_k H) exp(-i beta_k sum X).
  (The QAOAAnsatz CLASS is deprecated since Qiskit 2.1; the function is its replacement.)
- Training minimises <H> on the Aer EstimatorV2 in exact mode (statevector, no shot noise).
  It matches qiskit.primitives.StatevectorEstimator to ~1e-13 but is ~50x faster on 18 qubits
  (user-approved deviation from the original plan; see tests/test_qaoa.py).
- H is divided by its largest |coefficient| before training so the angles live on a sensible
  scale. This does not change which state is cheapest; energies are converted back to $.
- p = 1: grid search over (gamma, beta), then COBYLA from the best grid points.
  p > 1: COBYLA from the INTERP warm start (Zhou et al., PRX 2020) built from the p-1 optimum,
  plus random starts. The lowest <H> wins.
"""

import re
import time
from dataclasses import dataclass, field

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import qaoa_ansatz
from qiskit.quantum_info import SparsePauliOp
from qiskit_aer import AerSimulator
from qiskit_aer.primitives import EstimatorV2 as AerEstimator
from scipy.optimize import minimize

GAMMA_RANGE = (-np.pi, np.pi)
BETA_RANGE = (0.0, np.pi)  # beta has period pi; (gamma, beta) -> (-gamma, -beta) is a symmetry
GRID = (24, 12)  # gamma x beta points for the p = 1 grid search
GRID_STARTS = 3  # COBYLA starts taken from the best grid points (p = 1)
RANDOM_STARTS = 2  # extra random COBYLA starts for p > 1
MAXITER = 300
RHOBEG = 0.3


@dataclass
class CostOperator:
    hamiltonian: SparsePauliOp  # scaled: max |coefficient| = 1
    scale: float  # $ per unit of scaled energy
    offset: float  # $; energy in $ = <scaled H> * scale + offset
    # XY mixer (one-hot tiers only): one block of qubits per hour. The start state is then an equal
    # superposition of the valid one-hot states of every block (a W state per block).
    # None = the standard X mixer on |+>^n.
    xy_blocks: list[list[int]] | None = None

    def to_dollars(self, scaled_energy: float) -> float:
        return scaled_energy * self.scale + self.offset


@dataclass
class TrainResult:
    reps: int
    gammas: list[float]
    betas: list[float]
    energy_scaled: float
    energy_dollars: float
    evaluations: int
    seconds: float
    starts: list[dict] = field(default_factory=list)  # per start: initial point, final energy


def make_cost_operator(op: SparsePauliOp, offset: float) -> CostOperator:
    scale = float(np.max(np.abs(op.coeffs.real)))
    return CostOperator(hamiltonian=(op / scale).simplify(), scale=scale, offset=offset)


def xy_mixer(blocks: list[list[int]], num_qubits: int) -> SparsePauliOp:
    """Ring XY mixer: sum of (XX + YY) over neighbouring qubits inside each block.

    Plain English: it only ever MOVES a "1" to a neighbouring position inside a block, so a block
    that holds exactly one 1 (one battery level chosen for that hour) keeps exactly one 1. Every
    shot then decodes to a valid one-level-per-hour plan.
    """
    terms = []
    for block in blocks:
        for a, b in zip(block, block[1:] + block[:1]):
            terms += [("XX", [a, b], 1.0), ("YY", [a, b], 1.0)]
    return SparsePauliOp.from_sparse_list(terms, num_qubits=num_qubits)


def xy_start_state(blocks: list[list[int]], num_qubits: int) -> QuantumCircuit:
    """Start state: every block in the W state, an equal superposition of "exactly one 1 here".

    Plain English: every battery level is equally likely for each hour, and no invalid plan (two
    levels, or none) is possible. Starting from ONE fixed plan instead would leave the cost layer
    with nothing to act on, and the optimiser gets stuck (measured: P(optimal) stayed at 0).
    Construction: put a 1 on the first qubit, then repeatedly pass a share of its amplitude on to
    the next qubit with a controlled rotation and a CX.
    """
    qc = QuantumCircuit(num_qubits)
    for block in blocks:
        width = len(block)
        qc.x(block[0])
        for i in range(width - 1):
            theta = 2 * np.arccos(np.sqrt(1 / (width - i)))
            qc.cry(theta, block[i], block[i + 1])
            qc.cx(block[i + 1], block[i])
    return qc


def qaoa_circuit(cost: CostOperator, reps: int) -> QuantumCircuit:
    """The abstract QAOA circuit (unmeasured, symbolic angles), before any transpilation."""
    if cost.xy_blocks is None:
        return qaoa_ansatz(cost.hamiltonian, reps=reps)
    n = cost.hamiltonian.num_qubits
    return qaoa_ansatz(cost.hamiltonian, reps=reps, mixer_operator=xy_mixer(cost.xy_blocks, n),
                       initial_state=xy_start_state(cost.xy_blocks, n))


def build_ansatz(cost: CostOperator, reps: int) -> QuantumCircuit:
    """Unmeasured QAOA circuit, transpiled to Aer's gate set (parameters stay symbolic)."""
    return transpile(qaoa_circuit(cost, reps), AerSimulator(method="statevector"))


def parameter_values(circuit: QuantumCircuit, gammas, betas) -> np.ndarray:
    """Angle vector in circuit.parameters order. Binds by NAME (Qiskit sorts beta before gamma)."""
    values = []
    for prm in circuit.parameters:
        match = re.fullmatch(r"(β|γ)\[(\d+)\]", prm.name)
        if match is None:
            raise ValueError(f"unexpected QAOA parameter {prm.name}")
        values.append((betas if match[1] == "β" else gammas)[int(match[2])])
    return np.array(values, dtype=float)


def exact_estimator() -> AerEstimator:
    return AerEstimator(options={"backend_options": {"method": "statevector"},
                                 "run_options": {"approximation": True}})


def expectation(circuit, hamiltonian, values: np.ndarray, estimator=None) -> np.ndarray:
    """Exact <H> for one angle vector (shape (P,)) or many (shape (N, P))."""
    est = estimator or exact_estimator()
    return np.asarray(est.run([(circuit, hamiltonian, values)], precision=0).result()[0].data.evs)


def interp_init(gammas: list[float], betas: list[float]) -> tuple[list[float], list[float]]:
    """INTERP: stretch a depth-p schedule to depth p+1."""
    def stretch(x):
        p = len(x)
        padded = [0.0, *x, 0.0]
        return [((i - 1) / p) * padded[i - 1] + ((p - i + 1) / p) * padded[i] for i in range(1, p + 2)]
    return stretch(gammas), stretch(betas)


def train(cost: CostOperator, reps: int, seed: int = 7,
          warm_start: TrainResult | None = None) -> TrainResult:
    circuit = build_ansatz(cost, reps)
    est = exact_estimator()
    rng = np.random.default_rng(seed)
    evaluations = 0
    start_time = time.perf_counter()

    def split(x):
        return list(x[:reps]), list(x[reps:])  # optimiser vector = [gammas..., betas...]

    def objective(x):
        nonlocal evaluations
        evaluations += 1
        g, b = split(x)
        return float(expectation(circuit, cost.hamiltonian, parameter_values(circuit, g, b), est))

    starts: list[np.ndarray] = []
    if reps == 1:
        gs = np.linspace(*GAMMA_RANGE, GRID[0])
        bs = np.linspace(*BETA_RANGE, GRID[1], endpoint=False)
        grid = np.array([(g, b) for g in gs for b in bs])
        evs = expectation(circuit, cost.hamiltonian,
                          np.array([parameter_values(circuit, [g], [b]) for g, b in grid]), est)
        evaluations += len(grid)
        starts += [grid[i] for i in np.argsort(evs)[:GRID_STARTS]]
    else:
        if warm_start is not None and warm_start.reps == reps - 1:
            g, b = interp_init(warm_start.gammas, warm_start.betas)
            starts.append(np.array(g + b))
        for _ in range(RANDOM_STARTS):
            starts.append(np.concatenate([rng.uniform(*GAMMA_RANGE, reps), rng.uniform(*BETA_RANGE, reps)]))

    best, log = None, []
    for x0 in starts:
        res = minimize(objective, x0, method="COBYLA", options={"maxiter": MAXITER, "rhobeg": RHOBEG})
        log.append({"initial": [float(v) for v in x0], "energy_scaled": float(res.fun)})
        if best is None or res.fun < best.fun:
            best = res

    gammas, betas = split(best.x)
    return TrainResult(
        reps=reps, gammas=[float(v) for v in gammas], betas=[float(v) for v in betas],
        energy_scaled=float(best.fun), energy_dollars=cost.to_dollars(float(best.fun)),
        evaluations=evaluations, seconds=time.perf_counter() - start_time, starts=log,
    )
