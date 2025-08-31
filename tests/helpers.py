
expected_info_keys_and_types = {
    'likelihood': float,
    'am_score': float,
    'lm_score': float,
    'confidence': float,
    'expected_error_rate': float,
}

def assert_info_shape(info):
    assert isinstance(info, dict)
    for key, expected_type in expected_info_keys_and_types.items():
        assert key in info, f"Missing key: {key}"
        assert isinstance(info[key], expected_type), f"Incorrect type for {key}: expected {expected_type}, got {type(info[key])}"
