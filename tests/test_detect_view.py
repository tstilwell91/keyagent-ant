from pathlib import Path

from antid.data.detect_view import detect_view_type


def test_detect_view_dorsal():
    assert detect_view_type("casent0123456_d_1.jpg") == "dorsal"
    assert detect_view_type("casent0123456-d-2.jpg") == "dorsal"
    assert detect_view_type("casent0123456_d.png") == "dorsal"
    assert detect_view_type("my_dorsal_view.webp") == "dorsal"
    assert detect_view_type(Path("some/path/DORSAL_image.jpg")) == "dorsal"


def test_detect_view_head():
    assert detect_view_type("casent0123456_h_1.jpg") == "head"
    assert detect_view_type("casent0123456-h-2.jpg") == "head"
    assert detect_view_type("casent0123456_h.png") == "head"
    assert detect_view_type("my_head_view.webp") == "head"
    assert detect_view_type(Path("some/path/HEAD_image.jpg")) == "head"


def test_detect_view_profile():
    assert detect_view_type("casent0123456_p_1.jpg") == "profile"
    assert detect_view_type("casent0123456-p-2.jpg") == "profile"
    assert detect_view_type("casent0123456_p.png") == "profile"
    assert detect_view_type("my_profile_view.webp") == "profile"
    assert detect_view_type(Path("some/path/PROFILE_image.jpg")) == "profile"
    assert detect_view_type("casent0123456_lateral.jpg") == "profile"


def test_detect_view_unknown():
    assert detect_view_type("casent0123456_other.jpg") == "unknown"
    assert detect_view_type("ant_image.jpg") == "unknown"
    assert detect_view_type("") == "unknown"
