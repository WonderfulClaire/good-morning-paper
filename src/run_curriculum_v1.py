from __future__ import annotations

import runpy
import sys
from dataclasses import dataclass

import torch


@dataclass
class CurriculumConfig:
    """
    Curriculum learning configuration for VMAS/navigation.

    This runner keeps MAPPO and the original VMAS reward unchanged.
    It only changes the reset process during training:

    - Easy phase: goals are moved closer to agents.
    - Medium phase: goals are moved to a medium distance.
    - Hard phase: original VMAS/navigation reset is used.

    In testing/evaluation, use the original hard environment for fair comparison.
    """
    total_resets: int = 600
    easy_ratio: float = 0.30
    medium_ratio: float = 0.70
    easy_alpha: float = 0.35
    medium_alpha: float = 0.65
    verbose: bool = True


def _pop_arg(argv, name, default, cast):
    """
    Parse and remove a custom curriculum argument before forwarding argv to BenchMARL.

    Supported formats:
        --cl-total-resets=600
        --cl-total-resets 600
    """
    prefix = f"--{name}="
    flag = f"--{name}"

    kept = [argv[0]]
    value = default
    skip = False

    for i, item in enumerate(argv[1:], start=1):
        if skip:
            skip = False
            continue

        if item.startswith(prefix):
            value = cast(item[len(prefix):])
            continue

        if item == flag:
            if i + 1 >= len(argv):
                raise ValueError(f"Missing value for {flag}")
            value = cast(argv[i + 1])
            skip = True
            continue

        kept.append(item)

    argv[:] = kept
    return value


def parse_curriculum_args(argv):
    cfg = CurriculumConfig()

    cfg.total_resets = _pop_arg(argv, "cl-total-resets", cfg.total_resets, int)
    cfg.easy_ratio = _pop_arg(argv, "cl-easy-ratio", cfg.easy_ratio, float)
    cfg.medium_ratio = _pop_arg(argv, "cl-medium-ratio", cfg.medium_ratio, float)
    cfg.easy_alpha = _pop_arg(argv, "cl-easy-alpha", cfg.easy_alpha, float)
    cfg.medium_alpha = _pop_arg(argv, "cl-medium-alpha", cfg.medium_alpha, float)
    cfg.verbose = _pop_arg(
        argv,
        "cl-verbose",
        int(cfg.verbose),
        lambda x: int(x) != 0,
    )

    if cfg.total_resets <= 0:
        raise ValueError("--cl-total-resets must be positive")
    if not (0.0 < cfg.easy_ratio < cfg.medium_ratio < 1.0):
        raise ValueError("Require 0 < easy_ratio < medium_ratio < 1")
    if not (0.0 < cfg.easy_alpha <= cfg.medium_alpha <= 1.0):
        raise ValueError("Require 0 < easy_alpha <= medium_alpha <= 1")

    return cfg


def apply_curriculum_patch(cfg: CurriculumConfig):
    """
    Runtime monkey patch for VMAS/navigation.

    This does not edit files under site-packages. It only replaces
    navigation.Scenario.reset_world_at inside the current Python process.
    """
    import vmas.scenarios.navigation as navigation

    Scenario = navigation.Scenario
    original_reset = Scenario.reset_world_at

    def get_phase(self):
        if not hasattr(self, "_cl_reset_count"):
            self._cl_reset_count = 0
            self._cl_last_phase = None

        progress = min(
            float(self._cl_reset_count) / float(max(cfg.total_resets, 1)),
            1.0,
        )

        if progress < cfg.easy_ratio:
            return "easy", cfg.easy_alpha, progress
        if progress < cfg.medium_ratio:
            return "medium", cfg.medium_alpha, progress
        return "hard", 1.0, progress

    def update_pos_shaping(self, agent, env_index=None):
        """
        VMAS/navigation stores previous distance in agent.pos_shaping.
        After moving the goal in Easy/Medium phases, this must be refreshed;
        otherwise the first shaped reward after reset can be inconsistent.
        """
        if not hasattr(agent, "pos_shaping") or not hasattr(agent, "goal"):
            return

        if env_index is None:
            agent.pos_shaping = (
                torch.linalg.vector_norm(
                    agent.state.pos - agent.goal.state.pos,
                    dim=1,
                )
                * self.pos_shaping_factor
            )
        else:
            agent.pos_shaping[env_index] = (
                torch.linalg.vector_norm(
                    agent.state.pos[env_index] - agent.goal.state.pos[env_index]
                )
                * self.pos_shaping_factor
            )

    def curriculum_reset(self, env_index=None):
        # First use original VMAS/navigation reset to preserve all native logic.
        out = original_reset(self, env_index)

        if not hasattr(self, "_cl_reset_count"):
            self._cl_reset_count = 0
            self._cl_last_phase = None

        self._cl_reset_count += 1
        phase, alpha, progress = get_phase(self)

        if cfg.verbose and phase != getattr(self, "_cl_last_phase", None):
            print(
                f"[curriculum_v1] phase={phase}, alpha={alpha:.3f}, "
                f"reset={self._cl_reset_count}/{cfg.total_resets}, "
                f"progress={progress:.3f}"
            )
            self._cl_last_phase = phase

        # Hard phase is exactly original VMAS/navigation.
        if phase == "hard":
            return out

        # Easy/Medium phases: keep original direction but shorten target distance.
        # alpha=0.35 means the goal is placed at 35% of the original distance.
        for agent in self.world.agents:
            if not hasattr(agent, "goal"):
                continue

            if env_index is None:
                agent_pos = agent.state.pos
                goal_pos = agent.goal.state.pos
                new_goal_pos = agent_pos + alpha * (goal_pos - agent_pos)
                agent.goal.set_pos(new_goal_pos, batch_index=env_index)
            else:
                agent_pos = agent.state.pos[env_index]
                goal_pos = agent.goal.state.pos[env_index]
                new_goal_pos = agent_pos + alpha * (goal_pos - agent_pos)
                agent.goal.set_pos(new_goal_pos, batch_index=env_index)

            update_pos_shaping(self, agent, env_index)

        return out

    Scenario.reset_world_at = curriculum_reset

    print(
        "[curriculum_v1] runtime patch applied: "
        f"total_resets={cfg.total_resets}, "
        f"easy_ratio={cfg.easy_ratio}, "
        f"medium_ratio={cfg.medium_ratio}, "
        f"easy_alpha={cfg.easy_alpha}, "
        f"medium_alpha={cfg.medium_alpha}"
    )


def main():
    cfg = parse_curriculum_args(sys.argv)
    apply_curriculum_patch(cfg)

    # Forward remaining arguments to BenchMARL.
    sys.argv = ["benchmarl.run"] + sys.argv[1:]
    runpy.run_module("benchmarl.run", run_name="__main__")


if __name__ == "__main__":
    main()
