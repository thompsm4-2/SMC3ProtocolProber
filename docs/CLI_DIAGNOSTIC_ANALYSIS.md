# CLI Diagnostic Output Analysis

## Purpose

Provide a consistent method for analyzing the CLI summary produced by `smc3_readback_diagnostic.py`.

Analyze the CLI output independently of the generated CSV files. Do not require CSV inspection unless explicitly requested.

## Analysis Guidelines

### 1. Extract the reported metrics

Identify these values from the CLI output:

- Diagnostic mode (PASSIVE or ACTIVE)
- Test duration
- Configured polling rate
- Poll interval
- Total requests
- Successful responses
- Timeouts
- Malformed responses
- Errors
- Output directory

### 2. Evaluate communication reliability

Interpret the counters:

- **Successful responses:** Requests that received valid responses according to the diagnostic.
- **Timeouts:** Requests that did not receive a response within the allowed time.
- **Malformed responses:** Responses that failed the diagnostic's response validation.
- **Errors:** Reported communication or diagnostic errors.

Report the success rate when the necessary counts are available:

`success rate = successful responses / total requests × 100`

Do not assume that a successful response proves the reported motor position is physically accurate.

### 3. Evaluate polling performance

Calculate the nominal expected poll count:

`expected polls = duration × polling rate`

Compare the actual request count with this estimate.

Account for startup, shutdown, and scheduling overhead. A small difference is not automatically a failure.

Do not claim precise timing accuracy unless the output provides sufficient timing measurements.

Do not attribute a polling shortfall to startup/shutdown overhead, sleep intervals, or scheduling behavior unless the implementation or timing measurements support that explanation. Otherwise, describe the cause as possible but unverified.

### 4. Interpret the diagnostic mode

**PASSIVE mode:**
- Evaluates communication and readback behavior.
- Does not intentionally command motor movement.
- Cannot establish whether motor movement commands work correctly.

**ACTIVE mode:**
- Interpret the results in the context of the specific active test performed.
- Do not generalize beyond the motors, targets, and conditions actually tested.
- Do not recommend further movement tests without considering hardware safety.

### 5. Separate evidence from assumptions

Clearly distinguish:

- What the CLI output directly demonstrates.
- What the results reasonably suggest.
- What remains unverified.
- Successful response counts alone do not establish consistent readback values across individual motors. That requires examining the decoded data.
- Successful response validation establishes that the diagnostic accepted the response framing. It does not independently verify that the assumed protocol matches the installed firmware.

In particular, successful communication does not independently establish:
- Physical motor position accuracy.
- Motor calibration.
- Mechanical alignment.
- Correct motor direction or inversion.
- Accuracy of the assumed firmware protocol.
- Successful motor movement.

Do not claim that hardware behavior has been verified when only communication was tested.

## Example Analysis

### Input summary

- Mode: PASSIVE
- Duration: 30 seconds
- Polling rate: 4 Hz
- Poll interval: 0.250 seconds
- Requests: 117
- Successful responses: 117
- Timeouts: 0
- Malformed responses: 0
- Errors: 0

### Expected polling count

30 × 4 = 120 expected polls.

117 requests were completed, approximately 97.5% of the nominal expected count.

### Interpretation

- All 117 requests received successful responses.
- No timeouts, malformed responses, or errors were reported.
- The completed request count was close to the nominal polling expectation.
- The diagnostic completed its 30-second passive test without reported communication failures.

### Conclusion

The results demonstrate stable serial communication and successful readback responses during this passive test.

They do not establish physical motor position accuracy, calibration, or successful motor movement. Those require separate evidence.

## Response Format

Keep the analysis concise and use this structure:

1. **Test overview:** Mode, duration, polling rate.
2. **Communication results:** Request counts, success rate, failures.
3. **Polling performance:** Expected versus actual requests.
4. **Interpretation:** What the results demonstrate.
5. **Limitations:** What remains unverified.
6. **Overall conclusion:** One short paragraph.

Do not inspect or analyze generated CSV files unless explicitly requested.

Do not modify source code, tests, configuration, or diagnostic output files when asked only to analyze CLI output.
