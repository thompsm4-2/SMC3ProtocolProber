# **H3 controller configuration**

| Setting            | Motor A | Motor B | Motor C |
| ------------------ | ------- | ------- | ------- |
| PWM offset         | 0       | 0       | 0       |
| PWM maximum        | 180     | 180     | 180     |
| Feedback dead zone | 0       | 0       | 0       |
| Reverse PWM duty   | 200     | 200     | 200     |
| Kp                 | 1.20    | 1.20    | 1.20    |
| Ki                 | 0.01    | 0.01    | 0.01    |
| Kd                 | 0.04    | 0.04    | 0.04    |

*PID values use the firmware's ×100 scaling.*

## **What this tells us**

1. All three motors have identical controller settings.
2. The controller responds correctly to all 15 configuration queries.
3. Configuration readback works without enabling the motors.
4. The PWM maximum is configured to 180, not 255.
5. There are no configured feedback dead zones.


I reviewed all three CSV files. This is a useful result: **all three motors physically responded to the ±100 commands, and their feedback readings show a consistent directional pattern.**

## **1. Direction of feedback response**

The feedback values below use the script's tentative ×4 conversion.

| Motor | Command 612 (+100) | Feedback change | Command 412 (-100) | Feedback change |
| ----- | ------------------ | --------------- | ------------------ | --------------- |
| A     | 612                | 504 → 448 (−56) | 412                | 500 → 584 (+84) |
| B     | 612                | 520 → 600 (+80) | 412                | 536 → 456 (−80) |
| C     | 612                | 500 → 452 (−48) | 412                | 500 → 568 (+68) |

**A and C behave alike. B behaves in the opposite direction.**

This is strong evidence that B has the opposite feedback direction relative to A and C. Given the earlier observation that either A or B was inverted, B is now the likely motor in question. I would still distinguish this from a definitive wiring diagnosis until we correlate encoder direction with the physical actuator movement.

## **2. Does feedback return to center?**

This is particularly interesting. The target readback returns to 512 in every return phase, but the feedback does not always return to its original position.

| Motor | Initial feedback | After +100 return | After -100 return |
| ----- | ---------------- | ----------------- | ----------------- |
| A     | 504              | 500               | 528               |
| B     | 520              | 536               | 516               |
| C     | 500              | 500               | 524               |

These are the final five-sample averages, not averages over the entire return movement.

Observations:

- A returns almost exactly after the positive excursion, but finishes 24 counts above baseline after the negative excursion.
- B finishes 16 counts above baseline after the positive excursion and 4 counts below after the negative excursion.
- C returns exactly after the positive excursion but finishes 24 counts above baseline after the negative excursion.

The readings are stable over the last five samples, so this isn't simply a transient in the final sample.

## **3. Data quality**

All feedback frames valid

- 100 feedback samples per motor.
- 20 samples per phase.
- No invalid feedback frames.
- No reported CSV errors.
- All three motors showed feedback changes during both excursions.

One important distinction: the target readback and feedback readback are separate measurements. A target of 512 does not prove the actuator physically returned to its original position.

## **4. What I think we have established**

1. The controller accepts meaningful position commands.
2. The feedback readings respond to those commands.
3. Motor B's feedback direction is opposite to A and C.
4. Returning the target to 512 does not always restore the original feedback position.
5. The negative-excursion return is consistently worse for A and C than the positive-excursion return.
