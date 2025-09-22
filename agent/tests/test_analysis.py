from multi_inst_agent.core.analysis import (
    ImuStatistics,
    LoopStatistics,
    evaluate,
)


def test_evaluate_passes_within_thresholds():
    loop = LoopStatistics(100, 250.0, 5.0, 240.0, 260.0, 255.0, 256.0, 4000.0)
    imu = ImuStatistics(100, [2.0, 2.0, 2.0], [1.0, 1.0, 1.0], 1.5)
    analytics = evaluate(
        "usb_stand",
        loop,
        imu,
        i2c_error_rate=0.0,
        analog={"vbat_V": 5.0, "amps_A": 0.2},
        attitude={"roll_deg": 2.0, "pitch_deg": 3.0},
    )
    assert analytics.ok
    assert analytics.reasons == []


def test_evaluate_flags_excessive_values():
    loop = LoopStatistics(100, 250.0, 30.0, 240.0, 260.0, 255.0, 256.0, 4000.0)
    imu = ImuStatistics(100, [7.0, 2.0, 2.0], [13.0, 0.0, 0.0], 7.0)
    analytics = evaluate(
        "field_strict",
        loop,
        imu,
        i2c_error_rate=1.0,
        analog={"vbat_V": 3.5, "amps_A": 0.6},
        attitude={"roll_deg": 20.0, "pitch_deg": 5.0},
    )
    assert not analytics.ok
    assert any(reason.startswith("loop_jitter") for reason in analytics.reasons)
    assert any(reason.startswith("gyro_std_x") for reason in analytics.reasons)
    assert any(reason.startswith("gyro_bias_x") for reason in analytics.reasons)
    assert any(reason.startswith("acc_norm_std") for reason in analytics.reasons)
    assert any(reason.startswith("i2c_err") for reason in analytics.reasons)
    assert any(reason.startswith("vbat_low") for reason in analytics.reasons)
    assert any(reason.startswith("amps_high") for reason in analytics.reasons)
    assert any(reason.startswith("tilt") for reason in analytics.reasons)
