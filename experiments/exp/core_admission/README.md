# UPF video admission in the dual-UE ladder

The PF scenario keeps UE0's 20 ms / 99% control SLA and the target-UE MAC observation. Video admission is at UPF N6 ingress for UDP destination 6204. The effective token rate is the minimum of the controller's requested rate and the scenario capacity. The policer accounts for IPv4 and UDP headers. Its 4,120 B bucket permits credit accrued before a positive capacity reduction. Capacity 0 blocks new admissions immediately. Control traffic bypasses this bucket.

## Load the scenario

Run `bash experiments/exp/core_admission/run.sh "$SIMU5G_ROOT" "$RUNTIME" "$NEW_RESULTS"` on A100. The defaults run five paired seeds for 13 fixed configurations, plus one TCP command witness. Set `SEED_COUNT=1` for a small run. The runner uses the existing `dual_ue/run.sh` build entry point with `BUILD_GCC_ONLY=1 TARGET_UE=0 DL_DISCIPLINE=PF`. After sourcing the same environment, any individual configuration can run from that build with `-n "$NEW_RESULTS/ned" -l "$NEW_RESULTS/build/dualue" -f experiments/exp/core_admission/core_admission.ini -c CONFIG -r 0 --seed-set=SEED --result-dir=CASE_DIR`.

All workloads use UE0 source window [100, 1300) ms and drain through 4 s. The background sources and optional normal-time capacity are exposed in the same INI. Times below are in milliseconds and half open.

| Config | Active disturbances | Core capacity | Path / bands |
| --- | --- | --- | --- |
| AdmissionNormal | None | 3 Mbit/s | direct / 4 |
| AdmissionRadio | UE1 [400, 900) | 3 Mbit/s | direct / 4 |
| AdmissionWired | NE1–NE3 [400, 900) | 3 Mbit/s | direct / 4 |
| AdmissionReference | UE1 and NE1–NE3 [400, 900) | 3 Mbit/s | direct / 4 |
| AdmissionCore | Core only | 0.8 Mbit/s [400, 900) | direct / 4 |
| AdmissionRadioCore | UE1 and core | 0.8 Mbit/s [400, 900) | direct / 4 |
| AdmissionWiredCore | NE1–NE3 and core | 0.8 Mbit/s [400, 900) | direct / 4 |
| AdmissionAll | All three | 0.8 Mbit/s [400, 900) | direct / 4 |
| AdmissionAllDetour | All three | 0.8 Mbit/s [400, 900) | detour / 4 |
| AdmissionAllDetourBands | All three | 0.8 Mbit/s [400, 900) | detour / 10 |
| AdmissionStaggered | UE1 and NE1–NE3 [400, 900), core shifted | 0.8 Mbit/s [550, 800) | direct / 4 |
| AdmissionLowOffer | Core, source payload 0.4 Mbit/s | 0.8 Mbit/s [400, 900) | direct / 4 |
| AdmissionPolicyLimited | Requested rate fixed at 0.8 Mbit/s | 3 Mbit/s | direct / 4 |

Capacity outside the specified windows is 3 Mbit/s. The unchanged video source payload rate is 2 Mbit/s except in `AdmissionLowOffer`. `capacitySchedule` accepts strictly increasing `{atMs, bps}` entries. To drive the scenario online, set `*.routeController.requireController=true` and pass the controller's local port in `*.routeController.port`. The `AdmissionCore` witness sends rates at 460, 600 and 940 ms via `core_admission.policy:choose`.

## Observation and action contract

- Existing `apply_route_resources.upf_video_rate_bps` sets a request. Observation and acknowledgement fields `upf_video_rate_bps`, `upf_video_capacity_bps` and `upf_video_enforced_bps` expose request, scenario capacity and effective refill rate respectively. No policy command changes the scenario capacity.
- The augmented bridge also yields cumulative `core.offered_video_packets` and `core.offered_video_bytes` plus admitted and dropped packet/byte counters. Use two counter snapshots and their elapsed time to reconstruct N6 offered IP rate. Counters include the current source load regardless of any admission drops. The existing GCC solver and reporting codecs retain their previous decision models. A capacity-aware solver should explicitly consume the new fields.
- The extractor joins the periodic source stream to N6 by ordered timestamps and actual IP packet size, then checks source, disposition and endpoint counts. `rates.csv` records changes at their exact simulator time. `core.csv` and `flows.csv` use source-time cohorts. `pcap.csv` and `queues.csv` use local event times. Reported capacity represents a modeled sustained resource bound with burst allowance.