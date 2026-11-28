# PF scenarios for the first semantic compression experiment

Use `scenario-manifest-v1.0.json` and `split-groups-v1.0.csv`. These list scenario inputs and group assignment. The teacher owns the unified sample manifest. V0.1 was the initial handoff, and `refinement-v0.2.json` is discovery-only.

## Loading a scene in the teacher runner

1. Build using `DL_DISCIPLINE=PF TARGET_UE=0 BUILD_GCC_ONLY=1 bash experiments/exp/dual_ue/run.sh "$SIMU5G_ROOT" "$RUNTIME" "$NEW_BUILD"`. The build includes the `052b49c` core-admission actuator and target UE bridge.
2. Set `-f experiments/exp/semantic_scenarios/scenarios.ini -c SemanticScenariosPF -r 0` and `--seed-set=<seed>`. For each entry in the requested row's `ini_overrides`, append one argv element `--<key>=<value>`. List arguments can be passed unchanged through Python subprocess. Attach the existing TCP loop with `--*.routeController.port=<port>`.
3. The verified reference prefix stays at direct / 4 / 3 Mbit/s. Apply one of the eight joint actions at `source_time_ns`, hold for the evaluation window, then restore the initial action. Record actual apply/readback. The 40 ms validity bounds the age of the observation. `local_evaluation_window_ms` is a separate 100 ms diagnostic. If the teacher chooses a different prefix or hold length, generate fresh labels under that protocol.
4. Use the complete `split_group`, including scenario and seed, for all actions and preferences. Run `test` separately after choices are fixed and keep its results out of fitting and threshold selection. Scenario arguments and test labels are distinct artifacts.

## Independent probe

    bash experiments/exp/semantic_scenarios/run.sh "$SIMU5G_ROOT" "$RUNTIME" "$NEW_RESULTS" --split train validation --jobs 8
    bash experiments/exp/semantic_scenarios/run.sh "$SIMU5G_ROOT" "$RUNTIME" "$NEW_TEST_RESULTS" --split test --jobs 8

The probe reports actual endpoint SLA over the 500 ms source cohort, plus a local 100 ms control diagnostic. A valid control negative requires the number of actual late or missing source packets to push the on-time fraction below 99%. The probe records same-prefix evidence from controller transactions, available pre-fork vectors and the fork observation. It checks the entire source trace across actions. It does not freeze the post-fork RNG consumption. MAC and pcap resource costs are measured by event times.

The `discovery` splits are for feasibility-boundary search. The normal and low-priority wired families retain the 200 B / 5 ms control flow. Explicit high-priority wired stress contends in DSCP 46. Radio-stress variants change the control offered load and UE1 competition while using the same PF discipline. Core-only cases vary the N6 capacity schedule, independently of source load and policy rate. Preference terms and their normalization are part of the input manifest. The `test` split has new scenario IDs, seeds, times and settings fixed in v0.1.