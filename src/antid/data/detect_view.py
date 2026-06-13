import sys
from pathlib import Path
from typing import Union


def detect_view_type(path: Union[str, Path]) -> str:
    """
    Detects the AntWeb-style image view type from a filename or file path.

    Rules:
    - filenames containing '_d_', '-d-', '_d.', or dorsal indicators -> 'dorsal'
    - filenames containing '_h_', '-h-', '_h.', or head indicators -> 'head'
    - filenames containing '_p_', '-p-', '_p.', or profile indicators -> 'profile'
    - otherwise -> 'unknown'

    Args:
        path: File path as a string or pathlib.Path.

    Returns:
        str: Detected view type ('dorsal', 'head', 'profile', or 'unknown').
    """
    name = Path(path).name.lower()

    # Dorsal indicators
    if any(pattern in name for pattern in ["_d_", "-d-", "_d.", "dorsal"]):
        return "dorsal"

    # Head indicators
    if any(pattern in name for pattern in ["_h_", "-h-", "_h.", "head"]):
        return "head"

    # Profile indicators
    if any(pattern in name for pattern in ["_p_", "-p-", "_p.", "profile", "lateral"]):
        return "profile"

    return "unknown"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 -m antid.data.detect_view <path/to/image.jpg>")
        sys.exit(1)

    image_path = sys.argv[1]
    view = detect_view_type(image_path)
    print(view)
