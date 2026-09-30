from enum import Enum, auto
import random
import numpy as np
from numpy.typing import NDArray
from scipy.stats import qmc
from typing import Callable
from tqdm import trange
import matplotlib.pyplot as plt

class HyperParams(Enum):
    SEED = auto()
    N_POPULATION = auto()
    MAX_GEN = auto()
    INPUT_DIMENSIONS = auto()
    INPUT_BOUNDS = auto()

class SamplingStrategy(Enum):
    LHS = auto()
    GRID = auto()

class NSGA:
    def __init__(
        self,
        hyper_params: dict[HyperParams, float],
        solver: Callable[[NDArray], NDArray],
        objective_functions: list[tuple[Callable[[NDArray], NDArray], bool]],
        sampling_strategy: SamplingStrategy = SamplingStrategy.LHS
    ):
        random.seed(hyper_params[HyperParams.SEED])
        self.hyper_params = hyper_params
        self.solver = solver
        self.objective_functions = objective_functions
        self.population: NDArray = self.initialize_population(sampling_strategy)
        self.progress: list = []

    def initialize_population(self, sampling_strategy: SamplingStrategy) -> NDArray:
        bounds = self.hyper_params[HyperParams.INPUT_BOUNDS]
        n_pop = self.hyper_params[HyperParams.N_POPULATION]
        d = self.hyper_params[HyperParams.INPUT_DIMENSIONS]

        match sampling_strategy:
            case SamplingStrategy.LHS:
                sampler = qmc.LatinHypercube(d=d)
                unscaled_population = sampler.random(n=n_pop)
                return np.array([
                    [low + (high - low) * val for val, (low, high) in zip(ind, bounds)]
                    for ind in unscaled_population
                ])

            case SamplingStrategy.GRID:
                points_per_dim = int(round(n_pop ** (1 / d)))
                grids = [np.linspace(low, high, points_per_dim) for (low, high) in bounds]
                mesh = np.meshgrid(*grids, indexing='ij')
                return np.stack(mesh, axis=-1).reshape(-1, len(bounds))

        raise NotImplementedError

    def fast_non_dominated_sort(self, values, objectives_directions):
        objectives_directions = [("max" if d else "min") for d in objectives_directions]
        population_size = len(values[0])
        num_objectives = len(values)

        S = [[] for _ in range(population_size)]
        front = [[]]
        n = [0 for _ in range(population_size)]
        rank = [0 for _ in range(population_size)]

        for p in range(population_size):
            S[p] = []
            n[p] = 0
            for q in range(population_size):
                if p == q:
                    continue
                p_better = q_better = 0
                for k in range(num_objectives):
                    vp, vq = values[k][p], values[k][q]
                    if objectives_directions[k] == "max":
                        if vp > vq: p_better += 1
                        elif vp < vq: q_better += 1
                    else:
                        if vp < vq: p_better += 1
                        elif vp > vq: q_better += 1
                if p_better > 0 and q_better == 0:
                    S[p].append(q)
                elif q_better > 0 and p_better == 0:
                    n[p] += 1
            if n[p] == 0:
                rank[p] = 0
                front[0].append(p)

        i = 0
        while front[i]:
            Q = []
            for p in front[i]:
                for q in S[p]:
                    n[q] -= 1
                    if n[q] == 0:
                        rank[q] = i + 1
                        Q.append(q)
            i += 1
            front.append(Q)

        del front[-1]
        return front

    def crowding_distance(self, values, front):
        num_objectives = len(values)
        distance = [0.0 for _ in front]
        front_indices = list(range(len(front)))

        for m in range(num_objectives):
            obj_values = values[m]
            sorted_indices = sorted(front_indices, key=lambda i: obj_values[front[i]])
            min_value = min(obj_values[i] for i in front)
            max_value = max(obj_values[i] for i in front)
            range_val = max_value - min_value if max_value != min_value else 1e-9

            distance[sorted_indices[0]] = float("inf")
            distance[sorted_indices[-1]] = float("inf")

            for i in range(1, len(front) - 1):
                prev_val = obj_values[front[sorted_indices[i - 1]]]
                next_val = obj_values[front[sorted_indices[i + 1]]]
                distance[sorted_indices[i]] += (next_val - prev_val) / range_val

        return distance

    def crossover(self, parent1, parent2, bounds, alpha=0.5):
        child = np.empty_like(parent1)
        for i in range(len(parent1)):
            c_min = min(parent1[i], parent2[i])
            c_max = max(parent1[i], parent2[i])
            diff = c_max - c_min
            low = c_min - alpha * diff
            high = c_max + alpha * diff
            child[i] = np.clip(random.uniform(low, high), bounds[i][0], bounds[i][1])
        return child

    def mutate(self, individual, bounds, mutation_rate=0.2, scale=0.1):
        for i in range(len(individual)):
            if random.random() < mutation_rate:
                low, high = bounds[i]
                mutation = np.random.normal(0, scale * (high - low))
                individual[i] = np.clip(individual[i] + mutation, low, high)
        return individual

    def sort_by_values(self, list1, values):
        return sorted(list1, key=lambda x: values[x])

    def run(self):
        n_pop = self.hyper_params[HyperParams.N_POPULATION]
        max_gen = self.hyper_params[HyperParams.MAX_GEN]
        bounds = self.hyper_params[HyperParams.INPUT_BOUNDS]

        scaled_pop = self.population
        self.progress.clear()

        for curr_gen in trange(max_gen, desc="Evolution Progress"):
            solver_outputs = self.solver(scaled_pop)

            objective_scores = [func(solver_outputs) for func, _ in self.objective_functions]
            directions = [maximize for _, maximize in self.objective_functions]

            self.progress.append({
                "generation": curr_gen,
                "population": scaled_pop.copy(),
                "scores": objective_scores
            })

            fronts = self.fast_non_dominated_sort(objective_scores, directions)

            offspring = []
            while len(offspring) < 2 * n_pop:
                a, b = random.sample(range(n_pop), 2)
                child = self.crossover(scaled_pop[a], scaled_pop[b], bounds)
                child = self.mutate(child, bounds)
                offspring.append(child)
            offspring = np.array(offspring)

            offspring_outputs = self.solver(offspring)
            offspring_scores = [func(offspring_outputs) for func, _ in self.objective_functions]

            fronts = self.fast_non_dominated_sort(offspring_scores, directions)
            crowding = [self.crowding_distance(offspring_scores, front) for front in fronts]

            new_population_indices = []
            for i, front in enumerate(fronts):
                if len(new_population_indices) >= n_pop:
                    break
                sorted_front = self.sort_by_values(list(range(len(front))), crowding[i])
                sorted_front = [front[j] for j in sorted_front[::-1]]
                for idx in sorted_front:
                    if len(new_population_indices) < n_pop:
                        new_population_indices.append(idx)
                    else:
                        break

            scaled_pop = np.array([offspring[i] for i in new_population_indices])

        self.population = scaled_pop
        return self.progress

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    import matplotlib as mpl
    import numpy as np

    def obj1(outputs: np.ndarray) -> np.ndarray:
        return outputs ** 2

    def obj2(outputs: np.ndarray) -> np.ndarray:
        return (outputs - 2) ** 2

    hyper_params = {
        HyperParams.SEED: 42,
        HyperParams.N_POPULATION: 100,
        HyperParams.MAX_GEN: 100,
        HyperParams.INPUT_DIMENSIONS: 1,
        HyperParams.INPUT_BOUNDS: [(-55, 55)]
    }

    nsga = NSGA(
        hyper_params=hyper_params,
        solver=lambda x: x,
        objective_functions=[(obj1, False), (obj2, False)],
        sampling_strategy=SamplingStrategy.LHS
    )

    progress = nsga.run()

    num_generations = len(progress)
    colors = plt.cm.viridis(np.linspace(0, 1, 100))
    norm = mpl.colors.Normalize(vmin=0, vmax=num_generations - 1)
    cmap = mpl.cm.ScalarMappable(norm=norm, cmap='viridis')

    fig, ax = plt.subplots(figsize=(8, 6))

    for gen_idx, gen_data in enumerate(progress):
        scores = gen_data["scores"]
        f1_vals, f2_vals = scores[0], scores[1]
        ax.scatter(f1_vals, f2_vals, color=colors[gen_idx], label=f"Gen {gen_idx}", alpha=0.6, s=20)

    sm = mpl.cm.ScalarMappable(cmap='viridis', norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax)
    cbar.set_label("Generation")

    ax.set_xlabel("Objective 1 (minimize)")
    ax.set_ylabel("Objective 2 (minimize)")
    ax.set_title("NSGA-II Pareto Front Evolution Across Generations")
    ax.grid(True)

    plt.tight_layout()
    plt.show()