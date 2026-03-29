from audio_spectrum.constants import TARGET_FREQUENCIES_HZ


def test_frequency_range_complete() -> None:
    assert TARGET_FREQUENCIES_HZ[0] == 500
    assert TARGET_FREQUENCIES_HZ[-1] == 20000
    assert len(TARGET_FREQUENCIES_HZ) == 40
