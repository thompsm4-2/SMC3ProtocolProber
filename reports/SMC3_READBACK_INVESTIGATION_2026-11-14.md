# DOF Reality H3 — SMC3 Readback Investigation

**Session summary: November 14, 2026**

## Executive summary

This investigation established that the DOF Reality H3 responds to the tested SMC3 position and configuration readback commands for motors A, B, and C.

Bidirectional staircase tests revealed direction-dependent feedback on all three motors. A and C feedback decrease as commanded position increases; B feedback increases. The largest observed difference between ascending and descending measurements was 32 counts on C.

A separate yaw test demonstrated that sending C a command of 512 can cause physical movement when its existing controller target is 492. This explains a plausible cause of the unexpected yaw movement during an earlier staircase test, although the exact initial state of that earlier run was not recorded.

The results provide a basis for further calibration, but do not yet establish physical center, mechanical backlash, or the cause of the direction-dependent behavior.

## 1. Protocol and measurement terminology

### Controller and connection

- Controller: SMC3 v23.07, as reported by the Windows SMC3 Utility.
- Serial connection: `/dev/ttyACM0`, 500000 baud.
- Motors: A = 1, B = 2, C = 3.
- Conventional center command: 512.
- Position readback commands: `[rdA]`, `[rdB]`, `[rdC]`.

### Position terminology

| Term | Meaning |
|---|---|
| **Commanded position** | Position value sent to the controller, on the 0–1023 scale. |
| **Controller target** | Target setpoint reported by the controller. |
| **Feedback** | Position measurement reported by the controller. |
| **Raw target / raw feedback** | Target or feedback byte received in the readback response, before conversion. |
| **Target ×4 candidate / feedback ×4 candidate** | Corresponding raw byte multiplied by four. |

The reference SMC3 firmware divides target and feedback values by four before transmitting them. Multiplying the received bytes by four reconstructs candidate values on the 0–1023 scale.

For example:

| Value | Before C=512 | After C=512 |
|---|---:|---:|
| Command sent | — | 512 |
| Raw target | 123 | 128 |
| Target ×4 candidate | 492 | 512 |

The command is sent as 512; it is not divided by four. The values 123 and 128 are the raw readback bytes. The values 492 and 512 are reconstructed target candidates.

This scaling is consistent with the reference firmware, but the exact H3 firmware implementation and physical units have not been independently verified.

**Important:** Commanded position, controller target, and feedback are distinct values. A target is a setpoint, not a measured position. The conventional command of 512 is not a verified physical center, and a feedback ×4 candidate of 512 does not prove that the platform is physically centered.

### Motor command terminology

- **Initialization command:** A position command sent before the measurement sequence.
- **No further position commands:** No additional position commands are sent to that motor during the specified phase; its last controller target remains in effect unless changed by another operation.
- **Not commanded during the test:** No position command is sent to that motor at any point during the test.
- **Restoration command:** A position command sent after the measurement sequence to set the controller target to the script's configured return value.

These terms describe commands and controller targets, not guaranteed physical movement. Avoid saying a motor is "held" or "stationary" unless physical measurements establish that.

## 2. Controller configuration readback

The controller returned the following configuration for all three motors:

| Setting | Motor A | Motor B | Motor C |
|---|---:|---:|---:|
| PWM offset | 0 | 0 | 0 |
| PWM maximum | 180 | 180 | 180 |
| Feedback dead zone | 0 | 0 | 0 |
| Reverse PWM duty | 200 | 200 | 200 |
| Kp | 1.20 | 1.20 | 1.20 |
| Ki | 0.01 | 0.01 | 0.01 |
| Kd | 0.04 | 0.04 | 0.04 |

*PID values use the firmware's ×100 scaling.*

### Findings

- All three motors report identical configuration values.
- All 15 tested configuration queries returned valid responses.
- Configuration readback worked without enabling the motors.
- The configured PWM maximum is 180, not 255.
- The reported feedback dead zone is zero for all three motors.

These findings apply to the tested configuration queries, not every possible SMC3 configuration command or field.

## 3. Motor A: bidirectional staircase

- Commanded-position range: **537–587**, step 5.
- Settling time: 5 seconds.
- Samples per position: 10.
- Initialization: all three motors were commanded to 512.
- Sweep: only A received additional position commands.
- During the sweep, B and C received no further position commands.

The ascending sweep included both endpoints. The descending sweep began at 582, avoiding a repeated measurement at the upper endpoint.

| Commanded position | Ascending feedback ×4 candidate | Descending feedback ×4 candidate |
|---:|---:|---:|
| 537 | 496 | 480 |
| 542 | 496 | 476 |
| 547 | 496 | 472 |
| 552 | 496 | 468 |
| 557 | 496 | 468 |
| 562 | 488 | 468 |
| 567 | 488 | 468 |
| 572 | 480 | 468 |
| 577 | 476 | 468 |
| 582 | 472 | 468 |
| 587 | 468 | — |

### Findings

- Feedback decreases as commanded position increases.
- Feedback depends on the direction of approach.
- The maximum ascending/descending difference at shared commanded positions was 28 counts.
- Feedback was generally stable within each sampling period.

## 4. Motor B: bidirectional staircase

- Commanded-position range: **537–582**, step 5.
- Settling time: 5 seconds.
- Samples per position: 10.
- Initialization: all three motors were commanded to 512.
- Sweep: only B received additional position commands.
- During the sweep, A and C received no further position commands.

The ascending sweep included both endpoints. The descending sweep began at 577.

| Commanded position | Ascending feedback ×4 candidate | Descending feedback ×4 candidate |
|---:|---:|---:|
| 537 | 536 | 556 |
| 542 | 540 | 560 |
| 547 | 544 | 564 |
| 552 | 548 | 568 |
| 557 | 552 | 568 |
| 562 | 556 | 576 |
| 567 | 560 | 576 |
| 572 | 568 | 576 |
| 577 | 568 | 576 |
| 582 | 572 | — |

### Findings

- Feedback increases as commanded position increases, opposite to A and C.
- Feedback is direction-dependent.
- The maximum ascending/descending difference at shared commanded positions was 20 counts.
- This agrees with earlier observations that B's feedback direction is opposite to A and C.

## 5. Motor C: yaw staircase

- Commanded-position range: **537–587**, step 5.
- Settling time: 5 seconds.
- Samples per position: 10.
- Initialization: all three motors were commanded to 512.
- Sweep: only C received additional position commands.
- During the sweep, A and B received no further position commands.

The ascending sweep included both endpoints. The descending sweep began at 582.

| Commanded position | Ascending feedback ×4 candidate | Descending feedback ×4 candidate |
|---:|---:|---:|
| 537 | 508 | 480 |
| 542 | 504 | 476 |
| 547 | 504 | 472 |
| 552 | 496 | 472 |
| 557 | 492 | 472 |
| 562 | 492 | 472 |
| 567 | 488 | 472 |
| 572 | 484 | 472 |
| 577 | 480 | 472 |
| 582 | 472 | 472 |
| 587 | 472 | — |

### Findings

- Feedback decreases as commanded position increases, like A.
- The maximum ascending/descending difference at shared commanded positions was 32 counts.
- Descending feedback remained at 472 over much of the return sweep.
- This is the largest direction-dependent difference observed in the three staircase tests.

C is the yaw axis and should be characterized separately from the pitch/roll motors.

## 6. Yaw startup investigation

We created and ran `smc3_yaw_startup_center_test.py` to investigate unexpected yaw movement during an earlier staircase test.

The diagnostic:
1. Read existing feedback and targets.
2. Enabled the motors.
3. Read the values again.
4. Sent a position command of 512 only to C.
5. Read the values again.

It did not send initialization position commands to A or B.

| Stage | Motor | Command sent during stage | Raw target | Target ×4 candidate | Feedback ×4 candidate |
|---|---|---:|---:|---:|---:|
| Before enable | A | — | 128 | 512 | 500 |
| Before enable | B | — | 128 | 512 | 536 |
| Before enable | C | — | 123 | 492 | 480 |
| After enable | A | — | 128 | 512 | 500 |
| After enable | B | — | 128 | 512 | 536 |
| After enable | C | — | 123 | 492 | 480 |
| After C=512 | A | — | 128 | 512 | 500 |
| After C=512 | B | — | 128 | 512 | 536 |
| After C=512 | C | 512 | 128 | 512 | 496 |

All ten samples in each stage were identical.

### Findings

- Before enable, A and B had target ×4 candidates of 512; C had a target ×4 candidate of 492.
- Enabling the motors did not change the readings.
- Sending C=512 changed its raw target from 123 to 128, corresponding to a target ×4 candidate change from 492 to 512.
- C's feedback ×4 candidate changed from 480 to 496.
- Physical platform movement was observed when C=512 was sent.

The earlier staircase script initialized all three motors by sending position commands of 512. If C's target was still 492 at that time, its initialization command would have changed the target and could have caused the observed yaw movement.

This is a strongly supported explanation, but the exact controller state immediately before the earlier staircase run was not captured. Therefore, the cause of that earlier movement is not directly verified.

**Operational implication:** Do not assume that commanding 512 is a harmless initialization operation. It can cause physical movement when the existing controller target differs from 512.

## 7. Historical yaw measurements

The following measurements are from earlier tests, not today's staircase runs:

- Approximately 50 command counts produced 10 mm of measured yaw displacement.
- A ±400-count excursion produced approximately ±80 mm, close to the SRS ±82 mm range.
- One reversal produced approximately 3.25 mm of movement where a normal move produced approximately 10 mm.
- Earlier yaw measurements showed run-to-run differences.

These observations reinforce the need to characterize yaw separately.

## 8. SMC3 protocol and H3 compatibility

There is strong experimental evidence that the H3 supports the tested SMC3 readback interface for motors A, B, and C.

### Reference protocol

The reference SMC3 firmware defines the position readback response as a five-byte frame:

`[START_BYTE, motor_ID, feedback, target, END_BYTE]`

For `[rdA]`, `[rdB]`, and `[rdC]`, the reference firmware returns the corresponding motor's feedback and target values, divided by four before transmission.

### Evidence from the H3

- All three read commands returned five-byte responses.
- Each response contained the correct motor identifier.
- Start and end framing bytes were valid.
- Feedback and target fields changed in response to position commands.
- All three motors could be read repeatedly, including before and after motor enable.
- All 15 tested configuration queries returned valid responses.

The observed response structure and value encoding are consistent with the reference SMC3 implementation.

### Compatibility boundaries

| Claim | Status |
|---|---|
| H3 accepts `[rdA]`, `[rdB]`, `[rdC]` | Demonstrated |
| H3 returns the expected five-byte response structure | Demonstrated |
| Response identifies the requested motor | Demonstrated |
| Response contains feedback and target fields | Demonstrated |
| Feedback and target encoding matches the reference divide-by-four behavior | Consistent with measurements and reference source |
| All 15 tested configuration queries return valid responses | Demonstrated |
| Configuration readback works without motor enable | Demonstrated |
| H3 runs the exact reference SMC3 firmware source/version | Not established |
| Every SMC3 readback command and configuration field is supported | Not tested |

### Recommended project documentation statement

**SMC3 readback compatibility experimentally confirmed:** The DOF Reality H3 controller responds to the SMC3 `[rdA]`, `[rdB]`, and `[rdC]` commands using the expected five-byte response structure, including motor identifier, feedback value, and target value. The observed response format and value encoding are consistent with the reference SMC3 firmware implementation. Configuration readback has also been demonstrated for all 15 tested configuration queries across motors A, B, and C, including while the motors are disabled. Exact firmware provenance and full protocol compatibility have not been independently established.

## 9. Overall conclusions

1. A and C feedback decrease as commanded position increases; B feedback increases.
2. All three motors exhibit direction-dependent feedback at shared commanded positions.
3. The largest observed ascending/descending difference was 32 counts on C, compared with 28 on A and 20 on B.
4. Yaw exhibits distinct behavior and requires separate characterization.
5. Commanding C=512 caused physical movement when its existing target was 492. This is a plausible explanation for the earlier staircase startup movement, but that earlier initial state was not recorded.
6. Feedback and controller targets should be recorded before any position commands are sent.
7. The H3 supports the tested SMC3 position and configuration readback operations.
8. Identical controller configuration values do not imply identical motor behavior.
9. The staircase scripts initialized all three motors to 512, swept one selected motor, and then sent restoration commands. The other motors received no further position commands during the sweep, but their physical positions were not independently verified.

The tests have not established whether direction-dependent behavior is caused by mechanical backlash, friction, controller behavior, or a combination. They also have not established a reliable physical center from feedback values alone.

## 10. Diagnostic files

| File | Purpose |
|---|---|
| `smc3_bidirectional_staircase.py` | Generic A/B/C staircase diagnostic |
| `smc3_motor_A_bidirectional_staircase_537_to_587.csv` | Motor A results |
| `smc3_motor_B_bidirectional_staircase_537_to_582.csv` | Motor B results |
| `smc3_motor_C_bidirectional_staircase_537_to_587.csv` | Motor C results |
| `smc3_yaw_startup_center_test.py` | Isolates startup and C=512 behavior |
| `smc3_yaw_startup_center_test.csv` | Startup diagnostic measurements |

## 11. Recommended next steps

- Remove automatic commands to 512 from diagnostic startup.
- Record existing feedback and controller targets before sending position commands.
- Test one motor at a time.
- Do not send position commands to non-tested motors when they are intended to receive no commands.
- Record initialization, measurement-sequence, and restoration commands separately.
- Treat yaw as a separate calibration problem.
- Record physical position alongside encoder feedback.
- Make centering and restoration commands explicit rather than automatic.
- Preserve raw feedback and target bytes alongside their ×4 candidate values.

**The key result:** We experimentally confirmed the tested SMC3 readback behavior on the H3 and demonstrated that a C=512 command can cause physical movement when the existing target is 492. The staircase results also establish direction-dependent feedback on all three motors. These findings provide a stronger foundation for the next calibration phase.
